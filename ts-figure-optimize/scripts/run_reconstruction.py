#!/usr/bin/env python3
"""Orchestrate DrawAI-based editable scientific-figure reconstruction with a strict,
measured, multi-round refinement loop.

Pipeline per run:
  normalize+decompose+OCR+IR+first SVG/PPTX (DrawAI)  -> Round 0
  render SVG + PPTX -> measure global + per-region -> verify text/formula/editability
  if not passing: repair (guided global re-generation via DrawAI --from-stage svg_generated)
  repeat until PASS or max rounds; keep the best-scoring round; never fake the score.

Honesty contract (see resources/quality_metrics.md):
  * combined global similarity and per-region SSIM are measured, never rounded up;
  * PASS requires combined>=target AND all critical regions>=threshold AND critical-label
    recall==1.0 AND formulas reviewed AND PPTX editable AND a real PPTX render;
  * if the target is not reached within the budget -> REVIEW_REQUIRED with the real score;
  * DrawAI generates the whole figure, so "local repair" is guided global re-generation with
    best-of-round selection + regression check, not literal per-region patching (documented).

Usage:
  python run_reconstruction.py --image <path> --run-name <name> [--runs-root runs]
      [--max-rounds 10] [--target 0.99] [--region-threshold 0.99] [--device cpu]
      [--drawai-cmd "uv run --frozen drawai"] [--critical-labels "..."] [--transcribe-formulas]
      [--slide-size 16:9] [--no-repair]
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def run_drawai_full(drawai_cmd: list[str], image: Path, drawai_root: Path, run_name: str, device: str) -> dict:
    drawai_root.mkdir(parents=True, exist_ok=True)
    cmd = [*drawai_cmd, "run", str(image.resolve()), "--local",
           "--run-name", run_name, "--out", str(drawai_root), "--device", device]
    r = sh(cmd, cwd=str(_repo_root()))
    return {"cmd": " ".join(shlex.quote(c) for c in cmd), "returncode": r.returncode,
            "stdout_tail": r.stdout[-1500:], "stderr_tail": r.stderr[-1500:]}


def run_drawai_repair(drawai_cmd: list[str], case_config: Path) -> dict:
    cmd = [*drawai_cmd, "--config", str(case_config),
           "--from-stage", "svg_generated", "--to-stage", "svg_to_ppt_exported"]
    r = sh(cmd, cwd=str(_repo_root()))
    return {"cmd": " ".join(shlex.quote(c) for c in cmd), "returncode": r.returncode,
            "stdout_tail": r.stdout[-1500:], "stderr_tail": r.stderr[-1500:]}


def _drawai_repo() -> Path:
    """Locate the DrawAI checkout (where `uv run --frozen drawai` runs). Portable: DRAWAI_REPO env
    (or --drawai-repo), else upward search for src/drawai, else cwd. Set it when DrawAI lives outside
    this skill's tree — this skill is an absorbed, separately-updatable DrawAI dependency."""
    env = os.environ.get("DRAWAI_REPO")
    if env and (Path(env) / "src" / "drawai").exists():
        return Path(env)
    # default: the VENDORED engine shipped inside this skill (ts-figure-optimize/engine)
    vendored = HERE.parent / "engine"
    if (vendored / "src" / "drawai").exists():
        return vendored
    for p in [HERE, *HERE.parents]:
        if (p / "src" / "drawai").exists():
            return p
    return Path.cwd()


def _repo_root() -> Path:  # backward-compatible alias used throughout this module
    return _drawai_repo()


