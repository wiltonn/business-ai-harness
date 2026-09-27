# Experiment: AI Interview Rough-Cut Harness

Status: **designed, not approved, not implemented.**

## Hypothesis

A decomposed harness using deterministic processing, bounded decisions, Claude reasoning,
MakeMyClip structural execution, and optional HyperFrames graphics can produce a **useful and
auditable** interview edit **more reliably** than a single unconstrained editing agent.

Success does **not** require HyperFrames or Resolve. The experiment succeeds even if the best
result uses zero HyperFrames assets.

## Pipeline and phases

| # | Phase | Layer | Provider (initial) | Output |
|---|---|---|---|---|
| 1 | Discover media | L1 | code + ffprobe | `sources[]` with hashes, durations |
| 2 | Transcribe | L1 | ASR (e.g. whisper) — **TBD** | word-timed transcript |
| 3 | Identify speakers | L1/L2 | diarization where practical; else interviewer/subject heuristic + review | `speakers[]` |
| 4 | Detect questions | L2/L3 | rule + bounded decision | `questions[]` |
| 5 | Segment answers | L1/L2 | sentence/pause boundaries (code), complete-thought decision | `segments[]` |
| 6 | Keep/remove | L2 | `keep_segment.v1` (rule/Jev/Claude) | decisions |
| 7 | Redundancy | L2 | `duplicate_of.v1` | decisions |
| 8 | Narrative assembly | L3 | Claude | ordering + rationale |
| 9 | Structured edit plan | L1 | code | `plans/<run>/edit-plan.json` (schema v0) |
| 10 | Validate plan | L1 | schema + invariants (in<out, within source, no overlaps, all refs resolve) | pass/fail |
| 11 | Build rough cut | L4 | MakeMyClip timeline (pinned 0.3.0) | MMC `composition.json` + op log |
| 12 | Render & evaluate | L4 + verify | MMC export; automated checks; AI review | `rough-cut-v1.mp4`, findings |
| 13 | Graphics opportunities (1–3 max) | L2/L3 | `needs_graphic.v1` + Claude intent | `graphics_requests[]` (default none) |
| 14 | Generate graphics (optional) | L5 | route: MMC drawtext / HyperFrames | versioned artifacts |
| 15 | Composite | L4/L5 | graphics pass over rough cut | `rough-cut+gfx-v1.mp4` |
| 16 | Compare with/without graphics | eval | human + AI review | usefulness vs distraction |
| 17 | Record human corrections | eval | correction records | `evaluations/<run>/corrections.jsonl` |

## Baselines (eventually)

| | Description |
|---|---|
| A | Human rough cut |
| B | Claude directly driving MakeMyClip (MMC skill / MCP, one prompt, no harness) |
| C | Decomposed harness + MakeMyClip |
| D | C + selective HyperFrames graphics |
| E | Optional Resolve-finished version |

## Metrics

content quality · semantic accuracy · edit mistakes (mid-word cuts, orphaned references, dropped
key answers) · graphics usefulness · visual distraction · processing time · inference cost ·
execution cost · number of model decisions (by provider) · human interventions · reproducibility
(same inputs → same plan/render?) · auditability (can a reviewer answer "why is this here?") ·
revision effort (time/ops to reach acceptable).

Rubrics and scoring sheets go in `evaluations/`.

## Layout

```
fixtures/     media manifests (hashes, paths, rights notes). Media files themselves are git-ignored
              under fixtures/media/.
plans/        edit plans per run: plans/<run_id>/edit-plan.json (+ previous versions)
artifacts/    per-run outputs: artifacts/<run_id>/{trace.jsonl, mmc-workspace/, renders/, graphics/}
evaluations/  rubrics, scores, human corrections per run
```

## Known execution risks (from research)

- MakeMyClip timeline export is single-track and folds segments with repeated re-encodes
  (quadratic time + generational loss) — must be measured with a real interview.
- MakeMyClip timeline cannot hold overlays; graphics are a separate post-pass.
- WebM-alpha and animated-overlay timing through MMC `overlay` are unverified.
- Multicam (camera A/B) has no execution support in MMC; phase 1 assumes single camera.

See `docs/research/makemyclip.md`, `docs/research/hyperframes.md`,
`docs/architecture/video-provider-relationships.md`.

## Open inputs needed from the project owner

- Real interview fixture(s) with usage rights (length, cameras, speakers).
- Jev access/API details.
- ASR/diarization choice constraints (local vs hosted, cost).
- A reference human rough cut for baseline A (can come later).
