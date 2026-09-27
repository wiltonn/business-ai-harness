# Artifact Model

Generated media (graphics renders, rough-cut renders, previews, transcripts) are **artifacts**:
immutable, versioned files with provenance. Editorial decisions reference artifacts by id; swapping
`lower-third-v1.mov` for `lower-third-v2.mov` must not require a new editorial decision.

## Record (draft — see `schemas/edit-plan.v0.schema.json#/$defs/artifact`)

| Field | Meaning |
|---|---|
| `artifact_id` | stable id, e.g. `art_lt_dave_v2` |
| `type` | `graphic_overlay`, `rough_cut_render`, `preview_frame`, `transcript`, `audio_extract`, … |
| `provider` | `makemyclip`, `hyperframes`, `resolve`, `human`, `harness` |
| `source_request_id` | the graphics request / plan version that caused it |
| `created_at` | ISO timestamp |
| `duration_sec`, `width`, `height`, `fps` | media facts (probed, not trusted from provider) |
| `has_alpha` | transparency (probed: pix_fmt contains `a`) |
| `source_files` | inputs + provider project files (e.g. HyperFrames `index.html`), with hashes |
| `render_path` | where the file is (relative to run dir) |
| `content_hash` | sha256 of the rendered file |
| `version` | integer, per `source_request_id` |
| `status` | `pending → rendered → verified → approved / rejected / superseded` |

## Rules

- Artifacts are never overwritten; a new version is a new record + file.
- Media facts are **probed** after render (ffprobe), not copied from provider claims.
- Provider project files (HyperFrames HTML, MMC `composition.json`) are stored as *provenance* of the
  artifact, not as the source of truth for editorial intent.
