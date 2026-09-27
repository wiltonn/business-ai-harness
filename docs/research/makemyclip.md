# Research: MakeMyClip Editor

- Repo: https://github.com/MakeMyClip/editor
- Inspected: commit `8673339` (2026-06-18), npm `@makemyclip/editor@0.3.0`
- License: MIT (source); bundled FFmpeg via `ffmpeg-static` is GPL (subprocess-isolated)
- Runtime: Node ≥ 24, TypeScript, Zod 4, execa. No network calls, no telemetry, no embedded model.
- Method: read source directly (shallow clone, not vendored). Nothing was executed yet — every
  claim below is from code/docs and is marked **[verify]** where it needs an empirical check.

## TL;DR for this project

MakeMyClip (MMC) is a good **structural execution provider** for a single-camera interview rough
cut: its composition document is small, Zod-typed, pure-reducer-driven, and fully undoable, and its
export compiler is a pure function from document → FFmpeg plan. But its timeline export is
**v1: one video track of abutting clips, no compositing**. Overlays (text over footage, graphics
over footage, PiP) exist only as *single-file tools* that bypass the composition document. That
single fact shapes where graphics compositing lives in our architecture (see
`docs/architecture/video-provider-relationships.md`).

## 1. Composition / timeline model

`src/timeline/composition.ts` — `CompositionSchema` (version 1):

```
Composition { version: 1, rev, width=1920, height=1080, fps=30, background, tracks[] }
Track       { id, kind: 'video'|'audio', clips[], transitions[], muted }
Clip        = media { mediaId, sourceInSec, sourceOutSec }
            | text  { text, durationSec, style{fontSize,color,background,anchor} }
            | color { color, durationSec }
            + common { id, startSec, transform?, effects[] }
Effect      = adjust | speed | volume | chromaKey | fadeIn | fadeOut
Transition  { afterClipId, kind (12 xfade kinds), durationSec ≤ 10 }
```

- Time is float seconds everywhere. Keyframes/animated params are explicitly out of v1.
- `mediaId = "m_" + sha1(absolutePath)[0:12]` (`schema.ts`) — deterministic per path, *not* per
  content. Moving a file changes its id.
- The media registry is the `ingest` entries of `session.json` (`media-registry.ts`). A composition
  document alone is not renderable; the workspace session log must also contain the ingests.
- `applyOp` is pure: deep clone → mutate → re-parse (always-valid invariant); docs are canonicalized
  so undo returns a byte-identical document (`ops.ts`).

**Ops** (`ops.ts`): `setCanvas, addTrack, removeTrack, addClip, removeClip, moveClip, setTrim,
setDuration, splitClip, addEffect, removeEffect, setTransform, clearTransform, addTransition,
removeTransition`.

**Verbs** (`verbs.ts`) — the agent/UI vocabulary lowered to ops: `add_media, add_text, add_color,
trim, move, split, remove, transition` (+ `set_transform`, CLI-only because export rejects it).

## 2. CLI

Binary `clip` (`src/cli.ts`, `src/cli-timeline.ts`). Two families:

- **Single-file tools** — each reads a file, writes a *new* file, appends to `session.json`:
  `ingest, trim, split, concat, transition, add_text, add_title_card, add_captions, add_audio,
  overlay, transform, adjust, zoom_pan, speed, render, preview, silence_remove, highlight_reel,
  chroma_key, stabilize` + meta `snapshot, undo, inspect, delete`.
- **Timeline** — mutates the composition document:
  `clip timeline new|add-media|add-text|add-color|transition|trim|move|split|remove|show|at|frame|undo|redo|log|export`.
  All output is JSON on stdout, which is convenient for a harness to parse.

Workspace = `$MAKEMYCLIP_WORKSPACE` (default `$TMPDIR/makemyclip-editor`). Files:
`composition.json`, `composition-ops.json`, `session.json`, `snapshots/`, outputs.

## 3. MCP surface

