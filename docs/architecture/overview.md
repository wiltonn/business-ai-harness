# Architecture Overview

Status: **conceptual**. Nothing here is implemented. This document fixes vocabulary and boundaries
so experiments can be built against them and the boundaries themselves can be tested.

## Layers (video experiment instance)

| # | Layer | Owns | Video instance | Must be… |
|---|---|---|---|---|
| 1 | Deterministic preprocessing | media discovery, probing, audio extraction, transcript parsing, timestamp normalization, segment boundary math, schema/plan validation, artifact tracking | Python/TS code + ffprobe + ASR | pure, unit-tested |
| 2 | Bounded semantic decisions | small typed choices | KEEP/REMOVE, DUPLICATE/DISTINCT, complete thought?, answer quality 1–5, cam A/B, needs graphic?, needs review? | typed, inspectable, independently testable, traced |
| 3 | Foundation-model reasoning | understanding, narrative structure, ambiguity resolution, graphics *intent*, style interpretation, review | Claude | used only where layer 1–2 can't |
| 4 | Structural execution provider | timeline construction, trim, arrange, transitions, basic text, render | `MakeMyClipExecutionProvider` | deterministic, observable, undoable |
| 5 | Graphics provider (optional) | designed/animated visual artifacts | `HyperFramesGraphicsProvider` (also MMC drawtext, Resolve, human) | produces versioned artifacts; never edits the plan |
| 6 | Finishing provider (optional) | colour, mix, multicam, Fusion, polish | DaVinci Resolve | downstream only |
| × | Verification | did the render match the plan? | duration/timing checks, frame probes, AI review, human review | explicit, traced |
| × | Observability & evaluation | trace, metrics, baselines, corrections | JSONL trace + evaluation records | append-only |

## Flow

```
RAW MEDIA
  → [L1] discover/probe → extract audio → transcribe → diarize → segment
  → [L2] bounded decisions per segment (keep, duplicate, complete, quality, needs-graphic…)
  → [L3] Claude: narrative structure, ordering, ambiguous cases, graphics intents
  → EDIT PLAN (versioned JSON, schema-validated)            ← source of truth
  → [L1] validate plan (timing, coverage, references, policy)
  → [L4] MakeMyClip: build timeline from plan → render rough cut
  → [L5] (optional) route graphics intents → provider → artifacts
  → composite artifacts over rough cut (graphics pass)
  → [verify] automated checks → AI review → HUMAN REVIEW
  → (optional) [L6] Resolve finishing
  → corrections → evaluation data → precedent → rules
```

## Core abstractions (conceptual interfaces)

```
DecisionType<I, O>      a named, versioned, typed question (e.g. keep_segment.v1: Segment → KEEP|REMOVE)
DecisionProvider        decide(type, input, context) → Decision{output, confidence, reason, cost, latency}
                        impls: RuleProvider, JevProvider, ClaudeProvider, HumanProvider
ExecutionProvider       apply(plan) → ExecutionResult{provider_state_ref, op_log_ref, outputs}
                        impls: MakeMyClipExecutionProvider, (Resolve), (Human)
GraphicsProvider        render(GraphicsIntent, style) → Artifact
                        impls: MakeMyClipTextProvider, HyperFramesGraphicsProvider, (Resolve), (HumanDesigner)
VerificationProvider    verify(plan, outputs) → Findings
Artifact                versioned generated output + provenance
Trace                   append-only record of every decision, action, artifact, review
```

Deliberately **not** built now: a generic workflow engine, DSL, or router. The first harness is a
straight-line script whose steps call these interfaces directly.

## Critical separations

```
EDITORIAL INTELLIGENCE  (harness: what to show, in what order, why)
GRAPHICS INTENT         (harness: "identify the speaker", "emphasize the tax figure")
EDIT EXECUTION          (MakeMyClip: cut/arrange/render)
GRAPHICS GENERATION     (HyperFrames / MMC drawtext / Resolve / human: how it looks)
FINAL FINISHING         (Resolve / human)
```

See `docs/architecture/video-provider-relationships.md` for how the edit plan, MakeMyClip
composition, HyperFrames composition and Resolve timeline relate.
