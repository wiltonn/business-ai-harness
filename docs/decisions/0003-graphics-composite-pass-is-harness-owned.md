# ADR 0003 — Graphics compositing is a separate, harness-owned pass (for now)

- Status: Accepted (spike-001 evidence)
- Date: 2026-09-26

## Context

The default hypothesis placed HyperFrames artifacts inside the MakeMyClip timeline. Research
showed MakeMyClip 0.3.0 export is single-track (no overlays in the composition document). The spike
then measured the remaining MakeMyClip routes:

| Route | Result on spike-001 |
|---|---|
| HyperFrames ProRes-4444 → MakeMyClip `overlay` | **Overlay invisible** (peak region diff 5.9 vs 55 for the working route). The overlay stream starts at base t=0, so at the placement (8.6s) the 5s animation has already ended and only its faded last frame is held. |
| MakeMyClip `add_text` (drawtext) | **Fails on Windows**: drive-letter path breaks drawtext option parsing. |
| HyperFrames → harness FFmpeg overlay (`setpts` shift, `eof_action=pass`) | **Works.** Onset/offset within ±1 frame of plan (the ±1 is the template's own zero-opacity first/last frame). |

## Decision

Pass 2 (graphics composite) is a ~30-line **harness-owned FFmpeg step**
(`src/harness/composite.py::composite_ffmpeg`), placing each artifact at an output time computed
from the plan's segment anchor (`plan.graphics_placements`). MakeMyClip remains the structural
provider (pass 1). The MakeMyClip overlay route stays in the codebase as a comparison and should be
revisited if upstream fixes timing or ships multi-track export.

## Consequences

- One extra re-encode of the rough cut when graphics exist (27.6s for a 106s cut). None when there
  are no graphics.
- Graphics timing inherits pass-1 drift (see spike results): placements are computed from the plan,
  so if MakeMyClip's output drifts from the document, overlays drift relative to the content. Either
  pass 1 must be drift-free or pass 2 must place graphics by *observed* segment position (barcode
  or timeline read-back), not planned position.
- Resolve (later) receives rough cut + artifacts as separate layers, which this split already gives.
