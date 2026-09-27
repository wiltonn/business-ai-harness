# ADR 0001 — Bootstrap scope and provider roles

- Status: Accepted (bootstrap)
- Date: 2026-09-26

## Context

We want empirical evidence on whether decomposed, typed-decision harnesses beat unconstrained
agents. The first test bed is interview rough-cutting.

## Decision

1. The repo is a research + experimentation workspace, not a product. No SaaS, auth, infra,
   billing, DSL, workflow engine, or router until evidence justifies them.
2. **MakeMyClip Editor** is the primary structural execution provider, consumed as a pinned external
   CLI (`@makemyclip/editor@0.3.0`). Not forked or vendored.
3. **HyperFrames** is an optional graphics provider, invoked only for explicit graphics requests.
   Not forked or vendored.
4. **DaVinci Resolve** is optional downstream finishing; not a dependency.
5. The **semantic edit plan** (`schemas/edit-plan.v0.schema.json`) is the source of truth for
   editorial intent. Provider documents (MMC composition, HyperFrames HTML, Resolve timeline) are
   derived, provider-specific, and stored as provenance.
6. Decision providers are swappable (rule / Jev / Claude / human) behind a common interface.

## Consequences

- Provider limitations (e.g. MMC single-track export) are handled with thin adapters or separate
  passes, not forks.
- The runtime language for `src/` is deferred to the first approved experiment (ADR 0002).
