# Research: HyperFrames

- Repo: https://github.com/heygen-com/hyperframes
- Inspected: commit `640e990` (2026-09-27 UTC), CLI v0.8.79, npm package `hyperframes`
  (monorepo name `@hyperframes/cli`)
- License: Apache-2.0 (the talking-head-recut skill includes MIT vtake-skills content)
- Method: read the source and docs from a shallow clone. Nothing was vendored and nothing was
  executed. **[verify]** marks claims that still need an empirical check on this Windows machine.

## TL;DR for this project

HyperFrames (HF) is a **deterministic HTML-to-video renderer** with a large agent-skill layer
on top. For us, the valuable part is the **renderer used statelessly**: a template with declared
variables, plus `hyperframes render --variables … --format mov`, produces a transparent
ProRes 4444 clip. That clip becomes a versioned artifact which the harness composites over the
MakeMyClip rough cut.

The skill layer is where the risk is. The `/hyperframes` router, `talking-head-recut`,
`embedded-captions` and `general-video` each want to own the edit: they embed the footage,
choose timing and layout, and render the finished MP4. **Do not use them inside the harness.**
They are fine as a baseline or for inspiration.

## 1. Composition model

- **A composition is HTML.**
  - The root is `<div data-composition-id data-width data-height data-duration>`.
  - Timed children carry `class="clip"`, `data-start`, `data-duration` and `data-track-index`.
  - Tracks are only display lanes in Studio.
- **Sub-compositions** mount through `data-composition-src`, with per-instance
  `data-variable-values`.
- **Variables** are declared in `data-composition-variables` on `<html>`.
  - Types: string, number, color, boolean, enum.
  - Binding: `data-var-text` / `data-var-src`, the `--{id}` CSS custom properties, or
    `window.__hyperframes.getVariables()`.
  - The root **duration is fixed** and variables cannot change it.
- **Determinism:**
  - One paused GSAP timeline per composition, and the engine seeks it frame by frame
    (`time = floor(frame)/fps`).
  - `Date.now`, unseeded random, render-time fetches and infinite repeats are banned.
  - Pixels can still vary across Chrome, font and GPU versions. `--docker` pins them.
- **Animation runtimes:** GSAP by default. Adapters exist for Lottie, Three.js, Anime.js,
  CSS keyframes, WAAPI and TypeGPU.

## 2. CLI

- **Invocation:** `npx hyperframes <cmd>`. Requires Node ≥ 22 and FFmpeg on PATH.
- **Commands:**
  - Authoring: `init`, `add`, `catalog`
  - Checking: `lint`, `check`, `snapshot`, `compare`
  - Viewing: `preview`
  - Rendering: `render` (single or `--batch`)
  - Local media tools: `transcribe`, `tts`, `remove-background`
  - Maintenance: `doctor`, `browser`, `telemetry`
  - Hosted rendering: `cloud`, `lambda`, `cloudrun`
  - Many more
- **Render flags we need:**

```
npx hyperframes render <projectDir> \
  --format mov                      # ProRes 4444 + alpha (or webm = VP9 alpha, png-sequence)
  --fps 30000/1001                  # must match the footage; default 30
  --variables-file vars.json        # parametric content; --strict-variables to reject unknowns
  --quiet -o graphics/lt_dave_v1.mov
```

- **Batch rendering:** `--batch rows.json --output "renders/{name}.mov"` writes a `manifest.json`
  with per-row variables, status and timings.
- **Quality:** `-q draft|standard|high`, or `--crf`. The CRF option does not apply to MOV, which
  uses a fixed ProRes profile.

## 3. Skills: all 21 and the minimal set

- **Install options:**
  - `npx hyperframes skills update [<name>]`
  - `npx skills add heygen-com/hyperframes --skill <name>`
  - Note: `init` refreshes the installed skills unless `HYPERFRAMES_SKIP_SKILLS=1` is set.
- **Router:** `hyperframes`. It runs an intent interview, writes `BRIEF.md` and routes to a
  workflow.
- **Domain skills:** `hyperframes-core`, `-animation`, `-keyframes`, `-creative`, `-audio`, `-cli`,
  `-registry`, `-studio`, `media-use`, `figma`.
- **Workflows:** `motion-graphics`, `talking-head-recut`, `embedded-captions`, `general-video`,
  `product-launch-video`, `faceless-explainer`, `pr-to-video`, `music-to-video`, `slideshow`,
  `remotion-to-hyperframes`.

**The workflows we were asked about:**

