# Decisions and the Learning Loop

## Decision types

A decision type is a named, versioned, typed question with a finite (or tightly bounded) output.

| Decision type (draft) | Input | Output |
|---|---|---|
| `keep_segment.v1` | segment + question + context | `KEEP` \| `REMOVE` \| `REVIEW` |
| `duplicate_of.v1` | segment pair | `DUPLICATE` \| `DISTINCT` (+ which is better) |
| `complete_thought.v1` | segment | `COMPLETE` \| `INCOMPLETE` |
| `relevance.v1` | segment + topic | `RELEVANT` \| `IRRELEVANT` |
| `answer_quality.v1` | segment | integer 1–5 |
| `camera_select.v1` | segment + available angles | `A` \| `B` |
| `needs_graphic.v1` | segment | `NO_GRAPHIC` \| `GRAPHIC(type)` |
| `graphics_provider.v1` | graphics intent | `none` \| `mmc_text` \| `hyperframes` \| `human` |
| `review_required.v1` | any decision | `ACCEPT` \| `REVIEW` |

Each decision record in the trace: `decision_id, type, input_ref, provider, provider_version,
output, confidence, reason, cost, latency_ms, created_at, overridden_by?`.

## Providers

`rule` (deterministic) → `jev` (bounded decision provider, candidate) → `claude` → `human`.
The same decision type can be answered by several providers for comparison.
Jev's concrete API is not yet documented in this repo — see open questions.

## Learning loop

```
UNKNOWN → HUMAN DECISION → PRECEDENT → REPEATED PRECEDENT
        → PROPOSED RULE → VALIDATED RULE → DETERMINISTIC KNOWLEDGE
```

Human corrections (cuts, segment selection, camera, graphics placement/necessity) are captured as
`correction` records: `{target_ref, before, after, reason, reviewer, created_at}`. They become:
evaluation labels now; precedent for providers later; candidate rules only when repeated and validated.
