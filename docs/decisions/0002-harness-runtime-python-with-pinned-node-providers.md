# ADR 0002 — Harness runtime: Python; providers as pinned Node packages

- Status: Accepted (spike-001)
- Date: 2026-09-26

## Context

The first experiment needs a harness language. Providers (MakeMyClip, HyperFrames) are Node
packages. Upcoming layers (ASR, diarization, embeddings, decision-provider evaluation) are
Python-heavy ecosystems.

## Decision

- Harness code (`src/harness/`): **Python 3.12**, stdlib + `jsonschema` + `pytest`. No framework.
- Providers: pinned exact versions in `integrations/package.json`
  (`@makemyclip/editor@0.3.0`, `hyperframes@0.8.79`, `gsap@3.13.0`, `ffprobe-static@3.1.0`),
  invoked as subprocesses. FFmpeg is the `ffmpeg-static` 6.1.1 binary bundled with MakeMyClip,
  used by every step (harness, MakeMyClip, HyperFrames) via PATH/env — never the system FFmpeg.
- Where a provider's CLI is inadequate, a **thin Node adapter over the provider's published
  library API** is allowed (`integrations/makemyclip/adapter.mjs`), provided every mutation still
  goes through the provider's own reducer/op log. This is not a fork.

## Consequences

- Two runtimes (Python + Node). Accepted: the boundary coincides with the harness/provider
  boundary we want anyway.
- Provider upgrades are explicit version bumps, re-run against the spike's verification suite.
