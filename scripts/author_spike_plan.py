"""Author the Plan-to-Pixels spike edit plan from HUMAN editorial choices.

The editorial choices below (EDITORIAL) are hand-made — no model was consulted.
This script only does the deterministic parts: look up ground-truth sentence
timings, add handles, snap to the frame grid, and emit a schema-v0 plan with a
decision record for every sentence.

Output: experiments/video-editing/plans/spike-001/edit-plan.json
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "experiments" / "video-editing" / "fixtures"
OUT = ROOT / "experiments" / "video-editing" / "plans" / "spike-001" / "edit-plan.json"
FPS = 30
HEAD_HANDLE = 0.12
TAIL_HANDLE = 0.20

# Human editorial decisions: sentence -> (decision, reason)
REMOVE = {
    "a1_s1": "False start ('sorry, let me start that again').",
    "a2_s5": "Filler, no content.",
    "a4_s2": "Filler / stumble; adds nothing to the rebuttal.",
    "a5_s1": "Duplicate of a2_s1 (weaker phrasing of the same point).",
    "a5_s2": "Refers back to earlier answer; redundant once a5_s1 is removed.",
}
# Output order (sentence ids), with a title card and a cold open.
SEQUENCE = [
    ("segment", "a2_s1"),                      # cold open hook
    ("title_card", "Dana Reyes  -  Ward 3 Council Candidate"),
    ("segment", "a1_s2"), ("segment", "a1_s3"), ("segment", "a1_s4"), ("segment", "a1_s5"),
    ("segment", "a2_s2"), ("segment", "a2_s3"), ("segment", "a2_s4"),
    ("segment", "a3_s1"), ("segment", "a3_s2"), ("segment", "a3_s3"), ("segment", "a3_s4"), ("segment", "a3_s5"),
    ("segment", "a4_s1"), ("segment", "a4_s3"), ("segment", "a4_s4"),
    ("segment", "a6_s1"), ("segment", "a6_s2"), ("segment", "a6_s3"),
]
TRANSITION_INTO = {"a4_s1": ("fade", 0.5)}  # topic change: plan -> rebuttal
TITLE_CARD_SEC = 3.0


def snap(t: float) -> float:
    return round(round(t * FPS) / FPS, 6)


def main() -> None:
    tr = json.loads((FIX / "synth-interview-001.transcript.json").read_text(encoding="utf-8"))
    manifest = json.loads((FIX / "synth-interview-001.manifest.json").read_text(encoding="utf-8"))
    sents = tr["sentences"]
    by_id = {s["sentence_id"]: s for s in sents}
    idx = {s["sentence_id"]: i for i, s in enumerate(sents)}

    def window(sid: str) -> tuple[float, float]:
        s = by_id[sid]
        i = idx[sid]
        prev_end = sents[i - 1]["end"] if i > 0 else 0.0
        next_start = sents[i + 1]["start"] if i + 1 < len(sents) else manifest["duration_sec"]
        # handles never reach past the midpoint of the neighbouring pause
        start = max(s["start"] - HEAD_HANDLE, (prev_end + s["start"]) / 2)
        end = min(s["end"] + TAIL_HANDLE, (s["end"] + next_start) / 2)
        return snap(start), snap(end)

    speakers = [
        {"speaker_id": "interviewer", "name": "Interviewer", "is_interviewer": True},
        {"speaker_id": "dana", "name": "Dana Reyes", "role": "Candidate, City Council Ward 3",
         "is_interviewer": False},
    ]
    questions = []
    for s in sents:
        if s["speaker"] == "interviewer":
            questions.append({"question_id": s["turn_id"], "text": s["text"], "source_id": "cam_a",
                              "source_start": s["start"], "source_end": s["end"]})

    order_of = {sid: n for n, (k, sid) in enumerate(SEQUENCE) if k == "segment"}
    segments, decisions = [], []
    for s in sents:
        sid = s["sentence_id"]
        seg_id = f"seg_{sid}"
        if s["speaker"] == "interviewer":
            dec, reason = "REMOVE", "Interviewer question; answers stand alone."
        elif sid in REMOVE:
            dec, reason = "REMOVE", REMOVE[sid]
        else:
            dec, reason = "KEEP", "Substantive, complete thought."
        start, end = window(sid)
        segments.append({
            "segment_id": seg_id, "speaker": s["speaker"],
            "question_id": "q" + s["turn_id"][1:] if s["turn_id"].startswith("a") else s["turn_id"],
            "source_id": "cam_a", "source_start": start, "source_end": end,
            "transcript": s["text"], "decision": dec, "decision_provider": "human",
            "decision_confidence": 1.0, "reason": reason, "selected_visual_source": "cam_a",
            "timeline_order": order_of.get(sid), "review_required": False,
        })
        decisions.append({"decision_id": f"dec_keep_{sid}", "type": "keep_segment.v1",
                          "target_ref": seg_id, "provider": "human", "output": dec,
                          "confidence": 1.0, "reason": reason})
    decisions.append({"decision_id": "dec_dup_a5_s1", "type": "duplicate_of.v1",
                      "target_ref": "seg_a5_s1", "provider": "human",
                      "output": {"verdict": "DUPLICATE", "of": "seg_a2_s1", "keep": "seg_a2_s1"},
                      "confidence": 1.0, "reason": REMOVE["a5_s1"]})

    sequence = []
    for n, (kind, val) in enumerate(SEQUENCE):
        if kind == "segment":
            item = {"order": n, "kind": "segment", "segment_id": f"seg_{val}"}
            if val in TRANSITION_INTO:
                item["transition_in"], item["transition_sec"] = TRANSITION_INTO[val]
        else:
            item = {"order": n, "kind": "title_card", "text": val, "duration_sec": TITLE_CARD_SEC}
        sequence.append(item)

    plan = {
        "schema_version": "edit-plan.v0",
        "plan_id": "spike-001",
        "plan_version": 1,
        "project": {"project_id": "synth-interview-001", "title": "Dana Reyes interview (synthetic)",
                    "style_notes": "Plain rough cut. Cold open on the tax line.",
                    "canvas": {"width": 1920, "height": 1080, "fps": FPS}},
        "sources": [{"source_id": "cam_a", "path": manifest["path"], "content_hash": manifest["sha256"],
                     "role": "camera_a", "duration_sec": manifest["duration_sec"]}],
        "speakers": speakers,
        "questions": questions,
        "segments": segments,
        "decisions": decisions,
        "sequence": sequence,
        "graphics_requests": [{
            "graphics_request_id": "gfx_speaker_dana",
            "type": "speaker_id",
            "purpose": "Identify the speaker the first time she appears after the title card.",
            "related_segment_id": "seg_a1_s2",
            "start_time": 0.5,
            "duration": 5.0,
            "content": {"name": "Dana Reyes", "title": "Candidate, City Council Ward 3"},
            "style_intent": "Understated, modern, lower-left.",
            "provider_preference": "any",
            "required_or_optional": "optional",
            "status": "approved",
            "artifact_id": None,
        }],
        "review_flags": [],
        "artifacts": [],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    kept = sum(1 for s in segments if s["decision"] == "KEEP")
    print(json.dumps({"plan": str(OUT), "segments": len(segments), "kept": kept,
                      "sequence_items": len(sequence)}))


if __name__ == "__main__":
    main()
