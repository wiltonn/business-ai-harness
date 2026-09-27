"""Locations of pinned external tools and a traced subprocess runner.

All external tools are consumed from `integrations/node_modules` (pinned in
`integrations/package.json`) so runs are reproducible and never depend on
whatever happens to be on PATH (this machine's PATH ffmpeg is 4.2).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NODE_MODULES = REPO_ROOT / "integrations" / "node_modules"

FFMPEG = NODE_MODULES / "ffmpeg-static" / "ffmpeg.exe"
FFPROBE = NODE_MODULES / "ffprobe-static" / "bin" / "win32" / "x64" / "ffprobe.exe"
MMC_CLI = NODE_MODULES / "@makemyclip" / "editor" / "dist" / "cli.js"
HF_CLI = NODE_MODULES / "hyperframes" / "bin" / "hyperframes.mjs"

MMC_VERSION = "0.3.0"
HF_VERSION = "0.8.79"


@dataclass
class RunResult:
    args: list[str]
    returncode: int
    stdout: str | bytes
    stderr: str
    elapsed_s: float

    def json(self) -> object:
        return json.loads(self.stdout)


class ToolError(RuntimeError):
    pass


def provider_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for provider subprocesses: pinned ffmpeg first on PATH, no telemetry."""
    env = dict(os.environ)
    tool_dirs = [str(FFMPEG.parent), str(FFPROBE.parent)]
    env["PATH"] = os.pathsep.join(tool_dirs + [env.get("PATH", "")])
    env["MAKEMYCLIP_FFMPEG_PATH"] = str(FFMPEG)
    env["HYPERFRAMES_NO_TELEMETRY"] = "1"
    env["DO_NOT_TRACK"] = "1"
    env["HYPERFRAMES_SKIP_SKILLS"] = "1"
    if extra:
        env.update(extra)
    return env


def run(args: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None,
        check: bool = True, timeout: float | None = None, binary: bool = False) -> RunResult:
    """Run a tool. `binary=True` returns stdout as bytes (raw frames); stderr is always text."""
    start = time.perf_counter()
    proc = subprocess.run([str(a) for a in args], capture_output=True, env=env, cwd=cwd,
                          timeout=timeout)
    stdout = proc.stdout if binary else proc.stdout.decode("utf-8", errors="replace")
    result = RunResult([str(a) for a in args], proc.returncode, stdout,
                       proc.stderr.decode("utf-8", errors="replace"), time.perf_counter() - start)
    if check and proc.returncode != 0:
        raise ToolError(f"{args[0]} exited {proc.returncode}:\n{proc.stderr[-3000:]}")
    return result


def ffmpeg(args: list[str], **kw) -> RunResult:
    return run([str(FFMPEG), "-hide_banner", "-loglevel", "error", *args], **kw)


def ffprobe_json(path: Path) -> dict:
    res = run([str(FFPROBE), "-v", "error", "-print_format", "json", "-show_format",
               "-show_streams", str(path)])
    return json.loads(res.stdout)
