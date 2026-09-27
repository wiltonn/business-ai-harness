# Relationship: Edit Plan ↔ MakeMyClip ↔ HyperFrames ↔ Resolve

## Default hypothesis (as given)

```
Harness semantic edit plan
  ↓
MakeMyClip structural timeline
  ├── ordinary media
  └── HyperFrames-rendered graphics artifacts
  ↓
optional Resolve timeline
```

## Challenge

The hypothesis assumes MakeMyClip's timeline can hold graphics artifacts on top of the footage.
**It can't today.** MakeMyClip v0.3.0 export is **one populated video track of abutting clips**.
It rejects extra tracks, transforms and gaps (`compile.ts:117-149`). Overlays exist only as
single-file tools (`overlay`, `add_text`, `add_captions`), and those tools bypass the undoable
composition document.

So the literal hypothesis would force one of two things:

- (a) forking MakeMyClip to add compositing, or
- (b) hiding the graphics step inside ad-hoc single-file tool calls that nothing ties back to the
  plan.

Both violate our principles.

## Proposed model: plan-centric, two execution passes

```
                    ┌──────────── SEMANTIC EDIT PLAN (source of truth) ────────────┐
                    │ segments, decisions, sequence, graphics_requests (intent)     │
                    └──────┬───────────────────────────────┬───────────────────────┘
                           │ compile (deterministic)        │ route each approved intent
                           ▼                                ▼
         PASS 1: STRUCTURE (MakeMyClip)          GRAPHICS PROVIDERS (per intent)
         composition.json (A-roll only)          ├─ none
           → rough-cut.mp4                       ├─ MMC drawtext (simple text)
           + segment→output time map             ├─ HyperFrames template → alpha .mov artifact
                           │                     └─ human / Resolve (later)
                           └──────────────┬─────────────────┘
                                          ▼
                    PASS 2: GRAPHICS COMPOSITE (thin, deterministic)
                    overlay each artifact at output time = segment_out_start + anchor
                      → rough-cut+gfx.mp4        (the pass is skipped when there are no graphics)
                                          ▼
                    (optional) RESOLVE: import rough-cut.mp4 + artifacts
                    as separate tracks (e.g. via an EDL/OTIO), not as the burned-in composite
```

Key properties:

1. **The edit plan is the only source of truth.** The MakeMyClip composition, the HyperFrames
   HTML and variables, and any Resolve timeline are **derived and provider-specific**. They are
   stored as provenance and regenerated from the plan, never edited as the master.
2. **Graphics timing is anchored to segments, not absolute time.** The harness computes output time
   from the plan's sequence (after transitions). A re-cut therefore moves graphics automatically,
   and an artifact can be swapped from v1 to v2 without touching editorial decisions.
3. **The structural pass is complete on its own.** If there are no graphics, the result is
   `rough-cut.mp4`. This satisfies "must succeed without HyperFrames or Resolve".
4. **The graphics composite is a separate, replaceable execution step.** Initially it is either
   MakeMyClip's `overlay` tool (if the timing and alpha checks pass) or a ~50-line
   harness-owned FFmpeg overlay step. If MakeMyClip later ships multi-track export, this step folds
   back into pass 1 with no plan changes.
5. **HyperFrames never sees the footage.** It renders short, parametric, transparent clips from
   templates we own. That keeps its render cost small and keeps editorial control out of HF's
   autonomous skills.
6. **Resolve receives layers, not a flattened composite.** Finishing needs separable A-roll and
   graphics. That is a strong reason to keep graphics out of the structural render.

## Why not HyperFrames as the master compositor?

- It could work: HF has real tracks, can host the rough cut as a `<video>` clip, and can place
  graphics as clips.
- It would put the full interview duration through headless Chrome frame capture, which is slow.
- It would move execution ownership into a system whose skills are built to make editorial choices.
- Keep it as a fallback if pass 2 proves insufficient: for example, graphics that must interact
  with the footage, such as captions behind the subject.

## Why not wait for MakeMyClip multi-track?

We don't control its roadmap, and the two-pass split is cheap. It also gives Resolve layered
output, which we want anyway.

## Open

- Should pass 2 use MakeMyClip `overlay` or a harness-owned step? This depends on the verification
  spike.
- Multicam: MakeMyClip has no model for it. Camera selection resolves to per-segment source
  windows. If audio must stay on camera A while video comes from camera B, that is outside
  MakeMyClip's model: pre-mux the pair per segment, or defer to Resolve.
