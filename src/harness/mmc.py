"""MakeMyClipExecutionProvider — compiles a validated edit plan into MakeMyClip
timeline commands (pinned CLI), verifies MakeMyClip's document against the plan,
and exports the structural rough cut (pass 1).

MakeMyClip owns HOW clips are cut and encoded. The plan owns WHAT and WHY.
Nothing editorial is decided here.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .plan import time_map
from .tools import MMC_CLI, MMC_VERSION, REPO_ROOT, RunResult, provider_env, run
from .trace import Trace

TITLE_STYLE = ["--font", "64", "--color", "white"]
ADAPTER = REPO_ROOT / "integrations" / "makemyclip" / "adapter.mjs"
TOLERANCE = 1e-4


@dataclass
class StructuralResult:
    output: Path
    workspace: Path
    clip_map: dict[int, str]          # sequence order -> MakeMyClip clip id
    export_seconds: float
    export_steps: int


class MakeMyClipExecutionProvider:
    name = "makemyclip"
    version = MMC_VERSION

    def __init__(self, workspace: Path, trace: Trace, mode: str = "batched",
                 title_card_renderer=None):
        if mode not in ("batched", "cli"):
            raise ValueError(mode)
        self.mode = mode
        # Optional callable(item) -> artifact dict: realizes title cards as media
        # clips instead of MakeMyClip text clips (broken on Windows in 0.3.0).
        self.title_card_renderer = title_card_renderer
        self.run_dir = workspace.parent
        self.workspace = workspace
        self.trace = trace
        self.env = provider_env({"MAKEMYCLIP_WORKSPACE": str(workspace)})

    # -- low level ---------------------------------------------------------
    def _clip(self, *args: str, step: str, **ctx) -> RunResult:
        res = run(["node", str(MMC_CLI), *args], env=self.env)
        self.trace.event("provider_call", provider=self.name, provider_version=self.version,
                         step=step, args=list(args), elapsed_s=round(res.elapsed_s, 3),
                         result=_safe_json(res.stdout), **ctx)
        return res

    # -- compile -----------------------------------------------------------
    def build_timeline(self, plan: dict, fixtures_dir: Path) -> dict[int, str]:
        return (self._build_batched if self.mode == "batched" else self._build_cli)(plan, fixtures_dir)

    def _build_batched(self, plan: dict, fixtures_dir: Path) -> dict[int, str]:
        """One ingest per source + one atomic op batch via MakeMyClip's library API."""
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True)
        canvas = plan["project"].get("canvas", {})
        sources = {s["source_id"]: s for s in plan["sources"]}
        segs = {s["segment_id"]: s for s in plan["segments"]}
        ordered = sorted(plan["sequence"], key=lambda x: x["order"])
        items = []
        for item in ordered:
            if item["kind"] == "segment":
                s = segs[item["segment_id"]]
                entry = {"kind": "media", "path": str((fixtures_dir / sources[s["source_id"]]["path"]).resolve()),
                         "inSec": s["source_start"], "outSec": s["source_end"], "planRef": s["segment_id"]}
            elif item["kind"] == "title_card" and self.title_card_renderer is not None:
                art = self.title_card_renderer(item)
                path = (self.run_dir / art["render_path"]).resolve()
                entry = {"kind": "media", "path": str(path), "inSec": 0.0, "outSec": item["duration_sec"],
                         "planRef": f"sequence[{item['order']}]", "artifact_id": art["artifact_id"]}
            elif item["kind"] == "title_card":
                entry = {"kind": "text", "text": item["text"], "durationSec": item["duration_sec"],
                         "style": {"fontSize": 64, "color": "white"}, "planRef": f"sequence[{item['order']}]"}
            else:
                raise NotImplementedError(item["kind"])
            if item.get("transition_in", "cut") != "cut":
                entry["transitionIn"] = {"kind": item["transition_in"], "durationSec": item["transition_sec"]}
            items.append(entry)
        job = {"canvas": {"width": canvas.get("width", 1920), "height": canvas.get("height", 1080),
                          "fps": canvas.get("fps", 30), "background": "black"}, "items": items}
        job_path = self.workspace.parent / "mmc-build-job.json"
        job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        res = run(["node", str(ADAPTER), "build", str(job_path)], env=self.env)
        out = res.json()
        self.trace.event("provider_call", provider=self.name, provider_version=self.version,
                         step="adapter_build_batched", elapsed_s=round(res.elapsed_s, 3),
                         result={k: out[k] for k in ("ingests", "rev", "ops")},
                         plan_refs=[i["planRef"] for i in items])
        return {item["order"]: cid for item, cid in zip(ordered, out["clipIds"])}

    def _build_cli(self, plan: dict, fixtures_dir: Path) -> dict[int, str]:
        """One CLI call per plan item (MakeMyClip's documented agent path)."""
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True)
        canvas = plan["project"].get("canvas", {})
        self._clip("timeline", "new", "--width", str(canvas.get("width", 1920)),
                   "--height", str(canvas.get("height", 1080)), "--fps", str(canvas.get("fps", 30)),
                   "--background", "black", step="timeline_new")
        sources = {s["source_id"]: s for s in plan["sources"]}
        segs = {s["segment_id"]: s for s in plan["segments"]}
        clip_map: dict[int, str] = {}
        prev_clip = None
        for item in sorted(plan["sequence"], key=lambda x: x["order"]):
            if item["kind"] == "segment":
                s = segs[item["segment_id"]]
                src = (fixtures_dir / sources[s["source_id"]]["path"]).resolve()
                res = self._clip("timeline", "add-media", str(src), f"{s['source_start']:.6f}",
                                 f"{s['source_end']:.6f}", step="add_media",
                                 plan_ref=s["segment_id"], order=item["order"])
            elif item["kind"] == "title_card":
                res = self._clip("timeline", "add-text", item["text"], f"{item['duration_sec']:.6f}",
                                 *TITLE_STYLE, step="add_text", plan_ref=f"sequence[{item['order']}]",
                                 order=item["order"])
            else:
                raise NotImplementedError(item["kind"])
            clip_id = res.json()["clipId"]
            clip_map[item["order"]] = clip_id
            if item.get("transition_in", "cut") != "cut":
                self._clip("timeline", "transition", prev_clip, item["transition_in"],
                           f"{item['transition_sec']:.6f}", step="transition",
                           plan_ref=f"sequence[{item['order']}]", order=item["order"])
            prev_clip = clip_id
        return clip_map

    # -- verify provider state against the plan ------------------------------
    def verify_document(self, plan: dict, clip_map: dict[int, str]) -> dict:
        show = self._clip("timeline", "show", step="timeline_show").json()
        comp = json.loads((self.workspace / "composition.json").read_text(encoding="utf-8"))
        clips = {c["id"]: c for t in comp["tracks"] for c in t["clips"]}
        segs = {s["segment_id"]: s for s in plan["segments"]}
        problems: list[str] = []
        if not show.get("exportable"):
            problems.append(f"not exportable: {show.get('blockers')}")
        ordered = sorted(plan["sequence"], key=lambda x: x["order"])
        if len(clips) != len(ordered):
            problems.append(f"clip count {len(clips)} != plan items {len(ordered)}")
        # Order on the track must equal plan order.
        by_start = sorted(clips.values(), key=lambda c: c["startSec"])
        expected_ids = [clip_map[i["order"]] for i in ordered]
        if [c["id"] for c in by_start] != expected_ids:
            problems.append("clip order differs from plan sequence")
        for item in ordered:
            c = clips.get(clip_map[item["order"]])
            if c is None:
                problems.append(f"order {item['order']}: clip missing")
                continue
            if item["kind"] == "segment":
                s = segs[item["segment_id"]]
                if abs(c["sourceInSec"] - s["source_start"]) > TOLERANCE or \
                        abs(c["sourceOutSec"] - s["source_end"]) > TOLERANCE:
                    problems.append(f"{s['segment_id']}: window {c['sourceInSec']}-{c['sourceOutSec']} "
                                    f"!= plan {s['source_start']}-{s['source_end']}")
            elif item["kind"] == "title_card":
                if c["kind"] == "text" and c.get("text") != item["text"]:
                    problems.append(f"order {item['order']}: title text differs")
                if c["kind"] == "media" and \
                        abs((c["sourceOutSec"] - c["sourceInSec"]) - item["duration_sec"]) > TOLERANCE:
                    problems.append(f"order {item['order']}: title card duration differs")
        transitions = [t for tr in comp["tracks"] for t in tr["transitions"]]
        expected_tr = [i for i in ordered if i.get("transition_in", "cut") != "cut"]
        if len(transitions) != len(expected_tr):
            problems.append(f"transition count {len(transitions)} != plan {len(expected_tr)}")
        report = {"ok": not problems, "problems": problems, "mmc_rev": comp.get("rev"),
                  "clips": len(clips), "transitions": len(transitions)}
        self.trace.event("verification", check="mmc_document_matches_plan", **report)
        return report

    def profile_export(self, output: Path) -> dict:
        """Measurement: run MakeMyClip's own compiled export plan step by step."""
        output.parent.mkdir(parents=True, exist_ok=True)
        res = run(["node", str(ADAPTER), "profile-export", str(output)], env=self.env)
        data = res.json()
        self.trace.event("measurement", step="profile_export", total_ms=data["totalMs"],
                         segment_ms=data["segmentMs"], fold_ms=data["foldMs"],
                         alternative=data["alternative"])
        return data

    def export(self, output: Path) -> tuple[float, int]:
        output.parent.mkdir(parents=True, exist_ok=True)
        res = self._clip("timeline", "export", str(output), step="timeline_export")
        data = res.json()
        steps = data.get("steps", 0)
        return res.elapsed_s, steps if isinstance(steps, int) else len(steps)

    def snapshot_state(self, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("composition.json", "composition-ops.json", "session.json"):
            p = self.workspace / name
            if p.exists():
                shutil.copy2(p, dest / name)

    def execute(self, plan: dict, fixtures_dir: Path, output: Path) -> StructuralResult:
        clip_map = self.build_timeline(plan, fixtures_dir)
        doc = self.verify_document(plan, clip_map)
        if not doc["ok"]:
            raise RuntimeError(f"MakeMyClip document does not match plan: {doc['problems']}")
        secs, steps = self.export(output)
        return StructuralResult(output, self.workspace, clip_map, secs, steps)


def _safe_json(s: str) -> object:
    try:
        v = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s[-500:] if isinstance(s, str) else None
    if isinstance(v, dict) and isinstance(v.get("steps"), list):  # keep traces small
        v = {k: v[k] for k in v if k != "steps"} | {"step_count": len(v["steps"])}
    return v


__all__ = ["MakeMyClipExecutionProvider", "StructuralResult", "time_map"]
