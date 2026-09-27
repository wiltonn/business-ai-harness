# Integration: HyperFrames (optional graphics provider)

Status: **not implemented.** Research: `docs/research/hyperframes.md`.

## Contract (planned)

- **Usage:** a stateless renderer.
  `HYPERFRAMES_NO_TELEMETRY=1 npx hyperframes@<pinned> render <template-dir> --format mov --fps <match footage> --variables-file <vars.json> --strict-variables -o <artifact path>`
- **Input:** one approved `graphics_request` (semantic intent), mapped by the adapter to a
  **template id + variables**. The mapping lives here, not in the edit plan.
- **Output:** an artifact record. Media facts (duration, dims, `has_alpha`) are *probed* with
  ffprobe, not taken from the provider.
- **Templates:** our own copies live under `templates/`. Each one declares
  `data-composition-variables` and vendors GSAP. Registry blocks such as `lt-clean-bar` are copied
  here as templates. We do not fork the repo.
- **Skills:** none are installed for the harness. In particular, the harness never uses the
  `/hyperframes` router, `talking-head-recut`, `embedded-captions` or `general-video`.

## Preconditions to verify

1. A full FFmpeg build on PATH (this machine has 4.2; upgrade it or point HyperFrames at a newer
   one).
2. ProRes 4444 alpha renders correctly on Windows.
3. Render time per 5s lower-third at 1080p.
