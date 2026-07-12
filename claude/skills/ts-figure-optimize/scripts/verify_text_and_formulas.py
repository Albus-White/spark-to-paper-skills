#!/usr/bin/env python3
"""Text + formula verification.

Text: compares source OCR tokens against SVG <text> tokens (recall/precision) and checks
critical-label recall. Critical labels can be supplied via --critical-labels (comma list);
otherwise they are inferred (longer OCR tokens / title-like strings).

Formulas: detects candidate formula strings (from OCR + SVG data-pb-role="formula"), writes
formulas/formula_NNN.json with the transcription and a needs_review flag, and — when an LLM CLI
(codex/claude) is available and --transcribe is set — attempts a LaTeX transcription saved to
formula_NNN.tex. LaTeX->SVG is attempted via matplotlib mathtext when available; otherwise the
formula is flagged for manual vectorization (never a low-res raster).

Usage:
  python verify_text_and_formulas.py --source-ocr ocr.json --svg semantic.svg \
      --formulas-dir formulas/ --out-text text_verification.json --out-formula formula_verification.json \
      [--critical-labels "..."] [--transcribe]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402


def svg_formula_texts(svg_path: Path) -> list[str]:
    s = svg_path.read_text(encoding="utf-8", errors="ignore")
    out = []
    for m in re.finditer(r'<text\b[^>]*data-pb-role="formula"[^>]*>(.*?)</text>', s, re.S):
        out.append(re.sub(r"<[^>]+>", " ", m.group(1)).strip())
    return [t for t in out if t]


def detect_formulas(ocr_json: Path, svg_path: Path) -> list[str]:
    cands = set()
    d = C.read_json(ocr_json)
    for b in d.get("ocr_text_boxes", []):
        t = str(b.get("text", "")).strip()
        if C.looks_like_formula(t):
            cands.add(t)
    for t in svg_formula_texts(svg_path):
        if t:
            cands.add(t)
    return sorted(cands)


def latex_via_llm(text: str) -> str | None:
    """Best-effort LaTeX transcription using an available agent CLI. Honest: returns None if none."""
    for exe, args in (("codex", ["exec"]), ("claude", ["-p"])):
        if shutil.which(exe):
            prompt = ("Transcribe this scientific-figure formula text into a single line of LaTeX. "
                      "Output ONLY the LaTeX, no markdown fences, no prose.\nFormula text: " + text)
            try:
                r = subprocess.run([exe, *args, prompt], capture_output=True, text=True, timeout=120)
                out = (r.stdout or "").strip()
                out = re.sub(r"^```[a-zA-Z]*", "", out).strip().strip("`").strip()
                if out and len(out) < 400:
                    return out
            except Exception:  # noqa: BLE001
                return None
    return None


def latex_to_svg(latex: str, out_svg: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(4, 1))
        fig.text(0.01, 0.4, f"${latex}$", fontsize=18)
        fig.savefig(out_svg, format="svg", bbox_inches="tight", transparent=True)
        plt.close(fig)
        return out_svg.exists()
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-ocr", required=True)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--formulas-dir", required=True)
    ap.add_argument("--out-text", required=True)
    ap.add_argument("--out-formula", required=True)
    ap.add_argument("--critical-labels", default="")
    ap.add_argument("--transcribe", action="store_true")
    args = ap.parse_args()

    src_text = C.ocr_text_from_boxir(args.source_ocr)
    svg_text = C.svg_text_content(Path(args.svg))
    prf = C.token_prf(src_text, svg_text)

    if args.critical_labels.strip():
        crit = [s.strip() for s in args.critical_labels.split(",") if s.strip()]
    else:
        # infer: distinct multi-word OCR strings / capitalized titles
        d = C.read_json(args.source_ocr)
        crit = []
        for b in d.get("ocr_text_boxes", []):
            t = str(b.get("text", "")).strip()
            if len(t) >= 6 and (t[:1].isupper() or " " in t):
                crit.append(t)
        crit = sorted(set(crit))[:40]

    svg_tok = set(C.tokens(svg_text))
    label_results = []
    missed = 0
    for label in crit:
        ltoks = C.tokens(label)
        if not ltoks:
            continue
        hit = sum(1 for t in ltoks if t in svg_tok) / len(ltoks)
        ok = hit >= 0.7
        if not ok:
            missed += 1
        label_results.append({"label": label, "token_hit_ratio": round(hit, 3), "pass": ok})
    critical_recall = round(1 - missed / len(label_results), 4) if label_results else None

    text_result = {
        "ocr_token_prf": prf,
        "critical_label_recall": critical_recall,
        "critical_labels_checked": len(label_results),
        "critical_labels_failed": missed,
        "critical_label_recall_is_1": critical_recall == 1.0 if critical_recall is not None else False,
        "labels": label_results,
    }
    C.write_json(args.out_text, text_result)

    # formulas
    fdir = Path(args.formulas_dir)
    fdir.mkdir(parents=True, exist_ok=True)
    formulas = detect_formulas(Path(args.source_ocr), Path(args.svg))
    items = []
    for i, ftext in enumerate(formulas, start=1):
        fid = f"formula_{i:03d}"
        latex = None
        svg_ok = False
        if args.transcribe:
            latex = latex_via_llm(ftext)
            if latex:
                (fdir / f"{fid}.tex").write_text(latex + "\n", encoding="utf-8")
                svg_ok = latex_to_svg(latex, fdir / f"{fid}.svg")
        meta = {
            "id": fid,
            "detected_text": ftext,
            "latex": latex,
            "latex_source_file": f"{fid}.tex" if latex else None,
            "vector_svg_file": f"{fid}.svg" if svg_ok else None,
            "omml_inserted": False,  # native Office Math insertion not implemented; vector-SVG fallback documented
            "needs_review": True,    # every formula is always flagged for explicit correctness review
            "rasterized": False,
        }
        C.write_json(fdir / f"{fid}.json", meta)
        items.append(meta)

    formula_result = {
        "formula_count": len(items),
        "transcribed": sum(1 for x in items if x["latex"]),
        "vectorized": sum(1 for x in items if x["vector_svg_file"]),
        "all_flagged_for_review": all(x["needs_review"] for x in items),
        "omml_supported": False,
        "note": "Native OMML insertion not implemented; per spec item 6 the fallback is a vector SVG "
                "generated from LaTeX plus the preserved .tex source. Every formula needs manual review.",
        "formulas": items,
    }
    C.write_json(args.out_formula, formula_result)

    print(f"text recall={prf.get('recall')} critical_label_recall={critical_recall} "
          f"formulas={len(items)} transcribed={formula_result['transcribed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