`clip mcp` (stdio; `src/mcp/server.ts`) exposes only 5 tools: `timeline_show`, `timeline_edit`
(batch of verbs = one undoable change), `timeline_undo`, `timeline_redo`, `timeline_export`.
Media paths are confined to the workspace. No single-file tools (overlay, captions, silence removal)
over MCP. Note `docs/ROADMAP.md` still says MCP is out of scope — the roadmap is stale.

## 4. Claude Code skill behaviour

`SKILL.md` (install: `npx skills add MakeMyClip/editor`) triggers on edit/trim/caption/etc. requests
and shells out to `npx -y @makemyclip/editor <tool>`. It steers the agent toward the timeline for
multi-clip assembly and toward `preview` after every mutating edit. It is a *thin instruction layer*;
it contains no editorial logic. **For the harness we should call the CLI (or the library) directly,
not rely on the skill** — the skill is useful for Baseline B ("Claude directly driving MakeMyClip").

## 5. Operation logging

Two logs, by design:

| File | What | Undo model |
|---|---|---|
| `session.json` | append-only `{id, tool, args, result, timestamp}` per single-file tool call; also the media registry | pop last / restore named snapshot |
| `composition-ops.json` | `{forward[], inverse[]}` per applied verb batch, with cursor | standard undo/redo stack; dropped conservatively if `rev` desyncs after a crash |

Both use a `rev` CAS token for optimistic concurrency between agent and browser UI.
Neither log records **why** an op happened — that belongs in our harness trace.

## 6. Undo / redo

Composition: true inverse-op undo/redo (`doc-op-log.ts`, `invertOp`). Single-file tools: snapshot /
pop-last on the session log (outputs are new files, so nothing is destructive).

## 7. Inspect / preview

- `clip timeline show` → tracks, clips, timings, **`exportable` + `blockers`** (a dry-run of the
  compiler). Very useful as a validation gate.
- `clip timeline at <sec>` → which clips are live at T.
- `clip timeline frame <sec>` → JPEG rendered through the real segment path (so preview ≠ export
  divergence is avoided). Encodes the whole clip's segment to grab one frame — slow on long clips.
- `clip preview <file> <sec>` → fast keyframe-accurate JPEG from any file.
- `clip ui` → local browser timeline (127.0.0.1:5573) for human takeover/review.

## 8. Available operations (as relevant to interviews)

| Need | MMC path | Notes |
|---|---|---|
| Probe media | `ingest` | ffprobe JSON: duration, codecs, dims, fps, audio |
| Select answer windows | timeline `add-media <path> <in> <out>` | frame-accurate (re-encoded) |
| Order segments | append order / `move` | |
| Transitions | timeline `transition` | 12 xfade kinds, audio acrossfade |
| Title/section cards | timeline `add-text` / `add-color` | **full-screen cards, not overlays** |
| Burned captions over footage | `add_captions` (single-file) | caller supplies cues; drawtext per cue |
| Lower-third text over footage | `add_text` (single-file) | drawtext box; 9 anchor positions |
| Graphic/video over footage | `overlay` (single-file) | see alpha/timing caveats below |
| Silence removal | `silence_remove` | energy-based; not semantic |
| Audio bed | `add_audio` | mix/replace, no ducking |
| Final encode | `render` | mp4/mov/webm, CRF, preset, maxWidth |

## 9. Strengths for interview editing

- **Typed, inspectable, reversible timeline** — exactly the "execution provider with observable
  state" our architecture wants. A harness can emit verbs/ops and read back `show` to verify.
- **Pure compiler** → we can dry-run (`exportable/blockers`) before spending render time.
- **Frame-accurate A-roll assembly** from one or more long sources via `sourceIn/Out`.
- Local, offline, no API key, MIT, JSON everywhere, zero telemetry.
- Human takeover surface (`clip ui`) on the same document.
- Captions/lower-thirds that are *simple text* need no graphics provider at all.

## 10. Limitations for interview editing

