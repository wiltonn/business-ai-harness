"""Verification: recover per-frame source provenance from the burned-in barcode,
and check renders against the edit plan and the expected time map.

These checks are deterministic code (Layer 1 / verification provider). They do
not trust any provider's own report of what it did.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .tools import FFMPEG, ffprobe_json, run

BARCODE = {"x": 40, "y": 36, "size": 48, "stride": 56, "cells": 17}
_THRESH = 100  # luma; white cell ≈ 200 after area-averaging the 8px gap


def decode_barcodes(video: Path, fps: int = 30) -> list[int | None]:
    """Return, for every frame of `video`, the source frame number (or None if the
    marker block is absent, e.g. title cards / generated clips)."""
    b = BARCODE
    w = b["cells"] * b["stride"]
    res = run([
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf", f"fps={fps},crop={w}:{b['size']}:{b['x']}:{b['y']},scale={b['cells']}:1:flags=area,format=gray",
        "-f", "rawvideo", "-",
    ], binary=True)
    return _decode_raw(res.stdout, b["cells"])


def _decode_raw(raw: bytes, cells: int) -> list[int | None]:
    out: list[int | None] = []
    for i in range(0, len(raw) - cells + 1, cells):
        row = raw[i:i + cells]
        if row[0] < _THRESH:
            out.append(None)
            continue
        n = 0
        for bit in range(16):
            if row[bit + 1] >= _THRESH:
                n |= 1 << bit
        out.append(n)
    return out


def probe_media(path: Path) -> dict:
    p = ffprobe_json(path)
    v = next((s for s in p["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    fps = None
    if v and v.get("r_frame_rate") and v["r_frame_rate"] != "0/0":
        num, den = v["r_frame_rate"].split("/")
        fps = float(num) / float(den)
    pix = v.get("pix_fmt") if v else None
    return {
        "duration_sec": float(p["format"].get("duration", 0.0)),
        "width": v and v["width"], "height": v and v["height"], "fps": fps,
        "codec": v and v["codec_name"], "pix_fmt": pix,
        "has_alpha": bool(pix and ("yuva" in pix or "rgba" in pix or "argb" in pix or pix.startswith("ya"))),
        "has_audio": a is not None,
    }


@dataclass
class BoundaryCheck:
    item_order: int
    segment_id: str
    expected_first_src_frame: int
    observed_first_src_frame: int | None
    expected_last_src_frame: int
    observed_last_src_frame: int | None
    frames_expected: int
    frames_observed: int
    off_by_frames_start: int | None
    off_by_frames_end: int | None


def check_against_timemap(codes: list[int | None], timemap: list[dict], fps: int) -> dict:
    """Compare decoded source frames with the plan's expected output time map.

    Transition windows are excluded (blended frames carry mixed barcodes)."""
    checks: list[BoundaryCheck] = []
    for item in timemap:
        if item["kind"] != "segment":
            continue
        o0 = round(item["out_start"] * fps) + round(item.get("trim_head_transition", 0) * fps)
        o1 = round(item["out_end"] * fps) - round(item.get("trim_tail_transition", 0) * fps)
        window = [c for c in codes[o0:o1]]
        observed = [c for c in window if c is not None]
        s0 = round(item["source_start"] * fps) + round(item.get("trim_head_transition", 0) * fps)
        s1 = round(item["source_end"] * fps) - round(item.get("trim_tail_transition", 0) * fps) - 1
        first = observed[0] if observed else None
        last = observed[-1] if observed else None
        checks.append(BoundaryCheck(
            item["order"], item["segment_id"], s0, first, s1, last, o1 - o0, len(observed),
            None if first is None else first - s0, None if last is None else last - s1,
        ))
    # Monotonic continuity inside each segment window: any jump != +1 is a dropped/duplicated frame
    discontinuities = 0
    for item in timemap:
        if item["kind"] != "segment":
            continue
        o0 = round(item["out_start"] * fps) + round(item.get("trim_head_transition", 0) * fps)
        o1 = round(item["out_end"] * fps) - round(item.get("trim_tail_transition", 0) * fps)
        seq = [c for c in codes[o0:o1] if c is not None]
        discontinuities += sum(1 for a, b in zip(seq, seq[1:]) if b - a != 1)
    starts = [c.off_by_frames_start for c in checks if c.off_by_frames_start is not None]
    ends = [c.off_by_frames_end for c in checks if c.off_by_frames_end is not None]
    return {
        "segments_checked": len(checks),
        "max_abs_start_error_frames": max((abs(x) for x in starts), default=None),
        "max_abs_end_error_frames": max((abs(x) for x in ends), default=None),
        "segments_exact": sum(1 for c in checks if c.off_by_frames_start == 0 and c.off_by_frames_end == 0),
        "intra_segment_discontinuities": discontinuities,
        "details": [c.__dict__ for c in checks],
    }


def provenance_report(codes: list[int | None], timemap: list[dict], fps: int) -> dict:
    """Content + timing truth, per segment, independent of window guesses:

    - drift: output frame where the segment's first source frame ACTUALLY appears,
      minus where the plan says it should (positive = late).
    - missing: planned source frames that never appear in the output.
    - duplicates: output frames that repeat the previous frame's source frame.
    - foreign: source frames present in the output that no segment planned."""
    first_pos: dict[int, int] = {}
    for i, c in enumerate(codes):
        if c is not None and c not in first_pos:
            first_pos[c] = i
    planned: set[int] = set()
    rows = []
    for item in timemap:
        if item["kind"] != "segment":
            continue
        s0 = round(item["source_start"] * fps)
        s1 = round(item["source_end"] * fps)  # exclusive
        frames = range(s0, s1)
        planned.update(frames)
        head = round(item.get("trim_head_transition", 0) * fps)
        anchor = s0 + head  # first frame not blended by an incoming transition
        pos = first_pos.get(anchor)
        rows.append({
            "segment_id": item["segment_id"],
            "drift_frames": None if pos is None else pos - (round(item["out_start"] * fps) + head),
            "missing_frames": sum(1 for f in frames if f not in first_pos),
        })
    dups = sum(1 for a, b in zip(codes, codes[1:]) if a is not None and a == b)
    foreign = sorted({c for c in codes if c is not None and c not in planned})
    drifts = [r["drift_frames"] for r in rows if r["drift_frames"] is not None]
    return {
        "segments": len(rows),
        "segments_zero_drift": sum(1 for d in drifts if d == 0),
        "drift_frames_first": drifts[0] if drifts else None,
        "drift_frames_last": drifts[-1] if drifts else None,
        "drift_frames_max_abs": max((abs(d) for d in drifts), default=None),
        "missing_source_frames": sum(r["missing_frames"] for r in rows),
        "duplicated_output_frames": dups,
        "foreign_source_frames": len(foreign),
        "per_segment": rows,
    }


def locate_output_time(codes: list[int | None], src_frame: int, fps: int) -> float | None:
    for i, c in enumerate(codes):
        if c == src_frame:
            return i / fps
    return None


def region_luma_diff(a: Path, b: Path, at_sec: float, region: tuple[int, int, int, int]) -> float:
    """Mean absolute luma difference between two videos at `at_sec` in a region
    (x, y, w, h). Used to detect whether an overlay is visible."""
    x, y, w, h = region

    def grab(p: Path) -> bytes:
        r = run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-ss", f"{at_sec:.3f}", "-i", str(p),
                 "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y},scale={w // 8}:{h // 8}:flags=area,format=gray",
                 "-f", "rawvideo", "-"], binary=True)
        return r.stdout

    pa, pb = grab(a), grab(b)
    n = min(len(pa), len(pb))
    return sum(abs(pa[i] - pb[i]) for i in range(n)) / max(n, 1)


def ssim(ref: Path, ref_ss: float, test: Path, test_ss: float, dur: float) -> float:
    """SSIM (All) between a window of `test` and the corresponding window of `ref`."""
    r = run([str(FFMPEG), "-hide_banner", "-ss", f"{test_ss:.3f}", "-t", f"{dur:.3f}", "-i", str(test),
             "-ss", f"{ref_ss:.3f}", "-t", f"{dur:.3f}", "-i", str(ref),
             "-lavfi", "[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]ssim", "-f", "null", "-"],
            check=True)
    for line in r.stderr.splitlines():
        if "SSIM" in line and "All:" in line:
            return float(line.split("All:")[1].split()[0])
    raise RuntimeError("no SSIM output")


LOWER_THIRD_REGION = (96, 780, 700, 150)  # x, y, w, h — where the speaker lower-third sits


def region_series(video: Path, start: float, end: float, fps: int,
                  region: tuple[int, int, int, int]) -> list[bytes]:
    """Downscaled gray crops of `region` for every frame in [start, end)."""
    x, y, w, h = region
    sw, sh = w // 10, h // 10
    r = run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-ss", f"{start:.4f}", "-i", str(video),
             "-t", f"{end - start:.4f}", "-vf", f"fps={fps},crop={w}:{h}:{x}:{y},scale={sw}:{sh}:flags=area,format=gray",
             "-f", "rawvideo", "-"], binary=True)
    n = sw * sh
    return [r.stdout[i:i + n] for i in range(0, len(r.stdout) - n + 1, n)]


def overlay_timing(base: Path, composite: Path, placement: dict, fps: int = 30,
                   margin: float = 1.0, threshold: float = 6.0) -> dict:
    """Detect when an overlay is actually visible in `composite` (vs `base`) and
    compare with the planned placement. Returns onset/offset errors in frames."""
    t0 = max(0.0, placement["out_start"] - margin)
    t1 = placement["out_end"] + margin
    a = region_series(base, t0, t1, fps, LOWER_THIRD_REGION)
    b = region_series(composite, t0, t1, fps, LOWER_THIRD_REGION)
    diffs = [sum(abs(x - y) for x, y in zip(fa, fb)) / max(len(fa), 1) for fa, fb in zip(a, b)]
    visible = [i for i, d in enumerate(diffs) if d > threshold]
    f0 = round(t0 * fps)
    if not visible:
        return {"visible": False, "planned_start_frame": round(placement["out_start"] * fps),
                "planned_end_frame": round(placement["out_end"] * fps), "peak_diff": round(max(diffs, default=0), 2)}
    onset, offset = f0 + visible[0], f0 + visible[-1] + 1
    ps, pe = round(placement["out_start"] * fps), round(placement["out_end"] * fps)
    peak_i = max(range(len(diffs)), key=lambda i: diffs[i])
    return {"visible": True, "onset_frame": onset, "offset_frame": offset,
            "planned_start_frame": ps, "planned_end_frame": pe,
            "onset_error_frames": onset - ps, "offset_error_frames": offset - pe,
            "peak_diff": round(diffs[peak_i], 2), "peak_frame": f0 + peak_i,
            # animated intro reaches plateau ~0.6s in: frames from onset until diff >= 90% of peak
            "frames_to_plateau": next(i for i in range(visible[0], len(diffs)) if diffs[i] >= 0.9 * diffs[peak_i]) - visible[0]}
