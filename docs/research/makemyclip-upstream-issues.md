# MakeMyClip 0.3.0 — upstream issue drafts (NOT filed)

Drafts from spike-001 evidence (Windows 10, Node 24.12, bundled ffmpeg-static 6.1.1). Not posted —
filing is the project owner's call. Repro material: `experiments/video-editing/evaluations/spike-001/`.

## 1. drawtext broken on Windows (all text features)

`quoteFilterArg` (`src/ffmpeg/escape.ts`) wraps paths in single quotes and doubles backslashes. The
filtergraph parser strips that quoting level; drawtext's option parser then splits the value at the
drive colon (`D:`), so ffmpeg reports *"Both text and text file provided"*. Affects timeline text
clips, `add_text`, `add_captions`, `add_title_card`. Verified fix form:
`textfile='D\:/path/to/file.txt'` (forward slashes, colon escaped).

## 2. `ingest`/`add-media` fully decodes the source on every call

`probe()` runs `ffmpeg -i <file> -f null -`, decoding the entire file. On a 3-min 1080p source:
~7s per `timeline add-media`; 20 clips from one source = 124s (vs 11s when ingesting once via the
library). Scales linearly with source length — a 60-min interview would cost minutes per clip.
Suggest: probe without `-f null -` decoding (header-only), and/or cache by path+mtime.

## 3. Timeline export drifts from the document (~0.4 frame per cut)

Hard-cut folds (`concat` filter over per-clip normalized segments) make the output progressively
longer than the document: +8.25 frames over 19 cuts, with 13 duplicated frames inserted; the
drift is visible per segment via burned-in frame barcodes. Likely cause (unconfirmed): per-segment AAC
encoder padding makes each segment's audio slightly longer than its video, and `concat` pads video to
the longer stream. See `evaluations/mmc-scaling/` for how it scales.

## 4. Transitions after drift truncate content

The xfade/acrossfade `offset` is computed from document durations, but the accumulated file is
already longer (issue 3). The fade therefore starts early and cuts real frames from the outgoing
clip: in spike-001, 23 frames were lost around a 0.5s fade where ~15 are expected to be blended —
≈8 frames of the speaker's sentence dropped.

## 5. Export time grows super-linearly with clip count

Each fold step re-encodes the entire accumulated output (`-crf 23`), so total cost is O(N²) in
clip count and the first clip is re-encoded N times (generational loss). See
`evaluations/mmc-scaling/results.json`. A one-pass concat-demuxer join of the already-normalized
segments is a drop-in alternative for hard cuts.

## 6. `overlay` ignores overlay-stream timing

With `startSec > 0`, the overlay input still starts at base t=0 and `enable=between(...)` only gates
visibility, so an animated overlay shows whatever frame it is on at `startSec` (for a clip shorter
than `startSec`: its held last frame). Suggest `setpts=PTS-STARTPTS+start/TB` on the overlay input.
Also: VP9-alpha WebM overlays need `-c:v libvpx-vp9` before `-i` to keep alpha.
