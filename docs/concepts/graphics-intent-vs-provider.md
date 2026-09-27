# Graphics Intent vs Graphics Provider

Mirrors the Decision / Execution provider split.

## Intent (semantic — lives in the edit plan)

> "Identify Dave as the speaker with name and candidate role, when he first appears."

Fields: `graphics_request_id, type, purpose, related_segment_id, anchor (segment-relative time),
duration, content, style_intent, provider_preference, required_or_optional, status, artifact_id`.

Intent says **what and why**, never **how**. No HTML, CSS, GSAP, FFmpeg filters, or template ids.

## Implementation (provider-specific — lives in an artifact record)

The same intent may be realized as:

| Provider | Realization | When |
|---|---|---|
| none | intent rejected / deferred | graphic doesn't improve comprehension |
| MakeMyClip | `drawtext` box, static | plain name/title, speed & determinism matter |
| HyperFrames | animated lower-third, chart, pull quote → rendered alpha video | animation, design, data viz, branding |
| DaVinci Resolve | Fusion title | final-quality finishing by an editor |
| Human designer | hand-made asset | brand-critical, novel |

## Routing (concept only — do not build an elaborate router)

```
GraphicsIntent → router → { none | MakeMyClip | HyperFrames | Resolve | Human }
```

Criteria: complexity · animation required · transparency · branding · chart/data needs · latency ·
cost · determinism · final-quality requirement · **verified data available** (charts must not
display unverified numbers).

For the first experiment the router is a hand-written table or a single bounded decision
(`graphics_provider.v1: GraphicsIntent → none|mmc_text|hyperframes|human`), recorded in the trace.

## Rules

1. A graphics provider **never mutates the semantic plan**. It returns an artifact or a failure.
2. Timing is anchored to a **segment** (`related_segment_id` + offset), not to absolute output time.
   The absolute placement is computed deterministically at composite time, so re-cuts don't
   invalidate graphics.
3. "Needs a graphic?" is itself a decision with a default of **no**.
4. Every graphic must be evaluable on *usefulness* and *distraction* separately.