1. **No multi-track compositing in timeline export** (`compile.ts:117-136`). One populated video
   track only; separate audio tracks rejected; non-identity transforms rejected; gaps/overlaps
   rejected. ⇒ Overlays/graphics cannot live in the composition document today. They must be a
   post-pass on the flattened render using single-file tools (outside the undoable doc).
2. **Fold is O(N) sequential re-encodes of a growing file** (`compile.ts:577-630`): each segment
   joins the accumulator via a full `libx264 -crf 23` re-encode. For 40 answer segments the first
   segment is re-encoded ~40× ⇒ **quadratic time and generational quality loss**. **[verify]** —
   this is likely the biggest practical risk for a 30–60 segment interview. Mitigation candidates:
   concat-demuxer of normalized segments (one pass), or a higher-quality intermediate codec.
3. **Overlay alpha**: `overlay` does not force `-c:v libvpx-vp9` on input, so FFmpeg's native VP9
   decoder will likely **drop WebM alpha** **[verify]**. ProRes 4444 `.mov` or PNG sequences should
   keep alpha. This matters for HyperFrames artifacts.
4. **Overlay timing**: `enable=between(t,start,end)` gates visibility but the overlay stream still
   starts at t=0, so an *animated* overlay placed at `start=30s` would be ~30s into its own
   animation when it appears **[verify]**. A `setpts=PTS+start/TB` / `-itsoffset` shift is needed.
5. **No multicam / camera-angle switching model** (single track, no sync). Camera A/B selection must
   be resolved into plain source windows before execution, and there is no audio-from-A/video-from-B.
6. **Stream-copy tools (`trim`, `split`, `concat`, `highlight_reel`) are keyframe-accurate, not
   frame-accurate** — avoid for final interview cuts; use the timeline.
7. **No transcription, diarization, or semantic analysis** (by design — "bring transcript").
8. **Media identity by path**, registry in `session.json`: the harness must manage one workspace per
   run and ingest before editing.
9. `drawtext` styling is minimal (size/colour/box/anchor); no fonts, animation, safe-area control.
10. Pre-1.0; schemas may change. Pin the version (`0.3.0`).
11. Not tuned for >30 min or hundreds of clips (their own README).

## What we should NOT rebuild

FFmpeg arg building, media probing, frame-accurate segment extraction, xfade transitions, drawtext
escaping, undo/redo, the timeline document itself, the human review UI.

## Integration recommendation

- Treat MMC as a **pinned external CLI** (`npx -y @makemyclip/editor@0.3.0 …`), one workspace per
  harness run under `experiments/video-editing/artifacts/<run>/mmc-workspace/`.
- The harness emits **timeline verbs** from the validated edit plan and records the
  plan-op ↔ MMC-op mapping in the trace. Read back `timeline show` and assert it matches the plan.
- Do **not** fork. If limitations 2–4 bite, first try a thin adapter (e.g. harness-owned overlay
  post-pass); upstream a PR only if the fix is general.

## Verified in spike-001 (2026-09-26, Windows)

See `experiments/video-editing/evaluations/spike-001/REPORT.md`. Status of the [verify] items above:

| Item | Verdict |
|---|---|
| Limitation 2: quadratic fold / generational loss | **Confirmed.** 60 cuts: 1207s export (fold 1146s) vs 62s one-pass concat of the same segments. First-clip SSIM 0.979 vs 0.9955 |
| Limitation 3: overlay drops WebM alpha | Not tested; ProRes 4444 used instead |
| Limitation 4: animated overlay timing | **Confirmed.** Overlay invisible at placement; held last frame shown |
| NEW: export drifts 0.5 frame per cut, with duplicated frames | Found by barcode verification |
| NEW: transition after drift truncates real frames | Found (~8 frames in spike-001) |
| NEW: `add-media` fully decodes the source per call | Found. 124s vs 11s for 20 clips; mitigated with `integrations/makemyclip/adapter.mjs` |
| NEW: all drawtext paths fail on Windows (drive-colon escaping) | Found. Root cause and fix verified; title cards pre-rendered by the harness |

Upstream drafts (not filed): `docs/research/makemyclip-upstream-issues.md`.
