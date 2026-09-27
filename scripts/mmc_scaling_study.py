"""MakeMyClip export scaling study (open question #1).

Builds hard-cut timelines of N equal 2.5s clips from the synthetic source and
runs MakeMyClip's OWN compiled export plan step by step (integrations/makemyclip/
adapter.mjs profile-export), recording normalize (segment) vs fold time, plus a
one-pass concat-demuxer join of the same segments for comparison. Also measures
generational quality loss (SSIM of the first clip vs source) and verifies both
outputs frame-exactly with the barcode.

  python scripts/mmc_scaling_study.py [N ...]      default: 10 20 40 60
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from harness.mmc import MakeMyClipExecutionProvider  # noqa: E402
from harness.plan import time_map  # noqa: E402
from harness.trace import Trace  # noqa: E402
from harness.verify import decode_barcodes, provenance_report, ssim  # noqa: E402

EXP = Path(__file__).resolve().parents[1] / "experiments" / "video-editing"
CLIP = 2.5
FPS = 30


def synthetic_plan(n: int, manifest: dict) -> dict:
    segs, seq = [], []
    for i in range(n):
        # non-contiguous windows (skip 0.5s between) so every join is a real cut
        start = round(5.0 + i * (CLIP + 0.5), 6)
        segs.append({"segment_id": f"s{i}", "source_id": "cam_a", "source_start": start,
                     "source_end": round(start + CLIP, 6), "decision": "KEEP"})
        seq.append({"order": i, "kind": "segment", "segment_id": f"s{i}"})
    return {"schema_version": "edit-plan.v0", "project": {"project_id": "scaling", "title": "scaling",
            "canvas": {"width": 1920, "height": 1080, "fps": FPS}},
            "sources": [{"source_id": "cam_a", "path": manifest["path"], "duration_sec": manifest["duration_sec"]}],
            "segments": segs, "sequence": seq}


def main() -> None:
    ns = [int(a) for a in sys.argv[1:]] or [10, 20, 40, 60]
    manifest = json.loads((EXP / "fixtures" / "synth-interview-001.manifest.json").read_text(encoding="utf-8"))
    src = EXP / "fixtures" / manifest["path"]
    run_dir = EXP / "artifacts" / "mmc-scaling"
    trace = Trace(run_dir / "trace.jsonl", "mmc-scaling")
    rows = []
    for n in ns:
        plan = synthetic_plan(n, manifest)
        prov = MakeMyClipExecutionProvider(run_dir / f"ws-{n}", trace, mode="batched")
        t0 = time.perf_counter()
        prov.build_timeline(plan, EXP / "fixtures")
        build_s = time.perf_counter() - t0
        out = run_dir / "renders" / f"scaling-{n}.mp4"
        prof = prov.profile_export(out)
        alt = Path(prof["alternative"]["output"])
        tm = time_map(plan)
        std_check = provenance_report(decode_barcodes(out, FPS), tm, FPS)
        alt_check = provenance_report(decode_barcodes(alt, FPS), tm, FPS)
        first = tm[0]
        row = {
            "n_segments": n, "output_sec": n * CLIP, "build_s": round(build_s, 2),
            "mmc_export_s": round(prof["totalMs"] / 1000, 1),
            "normalize_s": round(prof["segmentMs"] / 1000, 1), "fold_s": round(prof["foldMs"] / 1000, 1),
            "concat_alt_total_s": round(prof["alternative"]["totalMs"] / 1000, 1),
            "fold_step_s_first": round(prof["steps"][n]["ms"] / 1000, 2) if n > 1 else None,
            "fold_step_s_last": round(prof["steps"][-1]["ms"] / 1000, 2),
            "mmc_drift_last_frames": std_check["drift_frames_last"],
            "mmc_duplicated_frames": std_check["duplicated_output_frames"],
            "mmc_missing_frames": std_check["missing_source_frames"],
            "alt_drift_last_frames": alt_check["drift_frames_last"],
            "alt_duplicated_frames": alt_check["duplicated_output_frames"],
            "alt_missing_frames": alt_check["missing_source_frames"],
            "ssim_first_clip_mmc": round(ssim(src, first["source_start"] + 0.5, out, 0.5, 1.5), 5),
            "ssim_first_clip_alt": round(ssim(src, first["source_start"] + 0.5, alt, 0.5, 1.5), 5),
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    dest = EXP / "evaluations" / "mmc-scaling" / "results.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
