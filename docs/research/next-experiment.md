# Next experiment

> **Status: spike-001 executed 2026-09-26.** Results: `experiments/video-editing/evaluations/spike-001/REPORT.md`.
> Ran on a synthetic fixture (no real interview supplied).

## Open architectural questions (top 5)

1. **Can MakeMyClip execute a real interview cut at acceptable cost and quality?**
   - Its export folds segments with sequential full re-encodes, which may give quadratic time and
     generational loss.
   - If this fails, the "structural execution provider" choice changes, or we need an upstream
     fix or an adapter.
2. **Where does graphics compositing live?**
   - Candidates: MakeMyClip `overlay`, a harness-owned FFmpeg pass, or HyperFrames as the
     compositor.
   - This depends on whether alpha and animated-overlay timing survive through `overlay`.
3. **Is the semantic edit plan the right unit of truth?**
   - Can a plan be compiled deterministically into MakeMyClip verbs, and can the result be verified
     back against the plan (plan ↔ `timeline show` ↔ probed render)?
   - Or does the plan need provider concepts that leak?
4. **Which decisions are genuinely bounded?**
   - KEEP/REMOVE and DUPLICATE may need so much context (the question, the narrative, other
     answers) that they are not cheaply answerable by Jev or a small model.
   - This also requires Jev's actual interface, which is not yet documented here.
5. **What is the trace and correction format?**
   - It has to make human review faster than re-editing.
   - It has to feed the precedent → rule ladder.
   - Unverified: whether reviewers actually use "why is this here?" metadata.

## Recommendation: one experiment — "Plan-to-Pixels execution spike"

**Question:** given a *hand-authored* edit plan for one real interview, can the harness
deterministically compile it into MakeMyClip, render it, composite one HyperFrames graphic, and
verify the output against the plan? Also: what does that cost in time and quality?

It deliberately involves **no AI decisions**. It reduces the largest source of uncertainty first:
whether the execution substrate and the plan/artifact boundary work. Everything downstream (Jev,
Claude, baselines) depends on that. If the substrate fails, the architecture changes before we
spend anything on decision providers.

**Scope (small):**

1. One real interview clip (5–15 min, single camera). The fixture manifest is recorded; the media
   is git-ignored.
2. Hand-write `edit-plan.json` (schema v0) with 15–30 kept segments, one title card, one
   transition, and **one** `speaker_id` graphics request.
3. A plan validator (schema plus invariants).
4. Plan → MakeMyClip compiler: emits CLI calls, traces each call, asserts `timeline show` matches
   the plan.
5. Export the rough cut. Measure wall time, output duration vs. plan, and cut accuracy at 3 sampled
   boundaries (frame-grab).
6. Render the lower-third twice, into two artifacts, and composite each over the rough cut at the
   segment-anchored time. Probe alpha. Visually check the edges and whether the animation starts
   on time.
   - Artifact A: MakeMyClip drawtext.
   - Artifact B: a HyperFrames ProRes 4444 template.
7. Swap the artifact from v1 to v2 without touching the plan, and confirm only pass 2 re-runs.

**Success criteria:**

- The render matches the plan (segment count, order, duration within 1 frame × N).
- The export time for 30 segments is acceptable. Target: under 3× realtime.
- The graphic appears at the correct output time with correct alpha.
- Every output traces back to a plan item.

**Deliverables:**

- The compiler and validator code (choice of language via ADR 0002).
- A results note in `experiments/video-editing/evaluations/`.
- An ADR deciding where the graphics pass lives.

**Needs from you:**

- Approval.
- One interview fixture with usage rights.
- Approval to install an upgraded FFmpeg, and HyperFrames' Chrome.
