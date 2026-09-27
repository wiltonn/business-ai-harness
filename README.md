# Business-Specific AI Harnesses — Research Workspace

Investigating whether complex business tasks become cheaper, more reliable, governable,
observable, testable and maintainable when decomposed into **explicit, typed decisions inside
domain-specific execution harnesses** — and validating that through executable experiments.

> Decision providers decide. Execution providers act. Graphics/artifact providers generate
> specialized artifacts. Verification providers check. Humans handle consequential ambiguity.

## First experiment

AI interview rough-cutting (`experiments/video-editing/`):
MakeMyClip Editor as the structural execution provider, HyperFrames as an *optional* graphics
provider, DaVinci Resolve as *optional* finishing.

## Map

| Path | Contents |
|---|---|
| `CLAUDE.md` | Working rules for agents and humans in this repo |
| `docs/thesis.md` | The claim under test and how it could be falsified |
| `docs/architecture/` | Layers, boundaries, provider relationships |
| `docs/concepts/` | Graphics intent vs provider, artifacts, decisions & learning loop |
| `docs/research/` | Investigations of external tools (MakeMyClip, HyperFrames) |
| `docs/decisions/` | ADRs |
| `docs/product/` | Intentionally empty until there is evidence |
| `experiments/` | Executable experiments (video-editing first) |
| `integrations/` | Thin adapters to external providers (no forks) |
| `schemas/` | Versioned JSON schemas (edit plan v0) |
| `src/`, `tests/`, `scripts/` | Harness code — empty until an experiment is approved |

## Status

Spike-001 (Plan-to-Pixels execution spike) complete — results in
`experiments/video-editing/evaluations/spike-001/REPORT.md`.

## Running

```bash
cd integrations && npm install && cd ..
python -m venv .venv && .venv/Scripts/pip install jsonschema==4.23.0 pytest==8.3.3
.venv/Scripts/python -m pytest
.venv/Scripts/python scripts/make_synthetic_fixture.py   # Windows (uses SAPI TTS)
.venv/Scripts/python scripts/author_spike_plan.py
.venv/Scripts/python scripts/run_spike.py --measure-cli-build
.venv/Scripts/python scripts/mmc_scaling_study.py
```
