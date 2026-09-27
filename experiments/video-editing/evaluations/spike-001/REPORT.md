# Spike-001 — Plan-to-Pixels execution spike: results

- Date: 2026-09-26/27. Machine: Windows 10, i7-6700K (8 threads), 16 GB, no GPU encode.
- Providers: MakeMyClip `@makemyclip/editor@0.3.0`, HyperFrames `0.8.79`, FFmpeg 6.1.1 (ffmpeg-static).
- Raw data: `results.json` (this folder), `../mmc-scaling/results.json`, trace at
  `../../artifacts/spike-001/trace.jsonl`, MakeMyClip state at `../../artifacts/spike-001/mmc-state/`.
- Reproduce: `python scripts/make_synthetic_fixture.py && python scripts/author_spike_plan.py &&
  python scripts/run_spike.py --measure-cli-build && python scripts/mmc_scaling_study.py`

## Fixture caveat (read first)

No real interview was supplied, so this ran on a **synthetic** 3m04s interview
(`fixtures/synth-interview-001.*`): Windows TTS speech in two voices, over a test pattern with a
**burned-in frame-number barcode**. That makes cut accuracy *measurable to the frame*, which a real
interview can't offer. But it says nothing about editorial quality, real-footage codecs (e.g. 29.97
fps, long-GOP camera files, variable frame rate) or ASR. The execution findings below are
content-independent; re-run on real footage before relying on the absolute timings.

## Question

Can a hand-authored, schema-validated edit plan be compiled deterministically into MakeMyClip,
rendered, given one HyperFrames graphic, and verified against the plan, at acceptable cost?

## Answer in one paragraph

**Mostly yes, and the verification layer earned its keep.**
- **Plan → MakeMyClip document:** deterministic and verifiably exact.
- **Render:** does *not* faithfully realize the document. Every cut adds 0.5 frame of drift, a
  transition then truncates real content to absorb the accumulated drift, and export time is
  quadratic in the number of cuts.
- **Graphics:** the semantic-intent → HyperFrames artifact → harness composite path works to ±1
  frame, and artifacts can be swapped without touching the plan or re-cutting.
- **MakeMyClip's own graphics routes fail:** `overlay` has a timing bug, and drawtext is broken on
  Windows.

None of these problems would have surfaced from an agent looking at the output. They surfaced because
the plan made an exact, checkable prediction.

## Results

### Pass 1: plan → MakeMyClip → rough cut

| Check | Result |
|---|---|
| Plan valid (schema + 9 invariants) | ✅ 19 segments kept of 30; 20 sequence items; cold open out of source order; 1 fade |
| MakeMyClip document == plan (clip order, source windows to 1e-4 s, transition count) | ✅ exact |
| Timeline build: CLI, one call per clip | 124.2s (each `add-media` fully decodes the 3-min source to probe it) |
| Timeline build: batched adapter (1 ingest + 1 atomic op batch via MakeMyClip library) | **11.0s**, same verified document |
| Export time (106s output, 39 FFmpeg steps) | 336s (**3.2× realtime**) |
| Output duration vs plan | **+8.25 frames** (106.475s vs 106.200s) |
| Source frames present / foreign frames | all planned frames present except around the fade; 0 foreign |
| Drift (actual − planned output position of each segment) | 0 → +7 frames, growing ~0.4 frame per cut |
| Duplicated output frames | 13 (padding that produces the drift) |
| Transition | 23 frames lost around a 0.5s fade where ~15 are blended: **~8 real frames truncated.** The fade offset is computed from document time while the file has already drifted |
| Title card | ✅ 90/90 frames, as a pre-rendered media clip (MakeMyClip text clips fail on Windows, see below) |

### Export scaling: hard cuts, N × 2.5s clips (`mmc-scaling`)

| N | MMC export | fold part | concat alternative* | MMC drift / dups | alt drift / dups | first-clip SSIM MMC / alt |
|---|---|---|---|---|---|---|
| 10 | 58s | 46s | 12.6s | 4 / 5 | 1 / 1 | 0.9884 / 0.9955 |
| 20 | 184s | 161s | 23.6s | 9 / 10 | 1 / 1 | 0.9854 / 0.9955 |
| 40 | 569s | 527s | 42.1s | 20 / 20 | 1 / 1 | 0.9820 / 0.9955 |
| 60 | 1207s | 1146s | 62.3s | 30 / 31 | 1 / 1 | 0.9792 / 0.9955 |

