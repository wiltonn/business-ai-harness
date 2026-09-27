# Integration: MakeMyClip (structural execution provider)

Status: **not implemented.** Research: `docs/research/makemyclip.md`.

## Contract (planned)

- Consume via pinned CLI: `npx -y @makemyclip/editor@0.3.0 …` (or a local `npm i` in this folder
  once a runtime is chosen). **No fork, no vendoring.**
- One MMC workspace per harness run: `MAKEMYCLIP_WORKSPACE=experiments/video-editing/artifacts/<run>/mmc-workspace`.
- Input: a validated edit plan (`schemas/edit-plan.v0.schema.json`).
- Adapter steps: `timeline new --width --height --fps` → `add-media <src> <in> <out>` per sequence
  item → `add-text`/`add-color` for title cards → `transition` → `timeline show` (assert
  `exportable`, assert clip windows equal the plan) → `timeline export`.
- Record in the trace: each CLI call, its JSON output, plan-item ↔ MMC clip id mapping, MMC `rev`,
  and copies of `composition.json` + `composition-ops.json`.

## Known gaps to test before relying on it

1. Export time/quality with 20–60 segments (sequential re-encode fold).
2. `overlay` with ProRes-4444 / WebM-VP9 alpha inputs.
3. `overlay` timing of animated inputs starting at t>0.
