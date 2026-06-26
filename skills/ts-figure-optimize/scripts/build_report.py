#!/usr/bin/env python3
"""Assemble the human-readable reports from the JSON artifacts produced during a run.

Writes (under <run-root>/reports/):
  RECONSTRUCTION_REPORT.md, TEXT_VERIFICATION_REPORT.md, FORMULA_VERIFICATION_REPORT.md,
  PPTX_EDITABILITY_REPORT.md, ITERATION_HISTORY.md

Usage: python build_report.py --run-root runs/<name> --status STATUS --target 0.99
       --best-round N [--slide-size ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402


def _latest(comparisons: Path, prefix: str):
    files = sorted(comparisons.glob(f"{prefix}_round*.json"))
    return C.read_json(files[-1]) if files else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--target", type=float, default=0.99)
    ap.add_argument("--best-round", type=int, default=-1)
    ap.add_argument("--slide-size", default="default")
    args = ap.parse_args()

    rr = Path(args.run_root)
    comp = rr / "comparisons"
    reports = rr / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    history = C.read_json(comp / "score_history.json") if (comp / "score_history.json").exists() else []
    g = _latest(comp, "global")
    reg = _latest(comp, "regions")
    txt = _latest(comp, "text")
    frm = _latest(comp, "formula")
    pptx = _latest(comp, "pptx")
    rbg = _latest(comp, "raster_bg")
    wf = _latest(comp, "waveform")
    name = rr.name

    # --- RECONSTRUCTION_REPORT.md
    gm = g.get("metrics", {})
    lines = [
        f"# Reconstruction Report — {name}", "",
        f"**Final status:** `{args.status}`  ·  **target combined similarity:** {args.target}  ·  "
        f"**best round:** {args.best_round}  ·  **slide-size:** {args.slide_size}", "",
        "> Scores are MEASURED, not rounded up. A status of `REVIEW_REQUIRED` means the 0.99 gate was not "
        "reached within the iteration budget; the real best score is reported below.", "",
        "## Global similarity (latest round)", "",
        f"- **combined global similarity: {g.get('combined_global_similarity')}** (target {args.target})",
        f"- SSIM: {gm.get('ssim')} · MS-SSIM: {gm.get('ms_ssim')} · LPIPS-sim: {gm.get('lpips_sim')} "
        f"(LPIPS available: {g.get('lpips_available')})",
        f"- edge IoU: {gm.get('edge_iou')} · OCR F1: {gm.get('ocr_f1')} · color-hist: {gm.get('color_hist')}",
        f"- object-count ratio: {gm.get('object_count')} · layout IoU: {gm.get('layout_iou')}",
        f"- PPTX render: {g.get('pptx_render', 'see editability report')}"
        + (f" · PPTX-vs-source SSIM: {g.get('pptx_vs_source_ssim')}" if g.get('pptx_vs_source_ssim') is not None else ""),
        "",
        "## Region similarity (latest round)", "",
        f"- regions evaluated: {reg.get('region_count')} · all critical regions pass: "
        f"**{reg.get('all_critical_pass')}** · failed critical: {reg.get('failed_critical_count')}", "",
        "| region | type | ssim | edge IoU | color Δ | ocr recall | pass |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reg.get("worst_regions", []):
        lines.append(f"| {r.get('id')} | {r.get('type')} | {r.get('ssim')} | {r.get('edge_iou')} | "
                     f"{r.get('color_delta')} | {r.get('ocr_recall')} | {'✅' if r.get('pass') else '❌'} |")
    lines += [
        "", "## Stop-condition checklist", "",
        f"- combined ≥ target: {_chk(g.get('combined_global_similarity'), args.target)}",
        f"- all critical regions ≥ threshold: {'✅' if reg.get('all_critical_pass') else '❌'}",
        f"- critical-label OCR recall == 1.0: {'✅' if txt.get('critical_label_recall') == 1.0 else '❌'} "
        f"(measured {txt.get('critical_label_recall')})",
        f"- formulas reviewed: {'⚠ manual review required' if frm.get('formula_count') else 'n/a (none detected)'}",
        f"- PPTX genuinely editable: {'✅' if pptx.get('editable') else '❌'}",
        f"- real PPTX render produced: {_pptx_render_flag(history)}",
        f"- RASTER_BACKGROUND_MATCH: {_gate(rbg.get('RASTER_BACKGROUND_MATCH'))} "
        f"(assets {rbg.get('asset_count')}, repaired {rbg.get('repaired')}, flagged {rbg.get('flagged')})",
        f"- WAVEFORM_STYLE: {_gate(wf.get('WAVEFORM_STYLE'))} "
        f"(expected {wf.get('waveform_expected')}, bar-style {(wf.get('classification') or {}).get('has_bar_style')}, "
        f"forbidden {(wf.get('classification') or {}).get('forbidden_total')}, repaired {wf.get('repaired_elements')})",
        "",
        "## User approval (required)", "",
        "Before this result is treated as final, review side-by-side: `source/source.png`, "
        "`svg/rendered_svg.png`, `pptx/rendered_pptx.png` (if rendered), the lowest-scoring regions above, "
        "the formula verification report, and the remaining raster assets (PPTX pictures). "
        "Approve explicitly to finalize.", "",
        "## Artifacts", "",
        "- editable SVG: `final/semantic.svg` · editable PPTX: `final/editable.pptx` · "
        "publication PDF: `final/publication_figure.pdf`",
        "- source preserved: `source/source.png` · Box IR: `ir/box_ir.json` · score history: "
        "`comparisons/score_history.json`",
    ]
    (reports / "RECONSTRUCTION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")

    # --- TEXT_VERIFICATION_REPORT.md
    prf = txt.get("ocr_token_prf", {})
    tl = [f"# Text Verification — {name}", "",
          f"- OCR token recall: **{prf.get('recall')}** · precision: {prf.get('precision')} "
          f"(unique src {prf.get('src_unique')}, matched {prf.get('matched_unique')})",
          f"- critical-label recall: **{txt.get('critical_label_recall')}** "
          f"(checked {txt.get('critical_labels_checked')}, failed {txt.get('critical_labels_failed')})",
          "- All ordinary text is emitted by DrawAI as native editable `<text>` (PowerPoint text boxes after "
          "conversion); no text is rasterized. Critical-label mismatch fails the quality gate.", "",
          "## Failed / weak labels", "", "| label | token-hit ratio | pass |", "|---|---|---|"]
    for l in txt.get("labels", []):
        if not l.get("pass"):
            tl.append(f"| {l.get('label')} | {l.get('token_hit_ratio')} | ❌ |")
    if all(l.get("pass") for l in txt.get("labels", [])) and txt.get("labels"):
        tl.append("| (none) | — | ✅ |")
    (reports / "TEXT_VERIFICATION_REPORT.md").write_text("\n".join(tl), encoding="utf-8")

    # --- FORMULA_VERIFICATION_REPORT.md
    fl = [f"# Formula Verification — {name}", "",
          f"- formulas detected: {frm.get('formula_count')} · transcribed to LaTeX: {frm.get('transcribed')} · "
          f"vectorized: {frm.get('vectorized')}",
          f"- native OMML insertion supported: {frm.get('omml_supported')} — "
          f"{frm.get('note','')}",
          "- **Every formula is flagged for explicit human correctness review.** Formulas are never kept as "
          "low-resolution raster.", "",
          "| id | detected text | latex | vector svg | needs review |", "|---|---|---|---|---|"]
    for f in frm.get("formulas", []):
        fl.append(f"| {f.get('id')} | `{(f.get('detected_text') or '')[:50]}` | "
                  f"{'✅' if f.get('latex') else '—'} | {'✅' if f.get('vector_svg_file') else '—'} | ⚠ |")
    (reports / "FORMULA_VERIFICATION_REPORT.md").write_text("\n".join(fl), encoding="utf-8")

    # --- PPTX_EDITABILITY_REPORT.md
    st = pptx.get("structure", {})
    pl = [f"# PPTX Editability — {name}", "",
          f"- gate pass: **{pptx.get('gate_pass')}** · editable: {pptx.get('editable')}",
          f"- native shapes (p:sp): {st.get('shape_tag_count')} · text runs (a:t): {st.get('text_run_count')} · "
          f"pictures (p:pic): {st.get('picture_tag_count')} · connectors (p:cxnSp): {st.get('connector_tag_count')}",
          f"- single-screenshot-like: {st.get('is_single_screenshot_like')} · media: {st.get('media_count')}", ""]
    if pptx.get("failures"):
        pl += ["## Failures", ""] + [f"- {x}" for x in pptx["failures"]]
    else:
        pl += ["No editability failures: the slide contains native autoshapes + editable text, not a flattened image."]
    (reports / "PPTX_EDITABILITY_REPORT.md").write_text("\n".join(pl), encoding="utf-8")

    # --- ITERATION_HISTORY.md
    il = [f"# Iteration History — {name}", "",
          "| round | stage | combined | ssim | ocr recall | crit-label | crit regions | "
          "worst ssim | pptx edit | pptx render | raster-bg | waveform | vq kept | sec |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for h in history:
        il.append(f"| {h.get('round')} | {h.get('stage')} | {h.get('combined_global_similarity')} | "
                  f"{h.get('ssim')} | {h.get('ocr_recall')} | {h.get('critical_label_recall')} | "
                  f"{h.get('all_critical_regions_pass')} | {h.get('worst_region_ssim')} | "
                  f"{h.get('pptx_editable')} | {h.get('pptx_render_status')} | "
                  f"{h.get('raster_background_match')} | {h.get('waveform_style')} | "
                  f"{h.get('vq_kept')} | {h.get('seconds')} |")
    il += ["", f"Best round by combined similarity: **{args.best_round}**. All intermediate attempts are kept "
           "under `drawai/` and `comparisons/`."]
    (reports / "ITERATION_HISTORY.md").write_text("\n".join(il), encoding="utf-8")

    print(f"reports written to {reports}")
    return 0


def _chk(v, target):
    if v is None:
        return "❌ (not measured)"
    return ("✅" if v >= target else "❌") + f" ({v})"


def _gate(v):
    return {"PASS": "✅ PASS", "REVIEW_REQUIRED": "⚠ REVIEW_REQUIRED", "FAILED": "❌ FAILED"}.get(v, f"({v})")


def _pptx_render_flag(history):
    statuses = [h.get("pptx_render_status") for h in history]
    if "OK" in statuses:
        return "✅"
    return "❌ NOT_RUN (no office renderer; cannot auto-PASS)"


if __name__ == "__main__":
    raise SystemExit(main())