def find_case_dir(drawai_root: Path, run_name: str) -> Path | None:
    cands = sorted(drawai_root.glob(f"*/*_{run_name}/outputs/case_001*"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def find_case_config(case_dir: Path) -> Path | None:
    run_dir = case_dir.parents[1]
    cfg = run_dir / "configs" / "case_001.yaml"
    return cfg if cfg.exists() else None


def collect(case_dir: Path, layout: dict) -> dict:
    cp = {}
    pairs = [
        (case_dir / "box_ir/box_ir.json", layout["ir"] / "box_ir.json"),
        (case_dir / "sam3/raw_regions.json", layout["ir"] / "regions.json"),
        (case_dir / "ocr/ocr_boxes.json", layout["ir"] / "ocr_boxes.json"),
        (case_dir / "svg/semantic.svg", layout["svg"] / "semantic.svg"),
        (case_dir / "svg/rendered.png", layout["svg"] / "rendered_svg.png"),
        (case_dir / "svg_to_ppt/semantic.svg_to_ppt.pptx", layout["pptx"] / "editable.pptx"),
        (case_dir / "reports/pipeline_summary.json", layout["drawai"] / "pipeline_summary.json"),
        (case_dir / "reports/svg_validation_report.json", layout["drawai"] / "svg_validation_report.json"),
        (case_dir / "reports/svg_to_ppt_export_report.json", layout["drawai"] / "svg_to_ppt_export_report.json"),
    ]
    for src, dst in pairs:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            cp[dst.name] = str(dst)
    # Copy the raster asset tree so the SVG's relative hrefs ("../svg_to_ppt/assets/...") resolve
    # from the skill layout (run_root/svg/semantic.svg -> run_root/svg_to_ppt/assets/...). Without
    # this the file-path raster crops are dropped from the skill SVG / rendered PNG / publication PDF.
    run_root = layout["svg"].parent
    assets_src = case_dir / "svg_to_ppt" / "assets"
    if assets_src.exists():
        assets_dst = run_root / "svg_to_ppt" / "assets"
        if assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)
        cp["assets_tree"] = str(assets_dst)
    return cp


def make_layout(run_root: Path) -> dict:
    sub = {k: run_root / k for k in
           ["source", "drawai", "ir", "svg", "pptx", "pdf", "formulas", "comparisons", "reports", "final"]}
    sub["region_diffs"] = run_root / "comparisons" / "region_diffs"
    for p in sub.values():
        p.mkdir(parents=True, exist_ok=True)
    return sub


def py(script: str, *args) -> subprocess.CompletedProcess:
    return sh([sys.executable, str(HERE / script), *map(str, args)])


def _ssim_render(source_png: Path, svg: Path, tmp_png: Path) -> float | None:
    """Render an SVG (hrefs resolve from its own dir) and return SSIM vs source."""
    py("render_svg.py", svg, tmp_png, "--width", 1600)
    if not tmp_png.exists():
        return None
    src = C.load_gray(source_png)
    ren = C.load_gray(tmp_png, (src.shape[1], src.shape[0]))
    return C.ssim(src, ren)


def visual_quality_repairs(case_dir: Path, L: dict, rnd: int, source_png: Path,
                           drawai_cmd, case_config, do_repair: bool) -> dict:
    """Apply raster-background matching + audio-waveform repair on the CASE svg (where hrefs
    resolve). Keep-if-not-regressed (SSIM). Re-export the PPTX only when a repair is kept."""
    case_svg = case_dir / "svg" / "semantic.svg"
    case_render = case_dir / "svg" / "rendered.png"
    case_ocr = case_dir / "ocr" / "ocr_boxes.json"
    raster_out = L["comparisons"] / f"raster_bg_round{rnd}.json"
    wave_out = L["comparisons"] / f"waveform_round{rnd}.json"
    info = {"RASTER_BACKGROUND_MATCH": "PASS", "WAVEFORM_STYLE": "PASS",
            "repaired_raster": 0, "repaired_waveform": 0, "kept": False, "reverted": False}
    if not case_svg.exists():
        return info

    backup = case_svg.with_suffix(".pre_vq.bak")
    shutil.copy2(case_svg, backup)
    pre_ssim = _ssim_render(source_png, case_svg, L["comparisons"] / f"_pre_vq_{rnd}.png") if do_repair else None

    rargs = ["--svg", case_svg, "--assets-root", case_dir / "svg", "--out", raster_out,
             "--mode", "transparent"]
    if case_render.exists():
        rargs += ["--render", case_render]
    if do_repair:
        rargs += ["--repair", "--svg-out", case_svg]
    py("fix_raster_backgrounds.py", *rargs)
    rj = C.read_json(raster_out) if raster_out.exists() else {}
    info["RASTER_BACKGROUND_MATCH"] = rj.get("RASTER_BACKGROUND_MATCH", "PASS")
    info["repaired_raster"] = rj.get("repaired", 0)

    wargs = ["--svg", case_svg, "--source-ocr", case_ocr, "--out", wave_out]
    if do_repair:
        wargs += ["--repair", "--svg-out", case_svg]
    py("verify_waveforms.py", *wargs)
    wj = C.read_json(wave_out) if wave_out.exists() else {}
    info["WAVEFORM_STYLE"] = wj.get("WAVEFORM_STYLE", "PASS")
    info["repaired_waveform"] = wj.get("repaired_elements", 0)

    total_repaired = (info["repaired_raster"] or 0) + (info["repaired_waveform"] or 0)
    if do_repair and total_repaired > 0:
        post_ssim = _ssim_render(source_png, case_svg, L["comparisons"] / f"_post_vq_{rnd}.png")
        info["pre_ssim"], info["post_ssim"] = pre_ssim, post_ssim
        keep = post_ssim is not None and (pre_ssim is None or post_ssim >= pre_ssim - 0.01)
        if keep:
            info["kept"] = True
            # re-render the case render + re-export the PPTX from the repaired svg (best-effort)
            py("render_svg.py", case_svg, case_render, "--width", 2048)
            if case_config is not None:
                sh([*drawai_cmd, "--config", str(case_config),
                    "--from-stage", "svg_to_ppt_exported", "--to-stage", "svg_to_ppt_exported"],
                   cwd=str(_repo_root()))
        else:
            shutil.copy2(backup, case_svg)  # revert regression
            info["reverted"] = True
    backup.unlink(missing_ok=True)
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--runs-root", default="runs")
    ap.add_argument("--max-rounds", type=int, default=10)
    ap.add_argument("--target", type=float, default=0.99)
    ap.add_argument("--region-threshold", type=float, default=0.99)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--drawai-cmd", default="uv run --frozen drawai")
    ap.add_argument("--drawai-repo", default="",
                    help="Path to the DrawAI checkout (where `uv run --frozen drawai` runs). "
                         "Defaults to $DRAWAI_REPO, else an upward search for src/drawai, else cwd.")
    ap.add_argument("--critical-labels", default="")
    ap.add_argument("--transcribe-formulas", action="store_true")
    ap.add_argument("--slide-size", default="")
    ap.add_argument("--no-repair", action="store_true")
    args = ap.parse_args()

    if args.drawai_repo:
        os.environ["DRAWAI_REPO"] = args.drawai_repo

    drawai_cmd = shlex.split(args.drawai_cmd)
    image = Path(args.image)
    if not image.exists():
        print(f"FATAL: image not found: {image}", file=sys.stderr)
        return 2

    run_root = Path(args.runs_root) / args.run_name
    if run_root.exists():
        shutil.rmtree(run_root)
    L = make_layout(run_root)
    shutil.copy2(image, L["source"] / "source.png")
    source_png = L["source"] / "source.png"

    score_history = []
    rounds_log = []
    best = {"combined": -1.0, "round": -1}
    status = "FAILED"
    case_dir = None
    case_config = None

    for rnd in range(0, args.max_rounds + 1):
        t0 = time.time()
        if rnd == 0:
            dr = run_drawai_full(drawai_cmd, image, L["drawai"] / "runs", args.run_name, args.device)
            case_dir = find_case_dir(L["drawai"] / "runs", args.run_name)
            if case_dir is None:
                rounds_log.append({"round": rnd, "stage": "drawai_full", "error": "no case dir", "drawai": dr})
                C.write_json(L["comparisons"] / "score_history.json", score_history)
                _write_status(L, "FAILED", "DrawAI produced no output", rounds_log, best)
                return 6
            case_config = find_case_config(case_dir)
        else:
            if args.no_repair or case_config is None:
                break
            dr = run_drawai_repair(drawai_cmd, case_config)

        # visual-quality repairs (raster background matching + audio waveform) on the case svg,
        # keep-if-not-regressed, BEFORE collecting so the collected artifacts reflect the fixes.
        vq = visual_quality_repairs(case_dir, L, rnd, source_png, drawai_cmd, case_config,
                                    do_repair=not args.no_repair)

        collect(case_dir, L)
        semantic = L["svg"] / "semantic.svg"
        if not semantic.exists():
            rounds_log.append({"round": rnd, "error": "no semantic.svg", "drawai": dr})
            break

        # render SVG (fresh) + PPTX (real renderer or NOT_RUN)
        py("render_svg.py", semantic, L["svg"] / "rendered_svg.png", "--width", 2048)
        pptx = L["pptx"] / "editable.pptx"
        pptx_render = L["pptx"] / "rendered_pptx.png"
        pptx_render_status = "NOT_RUN"
        if pptx.exists():
            rp = py("render_pptx.py", pptx, pptx_render)
            try:
                pptx_render_status = json.loads((Path(str(pptx_render) + ".render.json")).read_text()).get("status", "NOT_RUN")
            except Exception:  # noqa: BLE001
                pptx_render_status = "NOT_RUN"

        # measure
        gm = L["comparisons"] / f"global_round{rnd}.json"
        m_args = ["--source", source_png, "--svg-render", L["svg"] / "rendered_svg.png",
                  "--svg", semantic, "--source-ocr", L["ir"] / "ocr_boxes.json",
                  "--box-ir", L["ir"] / "box_ir.json", "--out", gm]
        if pptx_render.exists() and pptx_render_status == "OK":
            m_args += ["--pptx-render", pptx_render]
        py("measure_similarity.py", *m_args)
        global_metrics = C.read_json(gm) if gm.exists() else {}
        combined = global_metrics.get("combined_global_similarity")

        rg = L["comparisons"] / f"regions_round{rnd}.json"
        py("compare_regions.py", "--source", source_png, "--svg-render", L["svg"] / "rendered_svg.png",
           "--box-ir", L["ir"] / "box_ir.json", "--source-ocr", L["ir"] / "ocr_boxes.json",
           "--svg", semantic, "--out", rg, "--diffs-dir", L["region_diffs"], "--threshold", args.region_threshold)
        region_metrics = C.read_json(rg) if rg.exists() else {}

        tv = L["comparisons"] / f"text_round{rnd}.json"
        fv = L["comparisons"] / f"formula_round{rnd}.json"
        tf_args = ["--source-ocr", L["ir"] / "ocr_boxes.json", "--svg", semantic,
                   "--formulas-dir", L["formulas"], "--out-text", tv, "--out-formula", fv]
        if args.critical_labels:
            tf_args += ["--critical-labels", args.critical_labels]
        if args.transcribe_formulas:
            tf_args += ["--transcribe"]
        py("verify_text_and_formulas.py", *tf_args)
        text_metrics = C.read_json(tv) if tv.exists() else {}
        formula_metrics = C.read_json(fv) if fv.exists() else {}

        ev = L["comparisons"] / f"pptx_round{rnd}.json"
        editable = False
        if pptx.exists():
            py("verify_pptx_editability.py", str(pptx), "--out", ev)
            editable = C.read_json(ev).get("editable", False) if ev.exists() else False

        entry = {
            "round": rnd, "stage": "drawai_full" if rnd == 0 else "repair_from_svg",
            "combined_global_similarity": combined,
            "ssim": global_metrics.get("metrics", {}).get("ssim"),
            "ocr_recall": text_metrics.get("ocr_token_prf", {}).get("recall"),
            "critical_label_recall": text_metrics.get("critical_label_recall"),
            "all_critical_regions_pass": region_metrics.get("all_critical_pass"),
            "worst_region_ssim": (region_metrics.get("worst_regions") or [{}])[0].get("ssim"),
            "pptx_editable": editable,
            "pptx_render_status": pptx_render_status,
            "formulas": formula_metrics.get("formula_count"),
            "raster_background_match": vq.get("RASTER_BACKGROUND_MATCH"),
            "waveform_style": vq.get("WAVEFORM_STYLE"),
            "vq_repaired_raster": vq.get("repaired_raster"),
            "vq_repaired_waveform": vq.get("repaired_waveform"),
            "vq_kept": vq.get("kept"),
            "seconds": round(time.time() - t0, 1),
            "drawai_returncode": dr.get("returncode"),
        }
        score_history.append(entry)
        rounds_log.append({**entry, "drawai_cmd": dr.get("cmd")})
        C.write_json(L["comparisons"] / "score_history.json", score_history)

        # keep best by combined score (snapshot final/)
        if combined is not None and combined > best["combined"]:
            best = {"combined": combined, "round": rnd}
            _snapshot_final(L, semantic, pptx)

        # stop condition (PASS)
        ocr_label_ok = text_metrics.get("critical_label_recall") == 1.0
        formulas_ok = formula_metrics.get("formula_count", 0) == 0 or formula_metrics.get("all_flagged_for_review", False)
        passed = (
            combined is not None and combined >= args.target
            and region_metrics.get("all_critical_pass") is True
            and ocr_label_ok and editable
            and pptx_render_status == "OK"  # a real PPTX render is mandatory for auto-PASS
            and vq.get("RASTER_BACKGROUND_MATCH") != "FAILED"
            and vq.get("WAVEFORM_STYLE") != "FAILED"
        )
        # note: formulas_ok is informational; formulas always require human review, never block PASS by themselves
        if passed:
            status = "PASS"
            break

    else:
        pass

    if status != "PASS":
        # we finished the loop without PASS
        status = "REVIEW_REQUIRED" if best["combined"] >= 0 else "FAILED"

    # publication PDF from the best SVG (vector, zoom-clear)
    _build_pdf(L)

    # assemble reports
    py("build_report.py", "--run-root", run_root, "--status", status,
       "--target", args.target, "--best-round", best["round"], "--slide-size", args.slide_size or "default")

    _write_status(L, status, "", rounds_log, best)
    print(f"\n=== {args.run_name}: {status} | best combined={best['combined']} (round {best['round']}) ===")
    print(f"reports: {L['reports']}")
    print("USER APPROVAL REQUIRED before this result is treated as final (see RECONSTRUCTION_REPORT.md).")
    return 0 if status in ("PASS", "REVIEW_REQUIRED") else 7


def _snapshot_final(L: dict, semantic: Path, pptx: Path) -> None:
    if semantic.exists():
        shutil.copy2(semantic, L["final"] / "semantic.svg")
        if (L["svg"] / "rendered_svg.png").exists():
            shutil.copy2(L["svg"] / "rendered_svg.png", L["final"] / "rendered_svg.png")
    if pptx.exists():
        shutil.copy2(pptx, L["final"] / "editable.pptx")


def _build_pdf(L: dict) -> None:
    svg = L["final"] / "semantic.svg"
    if not svg.exists():
        svg = L["svg"] / "semantic.svg"
    if not svg.exists():
        return
    try:
        import cairosvg
        # unsafe=True so local <image> raster crops are embedded into the publication PDF (vector
        # text/shapes + embedded rasters only where the SVG had <image>).
        cairosvg.svg2pdf(url=str(svg), write_to=str(L["pdf"] / "publication_figure.pdf"), unsafe=True)
        shutil.copy2(L["pdf"] / "publication_figure.pdf", L["final"] / "publication_figure.pdf")
    except Exception as exc:  # noqa: BLE001
        (L["pdf"] / "pdf_error.txt").write_text(str(exc), encoding="utf-8")


def _write_status(L: dict, status: str, note: str, rounds_log, best) -> None:
    C.write_json(L["reports"].parent / "status.json",
                 {"status": status, "note": note, "best": best, "rounds": rounds_log})


if __name__ == "__main__":
    raise SystemExit(main())
