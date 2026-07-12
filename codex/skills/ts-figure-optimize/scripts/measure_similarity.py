#!/usr/bin/env python3
"""Global similarity between the source image and the reconstruction render(s).

Computes multiple metrics and a normalized combined score in [0,1]. Metrics that need
optional libraries (LPIPS, scikit-image MS-SSIM) are skipped honestly when unavailable;
the combined score is computed only over the metrics actually measured (weights renormalized).

Usage:
  python measure_similarity.py --source S.png --svg-render R.png --svg semantic.svg \
      --source-ocr ocr_boxes.json --box-ir box_ir.json [--pptx-render P.png] --out metrics.json
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402


def lpips_similarity(src_rgb, ren_rgb) -> float | None:
    try:
        import torch, lpips  # noqa: F401
    except Exception:
        return None
    try:
        import torch
        import lpips as lpips_mod
        net = lpips_mod.LPIPS(net="alex")
        def to_t(x):
            t = torch.tensor(x / 127.5 - 1.0, dtype=torch.float32).permute(2, 0, 1).unsqueeze(0)
            return t
        with torch.no_grad():
            d = float(net(to_t(src_rgb), to_t(ren_rgb)).item())
        return round(1.0 / (1.0 + d), 4)  # convert distance -> similarity
    except Exception:
        return None


def svg_object_count(svg_path: Path) -> int:
    s = svg_path.read_text(encoding="utf-8", errors="ignore")
    n = 0
    for t in ("rect", "circle", "ellipse", "path", "polygon", "polyline", "line", "image", "text"):
        n += len(re.findall(r"<" + t + r"\b", s))
    return n


def layout_iou(box_ir: dict, svg_path: Path) -> float | None:
    """Coarse layout overlap: union area of box_ir content boxes vs union of svg rects."""
    boxes = [b.get("bbox") for b in C.boxir_boxes(box_ir) if b.get("type") == "content_box" and b.get("bbox")]
    if not boxes:
        return None
    canvas = box_ir.get("canvas", {})
    cw, ch = canvas.get("width"), canvas.get("height")
    if not cw or not ch:
        return None
    s = svg_path.read_text(encoding="utf-8", errors="ignore")
    rects = re.findall(r'<rect\b[^>]*\bx="([\d.]+)"[^>]*\by="([\d.]+)"[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', s)
    if not rects:
        return None
    grid = np.zeros((64, 64), dtype=bool)
    grid2 = np.zeros((64, 64), dtype=bool)

    def paint(g, x1, y1, x2, y2):
        gx1, gy1 = int(x1 / cw * 64), int(y1 / ch * 64)
        gx2, gy2 = int(np.ceil(x2 / cw * 64)), int(np.ceil(y2 / ch * 64))
        g[max(0, gy1):min(64, gy2), max(0, gx1):min(64, gx2)] = True

    for b in boxes:
        paint(grid, *b)
    for x, y, w, h in rects:
        x, y, w, h = float(x), float(y), float(w), float(h)
        if w * h > 0.05 * cw * ch:  # only large panel-like rects
            paint(grid2, x, y, x + w, y + h)
    inter = np.logical_and(grid, grid2).sum()
    union = np.logical_or(grid, grid2).sum()
    return round(float(inter / union), 4) if union else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--svg-render", required=True)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--source-ocr", required=True)
    ap.add_argument("--box-ir", required=True)
    ap.add_argument("--pptx-render", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    src_img = C.load_gray(args.source)
    size = (src_img.shape[1], src_img.shape[0])
    ren_gray = C.load_gray(args.svg_render, size)
    src_rgb = C.load_rgb(args.source)
    ren_rgb = C.load_rgb(args.svg_render, size)

    box_ir = C.read_json(args.box_ir)
    src_text = C.ocr_text_from_boxir(args.source_ocr)
    svg_text = C.svg_text_content(args.svg)
    prf = C.token_prf(src_text, svg_text)
    ocr_f1 = None
    if prf.get("recall") is not None and prf.get("precision") is not None and (prf["recall"] + prf["precision"]) > 0:
        ocr_f1 = round(2 * prf["recall"] * prf["precision"] / (prf["recall"] + prf["precision"]), 4)

    # object count consistency (box_ir vs svg)
    n_boxir = len(C.boxir_boxes(box_ir)) + len(box_ir.get("ocr_text_boxes", []))
    n_svg = svg_object_count(Path(args.svg))
    obj_ratio = round(min(n_boxir, n_svg) / max(n_boxir, n_svg), 4) if max(n_boxir, n_svg) else None

    metrics = {
        "ssim": round(C.ssim(src_img, ren_gray), 4),
        "ms_ssim": (lambda v: round(v, 4) if v is not None else None)(C.ms_ssim(src_img, ren_gray)),
        "lpips_sim": lpips_similarity(src_rgb, ren_rgb),
        "edge_iou": C.edge_similarity(args.source, args.svg_render, size)["edge_iou"],
        "ocr_f1": ocr_f1,
        "color_hist": round(C.color_hist_similarity(src_rgb, ren_rgb), 4),
        "object_count": obj_ratio,
        "layout_iou": layout_iou(box_ir, Path(args.svg)),
    }
    combined = C.combined_score(metrics)

    result = {
        "size": list(size),
        "metrics": metrics,
        "ocr_token_prf": prf,
        "object_counts": {"box_ir": n_boxir, "svg_elements": n_svg},
        "combined_global_similarity": combined["combined"],
        "combined_detail": combined,
        "lpips_available": metrics["lpips_sim"] is not None,
    }

    if args.pptx_render and Path(args.pptx_render).exists():
        pptx_gray = C.load_gray(args.pptx_render, size)
        result["pptx_vs_source_ssim"] = round(C.ssim(src_img, pptx_gray), 4)
        result["pptx_vs_svg_ssim"] = round(C.ssim(ren_gray, pptx_gray), 4)
    else:
        result["pptx_render"] = "NOT_RUN"

    C.write_json(args.out, result)
    print(f"combined_global_similarity={result['combined_global_similarity']} "
          f"ssim={metrics['ssim']} ocr_f1={ocr_f1} edge_iou={metrics['edge_iou']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
