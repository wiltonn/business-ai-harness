"""Plan-to-Pixels spike runner.

  python scripts/run_spike.py [--measure-cli-build] [--force-pass1]

Stages (all traced to artifacts/<run>/trace.jsonl):
  A  validate plan
  B  pass 1: plan -> MakeMyClip timeline -> verify doc -> export rough cut (cached by structural hash)
  C  verify rough cut against the plan (duration, per-frame barcode provenance, audio, quality)
  D  graphics: HyperFrames artifact v1 + three compositing routes, each timing-verified
  E  artifact swap v1 -> v2: pass 2 only; prove pass 1 not re-run and plan unchanged
  F  (optional) measure MakeMyClip CLI-per-clip build path for comparison
Results: experiments/video-editing/evaluations/<run>/results.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from harness.composite import composite_ffmpeg, composite_mmc_overlay  # noqa: E402
from harness.graphics import (HarnessTitleCardProvider, HyperFramesGraphicsProvider,  # noqa: E402
                              MakeMyClipTextGraphicsProvider)
from harness.mmc import MakeMyClipExecutionProvider  # noqa: E402
from harness.plan import (graphics_placements, load_plan, output_duration, plan_hash,  # noqa: E402
                          structural_hash, time_map, validate_plan)
from harness.trace import Trace  # noqa: E402
from harness.verify import (check_against_timemap, decode_barcodes, locate_output_time,  # noqa: E402
                            overlay_timing, probe_media, provenance_report, ssim)

EXP = Path(__file__).resolve().parents[1] / "experiments" / "video-editing"
RUN_ID = "spike-001"
FPS = 30


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure-cli-build", action="store_true")
    ap.add_argument("--force-pass1", action="store_true")
    ap.add_argument("--verify-only", action="store_true", help="re-run stages A-C only (pass 1 cached)")
    args = ap.parse_args()

    run_dir = EXP / "artifacts" / RUN_ID
    renders = run_dir / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    fixtures = EXP / "fixtures"
    plan_path = EXP / "plans" / RUN_ID / "edit-plan.json"
    trace = Trace(run_dir / "trace.jsonl", RUN_ID)
    results: dict = {"run_id": RUN_ID, "fixture": "synth-interview-001 (SYNTHETIC)"}
    t_run = time.perf_counter()

    # ---- A: validate --------------------------------------------------------
    plan = load_plan(plan_path)
    rep = validate_plan(plan, fixtures)
    trace.event("verification", check="plan_valid", ok=rep.ok, errors=rep.errors, warnings=rep.warnings,
                plan_hash=plan_hash(plan), structural_hash=structural_hash(plan))
    if not rep.ok:
        raise SystemExit(f"plan invalid: {rep.errors}")
    tm = time_map(plan)
    placements = {p["graphics_request_id"]: p for p in graphics_placements(plan, tm)}
    (run_dir / "time-map.json").write_text(json.dumps(tm, indent=2), encoding="utf-8")
    results["plan"] = {"plan_hash": plan_hash(plan), "structural_hash": structural_hash(plan),
                       "sequence_items": len(tm), "segments_kept": sum(1 for t in tm if t["kind"] == "segment"),
                       "expected_duration_sec": output_duration(tm), "warnings": rep.warnings}

    # ---- B: pass 1 (structure) ---------------------------------------------
    rough = run_pass1(plan, fixtures, run_dir, trace, force=args.force_pass1)
    results["pass1"] = rough

    rough_path = run_dir / rough["render_path"]

    # ---- C: verify rough cut -------------------------------------------------
    results["rough_cut_verification"] = verify_rough_cut(plan, tm, rough_path, fixtures, trace)
    if args.verify_only:
        out = EXP / "evaluations" / RUN_ID / "results.json"
        prev = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        prev.update({k: results[k] for k in ("plan", "pass1", "rough_cut_verification")})
        out.write_text(json.dumps(prev, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in results["rough_cut_verification"].items() if k != "per_segment"}, indent=2))
        return

    # ---- D: graphics --------------------------------------------------------
    req = plan["graphics_requests"][0]
    pl = placements[req["graphics_request_id"]]
    hf = HyperFramesGraphicsProvider(run_dir, trace)
    art_v1 = hf.render(req, version=1, fps=FPS, style_key="v1")
    artifacts = [art_v1]
    routes = {}

    out_ff = renders / "rough-cut+gfx.harness-ffmpeg.v1.mp4"
    secs = composite_ffmpeg(rough_path, [(run_dir / art_v1["render_path"], pl)], out_ff, trace)
    routes["hyperframes+harness_ffmpeg"] = {"output": out_ff.name, "composite_seconds": round(secs, 2),
                                            "timing": overlay_timing(rough_path, out_ff, pl, FPS)}

    mmc_ws = run_dir / "mmc-workspace-pass2"
    mmc_ws.mkdir(parents=True, exist_ok=True)
    out_mo = renders / "rough-cut+gfx.mmc-overlay.v1.mp4"
    secs = composite_mmc_overlay(rough_path, run_dir / art_v1["render_path"], pl, out_mo, mmc_ws, trace)
    routes["hyperframes+mmc_overlay"] = {"output": out_mo.name, "composite_seconds": round(secs, 2),
                                         "timing": overlay_timing(rough_path, out_mo, pl, FPS)}

    mt = MakeMyClipTextGraphicsProvider(run_dir, trace, mmc_ws)
    try:
        art_txt = mt.render_and_composite(req, rough_path, pl, version=1)
        artifacts.append(art_txt)
        out_tx = run_dir / art_txt["render_path"]
        routes["mmc_text(drawtext)"] = {"output": out_tx.name, "composite_seconds": art_txt["render_seconds"],
                                        "timing": overlay_timing(rough_path, out_tx, pl, FPS)}
    except Exception as e:  # noqa: BLE001 — a failed route is a result, not a crash
        err = str(e)
        reason = ("drawtext Windows path escaping (textfile drive colon)"
                  if "Both text and text file" in err else "other")
        routes["mmc_text(drawtext)"] = {"error": reason, "detail": err[-300:]}
        trace.event("provider_failure", provider="makemyclip", step="add_text", reason=reason)
    for name, r in routes.items():
        if "timing" in r:
            trace.event("verification", check="overlay_timing", route=name, **r["timing"])
    results["graphics"] = {"request": req["graphics_request_id"], "placement": pl,
                           "hf_artifact_v1": art_v1, "routes": routes}

    # ---- E: artifact swap ---------------------------------------------------
    before_plan = plan_hash(load_plan(plan_path))
    art_v2 = hf.render(req, version=2, fps=FPS, style_key="v2")
    artifacts.append(art_v2)
    t0 = time.perf_counter()
    again = run_pass1(plan, fixtures, run_dir, trace, force=False)  # must be a cache hit
    out_v2 = renders / "rough-cut+gfx.harness-ffmpeg.v2.mp4"
    composite_ffmpeg(rough_path, [(run_dir / art_v2["render_path"], pl)], out_v2, trace)
    swap_secs = time.perf_counter() - t0
    after_plan = plan_hash(load_plan(plan_path))
    art_v1["status"] = "superseded"
    bindings = {req["graphics_request_id"]: art_v2["artifact_id"]}
    (run_dir / "bindings.json").write_text(json.dumps(bindings, indent=2), encoding="utf-8")
    trace.event("binding", graphics_request_id=req["graphics_request_id"],
                artifact_from=art_v1["artifact_id"], artifact_to=art_v2["artifact_id"],
                reason="style revision (accent colour); no editorial change")
    results["artifact_swap"] = {
        "pass1_cache_hit": again["cache_hit"], "plan_hash_unchanged": before_plan == after_plan,
        "structural_hash": again["structural_hash"], "swap_wall_seconds": round(swap_secs, 2),
        "hf_render_seconds_v2": art_v2["render_seconds"],
        "timing_v2": overlay_timing(rough_path, out_v2, pl, FPS),
    }
    (run_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=2), encoding="utf-8")

    # ---- F: CLI build path (measurement) -----------------------------------
    if args.measure_cli_build:
        ws = run_dir / "mmc-workspace-cli-measure"
        prov = MakeMyClipExecutionProvider(ws, trace, mode="cli")
        t0 = time.perf_counter()
        cm = prov.build_timeline(plan, fixtures)
        cli_secs = time.perf_counter() - t0
        results["build_path_comparison"] = {
            "cli_per_clip_seconds": round(cli_secs, 2),
            "batched_adapter_seconds": rough.get("build_seconds"),
            "cli_doc_matches_plan": prov.verify_document(plan, cm)["ok"],
        }

    results["total_wall_seconds"] = round(time.perf_counter() - t_run, 1)
    out = EXP / "evaluations" / RUN_ID / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    trace.event("run_complete", results_path=str(out.relative_to(EXP)))
    print(json.dumps(results, indent=2))


def run_pass1(plan: dict, fixtures: Path, run_dir: Path, trace: Trace, force: bool) -> dict:
    sh = structural_hash(plan)
    out = run_dir / "renders" / f"rough-cut.{sh}.mp4"
    meta_path = run_dir / f"pass1.{sh}.json"
    if out.exists() and meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["cache_hit"] = True
        trace.event("cache_hit", stage="pass1", structural_hash=sh, output=out.name)
        return meta
    ws = run_dir / "mmc-workspace"
    titles = HarnessTitleCardProvider(run_dir, trace, fps=FPS)
    prov = MakeMyClipExecutionProvider(
        ws, trace, mode="batched",
        title_card_renderer=lambda item: titles.render(item["text"], item["duration_sec"],
                                                       f"sequence[{item['order']}]"))
    t0 = time.perf_counter()
    clip_map = prov.build_timeline(plan, fixtures)
    build_s = time.perf_counter() - t0
    doc = prov.verify_document(plan, clip_map)
    if not doc["ok"]:
        raise SystemExit(f"MakeMyClip doc mismatch: {doc['problems']}")
    export_s, steps = prov.export(out)
    prov.snapshot_state(run_dir / "mmc-state")
    meta = {"structural_hash": sh, "render_path": f"renders/{out.name}", "build_seconds": round(build_s, 2),
            "export_seconds": round(export_s, 2), "export_ffmpeg_steps": steps,
            "clip_map": {str(k): v for k, v in clip_map.items()}, "mmc_doc_check": doc, "cache_hit": False}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    trace.event("artifact", provider="makemyclip", action="export",
                artifact={"artifact_id": f"art_roughcut_{sh}", "type": "rough_cut_render",
                          "render_path": meta["render_path"], **probe_media(out)})
    return meta


def verify_rough_cut(plan: dict, tm: list[dict], rough: Path, fixtures: Path, trace: Trace) -> dict:
    facts = probe_media(rough)
    expected = output_duration(tm)
    codes = decode_barcodes(rough, FPS)
    tmc = check_against_timemap(codes, tm, FPS)
    title = next(t for t in tm if t["kind"] == "title_card")
    title_frames = codes[round(title["out_start"] * FPS): round(title["out_end"] * FPS)]
    src = fixtures / plan["sources"][0]["path"]
    segs = [t for t in tm if t["kind"] == "segment"]
    first, last = segs[0], segs[-1]
    prov_rep = provenance_report(codes, tm, FPS)

    # Quality: same 2s of content, deep in the first vs. last segment (the first is
    # re-encoded most by the fold). Output time is located via the barcode, so
    # drift cannot misalign the comparison.
    def aligned_ssim(seg: dict) -> float | None:
        src_t = seg["source_start"] + 1.0
        out_t = locate_output_time(codes, round(src_t * FPS), FPS)
        return None if out_t is None else round(ssim(src, src_t, rough, out_t, 2.0), 5)

    report = {
        "probe": facts,
        "duration_expected_sec": expected,
        "duration_error_frames": round((facts["duration_sec"] - expected) * FPS, 2),
        "frames_total": len(codes),
        "frames_expected": round(expected * FPS),
        "title_card_frames_without_barcode": sum(1 for c in title_frames if c is None),
        "title_card_frames_expected": len(title_frames),
        "provenance": {k: v for k, v in prov_rep.items() if k != "per_segment"},
        "per_segment": prov_rep["per_segment"],
        "window_check_naive": {k: v for k, v in tmc.items() if k != "details"},
        "ssim_first_segment_vs_source_aligned": aligned_ssim(first),
        "ssim_last_segment_vs_source_aligned": aligned_ssim(last),
    }
    trace.event("verification", check="rough_cut_matches_plan",
                **{k: v for k, v in report.items() if k != "per_segment"})
    return report


if __name__ == "__main__":
    main()
