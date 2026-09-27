"""Graphics providers: turn a semantic GraphicsIntent into a versioned artifact.

The mapping from intent -> implementation (template, variables, style) lives HERE,
never in the edit plan.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .tools import HF_CLI, HF_VERSION, MMC_CLI, MMC_VERSION, REPO_ROOT, provider_env, run
from .trace import Trace
from .verify import probe_media

HF_TEMPLATES = REPO_ROOT / "integrations" / "hyperframes" / "templates"
GSAP = REPO_ROOT / "integrations" / "node_modules" / "gsap" / "dist" / "gsap.min.js"

# Style is a provider concern. The plan says "understated, modern"; this table
# is the (deliberately trivial) interpretation.
HF_STYLE = {"v1": {"accent": "#f5b700"}, "v2": {"accent": "#3aa0ff"}}
INTENT_TO_TEMPLATE = {"speaker_id": "lower-third-v1"}


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _artifact(artifact_id: str, type_: str, provider: str, request_id: str, path: Path,
              version: int, source_files: list[str], run_dir: Path, extra: dict) -> dict:
    facts = probe_media(path)
    return {
        "artifact_id": artifact_id, "type": type_, "provider": provider,
        "source_request_id": request_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_sec": facts["duration_sec"], "width": facts["width"], "height": facts["height"],
        "fps": facts["fps"], "has_alpha": facts["has_alpha"], "pix_fmt": facts["pix_fmt"],
        "source_files": source_files, "render_path": str(path.relative_to(run_dir)).replace("\\", "/"),
        "content_hash": _sha256(path), "version": version, "status": "rendered", **extra,
    }


class HyperFramesGraphicsProvider:
    name = "hyperframes"
    version = HF_VERSION

    def __init__(self, run_dir: Path, trace: Trace):
        self.run_dir = run_dir
        self.trace = trace

    def render(self, request: dict, version: int, fps: int, style_key: str) -> dict:
        template = INTENT_TO_TEMPLATE.get(request["type"])
        if template is None:
            raise NotImplementedError(f"no HyperFrames template for intent type {request['type']}")
        rid = request["graphics_request_id"]
        proj = self.run_dir / "graphics" / f"{rid}.hf.v{version}"
        if proj.exists():
            shutil.rmtree(proj)
        (proj / "vendor").mkdir(parents=True)
        shutil.copy2(HF_TEMPLATES / template / "index.html", proj / "index.html")
        shutil.copy2(GSAP, proj / "vendor" / "gsap.min.js")
        variables = {"name": request["content"]["name"], "title": request["content"]["title"],
                     **HF_STYLE[style_key]}
        vars_path = proj / "variables.json"
        vars_path.write_text(json.dumps(variables, indent=2), encoding="utf-8")
        out = self.run_dir / "renders" / f"{rid}.hf.v{version}.mov"
        out.parent.mkdir(parents=True, exist_ok=True)
        res = run(["node", str(HF_CLI), "render", str(proj), "--format", "mov", "--fps", str(fps),
                   "--variables-file", str(vars_path), "--strict-variables", "--quiet", "-o", str(out)],
                  env=provider_env())
        art = _artifact(f"art_{rid}_hf_v{version}", "graphic_overlay", self.name, rid, out, version,
                        [f"integrations/hyperframes/templates/{template}/index.html",
                         str(vars_path.relative_to(self.run_dir)).replace("\\", "/")],
                        self.run_dir, {"provider_version": self.version, "template": template,
                                       "variables": variables, "render_seconds": round(res.elapsed_s, 2)})
        self.trace.event("artifact", provider=self.name, action="render", artifact=art)
        return art


class MakeMyClipTextGraphicsProvider:
    """Static drawtext realization. MakeMyClip's add_text burns directly into a base
    video, so this provider's artifact is a composite, not a standalone overlay."""
    name = "makemyclip"
    version = MMC_VERSION

    def __init__(self, run_dir: Path, trace: Trace, workspace: Path):
        self.run_dir = run_dir
        self.trace = trace
        self.env = provider_env({"MAKEMYCLIP_WORKSPACE": str(workspace)})

    def render_and_composite(self, request: dict, base: Path, placement: dict, version: int) -> dict:
        c = request["content"]
        text = f"{c['name']}  |  {c['title']}"
        res = run(["node", str(MMC_CLI), "add_text", str(base), text, "bottom-left",
                   f"{placement['out_start']:.3f}", f"{placement['out_end']:.3f}"], env=self.env)
        produced = Path(json.loads(res.stdout)["path"])
        rid = request["graphics_request_id"]
        out = self.run_dir / "renders" / f"rough-cut+{rid}.mmc-text.v{version}.mp4"
        shutil.move(str(produced), out)
        art = _artifact(f"art_{rid}_mmc_text_v{version}", "composite", self.name, rid, out, version,
                        [], self.run_dir, {"provider_version": self.version, "text": text,
                                            "placement": placement, "render_seconds": round(res.elapsed_s, 2)})
        self.trace.event("artifact", provider=self.name, action="render_and_composite", artifact=art)
        return art


def ffmpeg_filter_path(path: Path) -> str:
    """Quote a file path for an FFmpeg filter OPTION value on any OS.

    The filtergraph parser strips one quoting level and the filter's own option
    parser splits on ':' — so a Windows drive colon must be escaped as a
    backslash-colon. (MakeMyClip 0.3.0's quoteFilterArg only doubles backslashes,
    which breaks every drawtext path on Windows — see docs/research/makemyclip.md.)"""
    bs = "\\"
    s = str(path).replace(bs, "/").replace(":", bs + ":").replace("'", bs + "'")
    return f"'{s}'"


class HarnessTitleCardProvider:
    """Deterministic full-screen title card rendered as a media clip, matching
    MakeMyClip's text-clip style (64px white, centred, black). Used instead of a
    MakeMyClip text clip where that path is broken (Windows)."""
    name = "harness-ffmpeg"

    def __init__(self, run_dir: Path, trace: Trace, width: int = 1920, height: int = 1080, fps: int = 30):
        self.run_dir, self.trace = run_dir, trace
        self.width, self.height, self.fps = width, height, fps

    def render(self, text: str, duration: float, request_ref: str) -> dict:
        from .tools import ffmpeg
        out_dir = self.run_dir / "renders"
        out_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(f"{text}|{duration}|{self.width}x{self.height}@{self.fps}".encode()).hexdigest()[:10]
        out = out_dir / f"title-card.{key}.mp4"
        textfile = self.run_dir / "graphics" / f"title-card.{key}.txt"
        textfile.parent.mkdir(parents=True, exist_ok=True)
        textfile.write_text(text, encoding="utf-8")
        if not out.exists():
            ffmpeg(["-y", "-f", "lavfi", "-i", f"color=c=black:s={self.width}x{self.height}:r={self.fps}",
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-vf", f"drawtext=textfile={ffmpeg_filter_path(textfile)}:fontsize=64:fontcolor=white:"
                           "x=(w-text_w)/2:y=(h-text_h)/2,format=yuv420p",
                    "-t", f"{duration:.6f}", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-ar", "48000", str(out)])
        art = _artifact(f"art_titlecard_{key}", "title_card", self.name, request_ref, out, 1,
                        [str(textfile.relative_to(self.run_dir)).replace("\\", "/")], self.run_dir, {"text": text})
        self.trace.event("artifact", provider=self.name, action="render", artifact=art)
        return art