| Skill | What it does | Input to output | Owns the edit? | Use in harness? |
|---|---|---|---|---|
| `/hyperframes` | Mandatory router: intent interview, `BRIEF.md`, routes to a workflow | request to workflow | Yes (it routes) | **No** |
| `/motion-graphics` | Short (under 10s, up to ~30s) unnarrated graphic: kinetic type, stat, chart, **lower-third**, map, callout. Lower-thirds default to an alpha overlay | brief to `index.html` to mp4/webm/mov | No, self-contained | **Later, optional**: for *designing new templates*, not per-run rendering |
| `/talking-head-recut` | Whisper transcript, then its own storyboard (it picks card count and timing, min 5 cards), then re-encodes the source, can reposition the speaker (split/stack/pip), then renders the final MP4 with footage embedded | mp4 to final mp4 | **Yes** | **No.** Possible comparison baseline only |
| `/embedded-captions` | Subject matting (u2net), WhisperX or whisper.cpp, captions behind the subject, final composite. Bash scripts. Refuses multi-cut footage | single-shot mp4 to final mp4 | **Yes** (final composite) | **No** for the rough cut. Maybe later as a finishing treatment on one shot |
| `/general-video` | Fallback for multi-scene pieces. Includes cut, trim, splice, reorder and crossfade recipes | brief/footage to video | **Yes**, and it overlaps MakeMyClip | **No** |

**Minimal useful set:** *none installed into the harness runtime.* The harness calls the CLI
directly with hand-owned templates.

For a human or agent *authoring* templates in a separate session, install only `hyperframes-core`,
`hyperframes-cli` and `hyperframes-registry`, plus `hyperframes-animation` if motion work is needed.
Add `motion-graphics` only if we want agent-designed templates.

## 4. Workflow dependencies (summary)

| Workflow | Dependencies |
|---|---|
| motion-graphics | CLI + FFmpeg + Chrome. Optional Gemini/search keys (only for asset sourcing). Lists macOS/Linux as prerequisites |
| talking-head-recut | ffmpeg, ffprobe, local Whisper. No API key |
| embedded-captions | ONNX u2net (~168 MB), WhisperX via `uvx` or whisper.cpp, **bash** |

- **Local media commands:** `transcribe` (Parakeet or whisper.cpp; whisper.cpp is awkward on
  Windows), `tts` (Kokoro, local), `remove-background` (u2net, local).
- **HeyGen services:** only `cloud render` (a HeyGen API key plus paid credits) and some optional
  `media-use` providers.

## 5. Rendering architecture

- **Packages:**
  - `core`: parser, linter, runtime, adapters
  - `engine`: Puppeteer + FFmpeg capture and encode
  - `producer`: compile, capture, encode, audio mix. Also provides a render server and a
    distributed chunk API.
  - Also: `studio`, `player`, `sdk`, `aws-lambda`, `gcp-cloud-run`
- **Capture:**
  - Uses a pinned `chrome-headless-shell` (152.x), auto-downloaded to `~/.cache/puppeteer`.
  - Frames are captured via BeginFrame, drawElement or screenshots and piped into FFmpeg.
- **Compile step:** CDN `<script src>` files (such as GSAP from jsdelivr) are **downloaded and
  inlined at compile time**. Hermetic or offline renders therefore need vendored scripts.
- **Where it can run:** locally, in Docker, on HeyGen cloud, AWS Lambda, Cloud Run, or k8s.
- **Programmatic use:** `@hyperframes/producer` exports
  `createRenderJob({…, variables})` + `executeRenderJob(job, dir, out)`.

## 6. Transparent overlay support

| Format | Codec / pix_fmt | Notes |
|---|---|---|
| `mov` | ProRes 4444 `prores_ks`, `yuva444p10le` | **Recommended for us.** FFmpeg's native decoder keeps the alpha. Large files |
| `webm` | VP9 `yuva420p`, `alpha_mode=1` | The consumer **must** put `-c:v libvpx-vp9` before `-i`, or the alpha is dropped. MakeMyClip's `overlay` does not do this |
| `png-sequence` | RGBA PNGs (+ `audio.m4a`) | Robust. Many files |
| `gif` | 1-bit alpha | Not useful |

- **Caveats:**
  - The root, `html` and `body` must stay unpainted, or the background renders opaque.
  - Alpha output forces the slower screenshot capture and SDR.
  - VP9 encoding is CPU-heavy.
- **Windows:** the Windows render canary only exercises MP4. **Alpha output on Windows is
  unverified.** **[verify]**

