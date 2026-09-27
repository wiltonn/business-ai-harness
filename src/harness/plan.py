"""Edit plan: load, validate (schema + invariants), hash, and derive the output time map.

The plan is the single source of truth for editorial intent. Everything here is
deterministic and provider-independent.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from .tools import REPO_ROOT

SCHEMA_PATH = REPO_ROOT / "schemas" / "edit-plan.v0.schema.json"
FRAME_EPS = 1e-6


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_plan(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_plan(plan: dict, fixtures_dir: Path | None = None) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(plan), key=str):
        errors.append(f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}")
    if errors:
        return ValidationReport(False, errors, warnings)

    fps = plan["project"].get("canvas", {}).get("fps", 30)
    sources = {s["source_id"]: s for s in plan["sources"]}
    segments = {s["segment_id"]: s for s in plan["segments"]}
    if len(segments) != len(plan["segments"]):
        errors.append("duplicate segment_id")

    for s in plan["segments"]:
        sid = s["segment_id"]
        if s["source_id"] not in sources:
            errors.append(f"{sid}: unknown source {s['source_id']}")
            continue
        if not s["source_start"] < s["source_end"]:
            errors.append(f"{sid}: source_start >= source_end")
        dur = sources[s["source_id"]].get("duration_sec")
        if dur is not None and s["source_end"] > dur + FRAME_EPS:
            errors.append(f"{sid}: source_end {s['source_end']} beyond source duration {dur}")
        for k in ("source_start", "source_end"):
            if abs(s[k] * fps - round(s[k] * fps)) > 1e-3:
                warnings.append(f"{sid}: {k} not on frame grid")
        if fixtures_dir is not None:
            p = fixtures_dir / sources[s["source_id"]]["path"]
            if not p.exists():
                errors.append(f"{sid}: source file missing: {p}")

    seen_orders = set()
    used = set()
    for i, item in enumerate(plan["sequence"]):
        if item["order"] in seen_orders:
            errors.append(f"sequence: duplicate order {item['order']}")
        seen_orders.add(item["order"])
        if item["kind"] == "segment":
            seg = segments.get(item.get("segment_id", ""))
            if seg is None:
                errors.append(f"sequence[{i}]: unknown segment {item.get('segment_id')}")
                continue
            if seg["decision"] != "KEEP":
                errors.append(f"sequence[{i}]: {seg['segment_id']} is {seg['decision']}, not KEEP")
            if seg["segment_id"] in used:
                errors.append(f"sequence[{i}]: {seg['segment_id']} used twice")
            used.add(seg["segment_id"])
            if item.get("transition_in", "cut") != "cut":
                if i == 0:
                    errors.append("sequence[0]: transition_in on first item")
        elif item["kind"] == "title_card":
            if not item.get("text") or not item.get("duration_sec"):
                errors.append(f"sequence[{i}]: title_card needs text and duration_sec")

    for s in plan["segments"]:
        if s["decision"] == "KEEP" and s["segment_id"] not in used:
            warnings.append(f"{s['segment_id']}: KEEP but not placed in sequence")

    # Transition must be shorter than both neighbours (MakeMyClip enforces the same).
    tm = time_map(plan) if not errors else []
    for n, it in enumerate(tm):
        t = it.get("transition_in_sec", 0)
        if t and (t >= it["duration"] or t >= tm[n - 1]["duration"]):
            errors.append(f"sequence order {it['order']}: transition longer than a neighbour")

    for g in plan.get("graphics_requests", []):
        seg = segments.get(g["related_segment_id"])
        if seg is None or seg["segment_id"] not in used:
            errors.append(f"{g['graphics_request_id']}: related segment not in the cut")
        forbidden = {"html", "css", "gsap", "template", "ffmpeg", "filter"}
        leaked = forbidden & {k.lower() for k in g.get("content", {})}
        if leaked:
            errors.append(f"{g['graphics_request_id']}: provider implementation keys in intent: {leaked}")

    return ValidationReport(not errors, errors, warnings)


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def structural_hash(plan: dict) -> str:
    """Hash of everything that affects the STRUCTURAL render (pass 1).
    Graphics requests, artifacts and review flags are excluded, so a graphics
    change never forces a re-cut."""
    p = copy.deepcopy(plan)
    for k in ("graphics_requests", "artifacts", "review_flags", "decisions", "plan_version"):
        p.pop(k, None)
    for s in p.get("segments", []):
        for k in ("reason", "decision_provider", "decision_confidence", "review_required"):
            s.pop(k, None)
    return hashlib.sha256(_canonical(p)).hexdigest()[:16]


def plan_hash(plan: dict) -> str:
    return hashlib.sha256(_canonical(plan)).hexdigest()[:16]


def time_map(plan: dict) -> list[dict]:
    """Deterministic output-time map for the sequence.

    A transition of d seconds into item k overlaps items k-1 and k by d, so item k
    starts d earlier than the previous item's end. Durations are frame-snapped."""
    fps = plan["project"].get("canvas", {}).get("fps", 30)
    segs = {s["segment_id"]: s for s in plan["segments"]}
    items = sorted(plan["sequence"], key=lambda x: x["order"])
    out: list[dict] = []
    cursor = 0.0
    for n, it in enumerate(items):
        if it["kind"] == "segment":
            s = segs[it["segment_id"]]
            dur = round((s["source_end"] - s["source_start"]) * fps) / fps
            entry = {"order": it["order"], "kind": "segment", "segment_id": s["segment_id"],
                     "source_start": s["source_start"], "source_end": s["source_end"]}
        else:
            dur = it["duration_sec"]
            entry = {"order": it["order"], "kind": it["kind"], "text": it.get("text")}
        trans = it.get("transition_sec", 0) if it.get("transition_in", "cut") != "cut" else 0
        start = cursor - trans if n > 0 else 0.0
        entry.update({"out_start": round(start, 6), "out_end": round(start + dur, 6),
                      "duration": dur, "transition_in_sec": trans,
                      "trim_head_transition": trans, "trim_tail_transition": 0.0})
        if trans and out:
            out[-1]["trim_tail_transition"] = trans
        out.append(entry)
        cursor = start + dur
    return out


def output_duration(tm: list[dict]) -> float:
    return tm[-1]["out_end"] if tm else 0.0


def graphics_placements(plan: dict, tm: list[dict]) -> list[dict]:
    """Resolve segment-anchored graphics intents to absolute output time."""
    by_seg = {t["segment_id"]: t for t in tm if t["kind"] == "segment"}
    out = []
    for g in plan.get("graphics_requests", []):
        if g["status"] not in ("approved", "rendered", "composited"):
            continue
        anchor = by_seg[g["related_segment_id"]]
        start = anchor["out_start"] + g.get("start_time", 0.0)
        out.append({"graphics_request_id": g["graphics_request_id"], "out_start": round(start, 6),
                    "out_end": round(start + g["duration"], 6), "duration": g["duration"]})
    return out
