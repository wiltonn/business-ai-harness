"""Pass 2: composite graphics artifacts over the structural rough cut.

Two interchangeable compositors, compared in the spike:
  - MakeMyClip `overlay` single-file tool (provider path)
  - a harness-owned FFmpeg overlay step that time-shifts each overlay stream so
    an animated artifact starts at frame 0 when it appears.
Placement times come from the plan's time map (segment-anchored), never from
the provider.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .tools import FFMPEG, MMC_CLI, provider_env, run
from .trace import Trace


def composite_mmc_overlay(base: Path, overlay: Path, placement: dict, out: Path,
                          workspace: Path, trace: Trace) -> float:
    env = provider_env({"MAKEMYCLIP_WORKSPACE": str(workspace)})
    # Full-frame overlay: `center` is the only anchor with zero edge padding.
    res = run(["node", str(MMC_CLI), "overlay", str(base), str(overlay), "center", "",
               f"{placement['out_start']:.3f}", f"{placement['out_end']:.3f}"], env=env)
    produced = Path(json.loads(res.stdout)["path"])
    shutil.move(str(produced), out)
    trace.event("provider_call", provider="makemyclip", step="overlay", base=str(base.name),
                overlay=str(overlay.name), placement=placement, output=out.name,
                elapsed_s=round(res.elapsed_s, 2))
    return res.elapsed_s


def composite_ffmpeg(base: Path, overlays: list[tuple[Path, dict]], out: Path, trace: Trace,
                     crf: int = 23) -> float:
    """Harness-owned compositor. Each overlay's timestamps are shifted to its
    placement start so animation frame 0 lands exactly on out_start."""
    args = ["-y", "-i", str(base)]
    chains = []
    last = "0:v"
    for i, (ov, pl) in enumerate(overlays, start=1):
        args += ["-i", str(ov)]
        chains.append(f"[{i}:v]setpts=PTS-STARTPTS+{pl['out_start']:.6f}/TB[o{i}]")
        chains.append(f"[{last}][o{i}]overlay=0:0:eof_action=pass:format=auto[v{i}]")
        last = f"v{i}"
    args += ["-filter_complex", ";".join(chains), "-map", f"[{last}]", "-map", "0:a?",
             "-c:v", "libx264", "-preset", "fast", "-crf", str(crf), "-pix_fmt", "yuv420p",
             "-c:a", "copy", str(out)]
    res = run([str(FFMPEG), "-hide_banner", "-loglevel", "error", *args])
    trace.event("provider_call", provider="harness-ffmpeg", step="composite", base=base.name,
                overlays=[{"file": o.name, **p} for o, p in overlays], output=out.name,
                elapsed_s=round(res.elapsed_s, 2))
    return res.elapsed_s
