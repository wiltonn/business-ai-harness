import copy
import json
from pathlib import Path

import pytest

from harness.plan import (graphics_placements, output_duration, plan_hash, structural_hash,
                          time_map, validate_plan)

SPIKE_PLAN = Path(__file__).resolve().parents[1] / "experiments/video-editing/plans/spike-001/edit-plan.json"


def mini_plan() -> dict:
    return {
        "schema_version": "edit-plan.v0",
        "project": {"project_id": "p", "title": "t", "canvas": {"width": 1920, "height": 1080, "fps": 30}},
        "sources": [{"source_id": "a", "path": "a.mp4", "duration_sec": 100.0}],
        "segments": [
            {"segment_id": "s1", "source_id": "a", "source_start": 10.0, "source_end": 14.0, "decision": "KEEP"},
            {"segment_id": "s2", "source_id": "a", "source_start": 30.0, "source_end": 33.0, "decision": "KEEP"},
            {"segment_id": "s3", "source_id": "a", "source_start": 50.0, "source_end": 52.0, "decision": "REMOVE"},
        ],
        "sequence": [
            {"order": 0, "kind": "title_card", "text": "Hi", "duration_sec": 2.0},
            {"order": 1, "kind": "segment", "segment_id": "s2"},
            {"order": 2, "kind": "segment", "segment_id": "s1", "transition_in": "fade", "transition_sec": 0.5},
        ],
        "graphics_requests": [{
            "graphics_request_id": "g1", "type": "speaker_id", "purpose": "who", "related_segment_id": "s1",
            "start_time": 1.0, "duration": 2.0, "content": {"name": "X", "title": "Y"},
            "required_or_optional": "optional", "status": "approved",
        }],
    }


def test_valid_mini_plan():
    rep = validate_plan(mini_plan())
    assert rep.ok, rep.errors


def test_time_map_with_transition_and_reorder():
    tm = time_map(mini_plan())
    assert [t["out_start"] for t in tm] == [0.0, 2.0, 4.5]  # s1 starts 0.5s early (fade overlap)
    assert output_duration(tm) == pytest.approx(8.5)
    assert tm[1]["trim_tail_transition"] == 0.5 and tm[2]["trim_head_transition"] == 0.5


def test_graphics_anchor_follows_segment_not_absolute_time():
    p = mini_plan()
    assert graphics_placements(p, time_map(p))[0]["out_start"] == pytest.approx(5.5)
    p["sequence"][0]["duration_sec"] = 4.0  # re-cut: longer title card
    assert graphics_placements(p, time_map(p))[0]["out_start"] == pytest.approx(7.5)


def test_graphics_change_does_not_change_structural_hash():
    p = mini_plan()
    q = copy.deepcopy(p)
    q["graphics_requests"][0]["content"]["title"] = "Different"
    q["graphics_requests"][0]["artifact_id"] = "art_v2"
    assert structural_hash(p) == structural_hash(q)
    assert plan_hash(p) != plan_hash(q)
    q["segments"][0]["source_end"] = 14.5
    assert structural_hash(p) != structural_hash(q)


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p["sequence"].append({"order": 3, "kind": "segment", "segment_id": "s3"}), "REMOVE, not KEEP"),
    (lambda p: p["sequence"].append({"order": 3, "kind": "segment", "segment_id": "s1"}), "used twice"),
    (lambda p: p["segments"][0].update(source_end=9.0), "source_start >= source_end"),
    (lambda p: p["segments"][0].update(source_end=101.0), "beyond source duration"),
    (lambda p: p["sequence"][2].update(transition_sec=3.0), "transition longer"),
    (lambda p: p["graphics_requests"][0]["content"].update(html="<div>"), "implementation keys"),
    (lambda p: p["graphics_requests"][0].update(related_segment_id="s3"), "not in the cut"),
])
def test_invariant_violations(mutate, needle):
    p = mini_plan()
    mutate(p)
    rep = validate_plan(p)
    assert not rep.ok
    assert any(needle in e for e in rep.errors), rep.errors


def test_spike_plan_is_valid_and_frame_aligned():
    plan = json.loads(SPIKE_PLAN.read_text(encoding="utf-8"))
    rep = validate_plan(plan)
    assert rep.ok, rep.errors
    assert not rep.warnings