\* The alternative uses MakeMyClip's own normalized segments, joined with one concat-demuxer pass.
It is a measurement, not an adopted path. At N=60 both routes show 30 missing frames; that is a
fixture artefact (the last window ran past the 3-min source), not a provider fault.

- **Fold time is quadratic.** It is ≈ 0.25 s per second of accumulated output, re-encoded at every
  fold.
  - Extrapolated to a realistic 10-min cut of 80 segments: **≈ 1.7 h export and ≈ 40 frames (1.3s)
    of drift.** The concat route: ≈ 4–5 min, constant 1-frame offset.
- **Drift is exactly 0.5 frame per cut.** It is systematic, not random.
- **Generational loss is real but modest:** first-clip SSIM falls 0.988 → 0.979 over 60 folds,
  against 0.9955 for a single pass.

### Pass 2: graphics (one `speaker_id` intent → placed at 8.6–13.6s from its segment anchor)

| Route | Works? | Timing vs plan | Cost |
|---|---|---|---|
| HyperFrames template (ProRes 4444, `yuva444p10le`) → **harness FFmpeg overlay** | ✅ | onset +1 / offset −1 frame (the template's first and last frames are at 0 opacity by design) | HF render 24–30s; composite 27.6s |
| HyperFrames artifact → **MakeMyClip `overlay`** | ❌ invisible | overlay stream starts at base t=0, so only the held, faded last frame shows (peak diff 5.9 vs 55) | 29.8s |
| **MakeMyClip `add_text`** drawtext lower-third | ❌ error on Windows | n/a | n/a |

### Artifact swap: v1 (gold accent) → v2 (blue accent)

- Pass 1 cache hit (structural hash unchanged), and the plan file hash is unchanged.
- Binding recorded in `bindings.json`, with a trace `binding` event giving the reason.
- Wall time 27.9s (composite only) + 23.8s for the HF render. The v2 timing is identical to v1.

## What this means for the architecture

1. **The semantic plan works as the single source of truth.** It compiled deterministically. The
   provider document could be checked back against it exactly. Graphics timing derived from segment
   anchors followed a re-cut automatically (unit-tested). The graphics swap needed no editorial
   change.
2. **"Execution provider acted" ≠ "expected result occurred".** MakeMyClip's document was exactly
   right and its render was still wrong in three independent ways. Verification must check the
   *output*, not the provider's state. The barcode fixture is a cheap, reusable way to do that.
   Real footage needs another method, such as audio cross-correlation against source windows.
3. **MakeMyClip is a good *document and edit* layer but a weak *renderer* for interview-length
   work.**
   - Keep: the document, ops, undo/redo and UI.
   - Don't rely on: 0.3.0 export for >~15 cuts, or on any MakeMyClip text/overlay path on Windows.
4. **HyperFrames is a good stateless graphics provider** for this use: parametric template, alpha
   MOV, Windows-OK, ~25s per 5s lower-third, no HyperFrames skills used, telemetry off.
5. **Compositing belongs to the harness for now** (ADR 0003). Graphics placement must account for
   pass-1 drift, or pass 1 must be drift-free.

## Decisions taken during the spike

- ADR 0002: Python harness; providers pinned as Node packages; thin adapters over published APIs
  allowed.
- ADR 0003: graphics composite is a harness-owned pass.
- Title cards pre-rendered by a harness provider (`HarnessTitleCardProvider`) because MakeMyClip
  drawtext fails on Windows. This is an example of intent→provider routing working as designed.
- Graphics→artifact bindings live **outside** the plan (`bindings.json`) so swaps don't change the
  plan hash. Proposal for schema v1: drop `graphics_requests[].artifact_id` and `artifacts[]` from
  the plan.

## Not tested / open

- Real camera footage, 29.97/VFR sources, multicam.
- Audio/video sync inside the drifted output. Duplicated frames suggest video is padded to audio,
  but A/V offset was not measured.
- Whether a one-pass export (concat demuxer + separate xfade handling) should be proposed upstream,
  or implemented as a harness-side "render provider" over MakeMyClip's own segment plan.
- Upstream issue drafts: `docs/research/makemyclip-upstream-issues.md` (not filed).
