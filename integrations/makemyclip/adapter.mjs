// Thin adapter over MakeMyClip's PUBLISHED library API (@makemyclip/editor@0.3.0).
// Not a fork: every edit still goes through MakeMyClip's own reducer, op log
// (undo/redo) and session log. Exists because the CLI's `timeline add-media`
// re-probes (fully decodes) the source on every call — see
// docs/research/makemyclip.md and the spike results.
//
// Usage (MAKEMYCLIP_WORKSPACE must be set by the caller):
//   node adapter.mjs build <job.json>           -> {clipIds:[...], ingests:{path:mediaId}, rev}
//   node adapter.mjs profile-export <out.mp4>   -> per-step timings of MakeMyClip's own export plan,
//                                                  plus a single-pass concat alternative (measurement only)
import { readFile, writeFile, unlink } from 'node:fs/promises';
import { resolve } from 'node:path';
import {
  appendOp,
  buildMediaMap,
  compileTimeline,
  emptyComposition,
  ingest,
  makeClipId,
  mediaClip,
  mutateComposition,
  readComposition,
  resetComposition,
  runFfmpeg,
  textClip,
  videoTrack,
} from '@makemyclip/editor';

const TRACK = 'v0';

async function build(jobPath) {
  const job = JSON.parse(await readFile(jobPath, 'utf8'));
  await resetComposition(emptyComposition(job.canvas));

  // Ingest each distinct source ONCE (MakeMyClip's own ingest + session log entry).
  const ingests = {};
  for (const path of [...new Set(job.items.filter((i) => i.kind === 'media').map((i) => i.path))]) {
    const t0 = Date.now();
    const result = await ingest({ path });
    await appendOp({ tool: 'ingest', args: { path }, result });
    ingests[path] = { mediaId: result.mediaId, durationSec: result.ref.durationSec, ms: Date.now() - t0 };
  }

  const ops = [{ op: 'addTrack', track: videoTrack({ id: TRACK }) }];
  const clipIds = [];
  let cursor = 0;
  let prev = null;
  for (const item of job.items) {
    const id = makeClipId();
    let clip;
    if (item.kind === 'media') {
      clip = mediaClip({
        id,
        mediaId: ingests[item.path].mediaId,
        sourceInSec: item.inSec,
        sourceOutSec: item.outSec,
        startSec: cursor,
      });
      cursor += item.outSec - item.inSec;
    } else if (item.kind === 'text') {
      clip = textClip({ id, text: item.text, durationSec: item.durationSec, startSec: cursor, style: item.style ?? {} });
      cursor += item.durationSec;
    } else {
      throw new Error(`unsupported item kind ${item.kind}`);
    }
    ops.push({ op: 'addClip', trackId: TRACK, clip });
    if (item.transitionIn && prev) {
      ops.push({
        op: 'addTransition',
        trackId: TRACK,
        transition: { afterClipId: prev, kind: item.transitionIn.kind, durationSec: item.transitionIn.durationSec },
      });
    }
    clipIds.push(id);
    prev = id;
  }
  // One atomic, undoable batch through MakeMyClip's reducer.
  const doc = await mutateComposition(ops);
  process.stdout.write(`${JSON.stringify({ clipIds, ingests, rev: doc.rev, ops: ops.length })}\n`);
}

async function profileExport(output) {
  const ws = process.env.MAKEMYCLIP_WORKSPACE;
  const comp = await readComposition();
  const media = await buildMediaMap();
  const plan = compileTimeline(comp, { media, dir: ws, output: resolve(output) });
  const timings = [];
  const intermediates = [];
  const t0 = Date.now();
  for (const step of plan.steps) {
    for (const tf of step.textFiles) await writeFile(tf.path, tf.content, 'utf8');
    const s = Date.now();
    await runFfmpeg(step.args);
    timings.push({ label: step.label, ms: Date.now() - s });
    if (step.output !== plan.output) intermediates.push(step.output);
  }
  const totalMs = Date.now() - t0;

  // Alternative (measurement only): one-pass concat-demuxer join of the SAME
  // normalized segments. Valid only for hard cuts, so report it alongside.
  const segs = plan.steps.filter((s) => s.label.startsWith('segment:')).map((s) => s.output);
  const listPath = resolve(ws, 'profile-concat.txt');
  await writeFile(listPath, segs.map((p) => `file '${p.replaceAll('\\', '/')}'`).join('\n'), 'utf8');
  const altOut = output.replace(/\.mp4$/, '.concat-alt.mp4');
  const a0 = Date.now();
  await runFfmpeg(['-y', '-f', 'concat', '-safe', '0', '-i', listPath, '-c', 'copy', altOut]);
  const concatMs = Date.now() - a0;
  const segmentMs = timings.filter((t) => t.label.startsWith('segment:')).reduce((a, t) => a + t.ms, 0);
  for (const p of [...intermediates, listPath]) await unlink(p).catch(() => undefined);
  process.stdout.write(
    `${JSON.stringify({ totalMs, segmentMs, foldMs: totalMs - segmentMs, steps: timings, alternative: { output: altOut, concatMs, totalMs: segmentMs + concatMs } })}\n`,
  );
}

const [cmd, arg] = process.argv.slice(2);
if (cmd === 'build') await build(arg);
else if (cmd === 'profile-export') await profileExport(arg);
else {
  process.stderr.write('usage: adapter.mjs build <job.json> | profile-export <out.mp4>\n');
  process.exit(2);
}
