# CLAUDE.md

Durable instructions for working in this repository.

## What this project is

A research + engineering workspace investigating **business-specific AI harnesses**: whether complex
business tasks become cheaper, more reliable, governable, observable, testable and maintainable when
decomposed into explicit, typed decisions inside domain-specific execution harnesses.

The first executable experiment is an **AI interview rough-cut harness**
(`experiments/video-editing/`). Video is the test bed, not the product.

Read first: `docs/thesis.md`, `docs/architecture/overview.md`,
`docs/architecture/video-provider-relationships.md`, `experiments/video-editing/README.md`.

## Current phase: empirical validation — do not build a product

Do NOT build yet: SaaS UI, auth, cloud infra, billing, microservices, a generic harness DSL, a
generic workflow engine, an elaborate provider router, brand systems, deep Resolve integration, or
forks of MakeMyClip / HyperFrames. Build only what the current approved experiment needs.
Experiments are implemented **only after the user approves them.**

## Design principles

Prefer: **simple · typed · observable · testable · replaceable · version-controlled.**

Avoid: agent magic · opaque prompt chains · unbounded autonomy · unnecessary frameworks ·
business logic hidden inside prompts.

Before adding any step, ask in order:

1. Can deterministic code solve this?
2. Can this be represented as a bounded decision (typed, finite output)?
3. Does this actually require a frontier model?
4. Can an execution provider perform it deterministically?
5. Does this graphic actually improve comprehension?
6. Does this need HyperFrames at all?
7. Does this require human judgment?

## Architectural boundaries (keep separate — never collapse into one "agent")

DOMAIN MODEL · DECISION · DECISION PROVIDER · WORKFLOW · EDIT PLAN · EXECUTION PROVIDER ·
GRAPHICS INTENT · GRAPHICS PROVIDER · POLICY · CONTEXT · OBSERVABILITY · EVALUATION · ARTIFACT

- The harness decides **what** should happen. Providers decide **how**.
- **Decision providers decide** (deterministic rule / Jev / Claude / human).
  Jev is a candidate, not a dependency — code against a provider interface.
- **Execution providers act** (MakeMyClip for structural edits; optional Resolve).
- **Graphics providers generate artifacts** (MakeMyClip drawtext / HyperFrames / Resolve / human).
- **Verification providers** check that expected results occurred.
- **Humans** handle consequential ambiguity; their corrections are recorded as evaluation data.
- Graphics **intent** (semantic, in the edit plan) ≠ graphics **implementation** (provider-specific,
  in an artifact record). Never put HyperFrames HTML/CSS/GSAP details in the semantic plan.
- Editorial decisions must never hide inside timeline commands or graphics prompts.
- Generated media are **versioned artifacts**, replaceable without new editorial decisions.

## Video experiment rules

- MakeMyClip is the primary structural execution provider. Call its pinned CLI
  (`@makemyclip/editor@0.3.0`); do not re-implement what it does.
- HyperFrames is OPTIONAL. Invoke it only when the edit plan contains an explicit graphics request
  whose routing selects it. The rough cut must be complete and usable without it.
- DaVinci Resolve is optional downstream finishing. Never a dependency.
- Every decision is recorded in the trace: input, provider, output, confidence, reason, cost, latency.
- Never commit media (see `.gitignore`). Commit plans, traces, manifests, evaluations.

## Engineering conventions

- Schemas live in `schemas/` and are versioned (`<name>.v<N>.schema.json`). Breaking change ⇒ new
  version file, never an in-place edit of a published version.
- Architecture decisions go in `docs/decisions/NNNN-title.md` (ADR format).
- Research on external tools goes in `docs/research/`, with the commit/version inspected.
- Language/tooling for `src/` is not chosen yet — decide in an ADR when the first experiment is
  approved. Do not add frameworks speculatively.
- Git: local only. Do not add a remote or push. Do not vendor MakeMyClip or HyperFrames.