## 7. Artifacts and outputs

- **Output files:** video files or a PNG directory.
- **Provenance tags:** container tags `hyperframes_renderer` and `hyperframes_version`.
- **Manifests:** `--batch` writes `manifest.json`. A single render writes **no per-render
  manifest** of placement, timing or alpha, so our artifact record (probed with ffprobe) must
  carry that.

## 8. Setup and runtime requirements

- **Node:** ≥ 22. This machine has Node 24.12.
- **Chrome:** auto-downloaded. Override with `HYPERFRAMES_BROWSER_PATH`.
- **FFmpeg:** must be on PATH. The Windows CI asserts a full GPL build (libx264, libx265,
  libvpx-vp9, prores_ks). **This machine's PATH ffmpeg is 4.2 (2019).** It must be upgraded or
  overridden before trusting alpha output. **[verify]**
- **Telemetry:** anonymous PostHog, **on by default**. Set `HYPERFRAMES_NO_TELEMETRY=1` (or
  `DO_NOT_TRACK=1`) in every harness invocation. The CLI also runs update and skill checks over
  the network.
- **API keys:** none for local rendering.

## 9. Integration options with MakeMyClip

| Option | Description | Verdict |
|---|---|---|
| A | HF renders short alpha clips (MOV). The harness composites them over the flattened MMC rough cut, in output-time coordinates derived from the plan | **Recommended** |
| B | Composite through MMC's single-file `overlay` tool | Viable only if animated-overlay timing works (the overlay stream starts at t=0 of the base) **[verify]**. MOV alpha should work. WebM would need a patch |
| C | HF as the final compositor: the rough-cut mp4 becomes a `<video>` clip, with graphics as sibling clips | Clean compositing model, but a Chrome frame capture over the **full interview length** is slow. Also moves execution ownership into HF |
| D | MMC timeline holds the graphics directly | **Not possible today.** MMC export is single-track |

## 10. Registry blocks we can reuse (1920×1080)

- **Lower-thirds:** `lt-clean-bar` (interview/podcast style), `lt-kicker-name`,
  `lt-accent-underline`, `lt-stack-bars`, `lower-third-bild` (has variables)
- **Charts:** `data-chart`, `mk-line-graph`, `mk-progress-stat`, `bar-chart-race`
  (variable-driven)
- **Titles and callouts:** `hw-title`, `mk-callout-highlight`
- **Caption components:** `caption-pill-karaoke`, `caption-editorial-emphasis`

**Caveat:** most lower-thirds (e.g. `lt-clean-bar`) have **hard-coded text and no declared
variables**, and they load GSAP from a CDN. We would copy one into our own template
(`integrations/hyperframes/templates/`), add variables and vendor GSAP. That copy is a template,
not a fork.

## 11. Strengths

- Deterministic, seekable, parametric rendering of designed motion graphics.
- Real alpha output (ProRes 4444).
- Batch rendering with a manifest.
- Large block registry.
- Programmatic API.
- Apache-2.0.
- No API keys needed locally.

## 12. Limitations

- **Render cost:** headless Chrome per frame, roughly 10–25s per 300 frames at 1080p, and slower
  with alpha. Keep overlays short (a few seconds each), never full-length.
- **Windows:** narrower support. Alpha paths are not tested in CI, and the workflow skills assume
  bash and macOS/Linux.
- **Network use by default:** telemetry, CDN inlining, update checks.
- **Durations** are fixed per template.
- **Frame rate** must be set explicitly (for example 29.97 footage).
- **Skill layer:** an opinionated, autonomous agent layer that can silently take over editorial
  decisions.

## 13. Setup to test before relying on it

1. Upgrade or override FFmpeg (a full build with prores_ks and libvpx-vp9).
2. `HYPERFRAMES_NO_TELEMETRY=1 npx hyperframes doctor`
3. Render one parametric lower-third to MOV. Probe it for `yuva444p10le`. Composite it over footage
   and check the edges and the timing.

## 14. What should remain outside HyperFrames

- **Editorial decisions:** what to cut, order, emphasize, and whether a graphic is needed at all.
- **The semantic edit plan and the graphics intent.**
- **Structural editing:** cutting, trimming, arranging, transitions. That is MakeMyClip's job.
- **Transcription and diarization for the harness.** These go through our own L1 pipeline, not
  `talking-head-recut`.
- **Overlay placement timing:** the harness computes it from segment anchors.
- **Verification of data shown in charts:** only verified figures with a source citation.
- **Final colour and mix:** Resolve or a human.
