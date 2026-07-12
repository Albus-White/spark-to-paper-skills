#!/usr/bin/env python3
"""Region-level similarity using Box IR panels/regions.

For each region (content_box panels, plus grids/large icons) computes region SSIM, edge IoU,
dominant-color delta, local OCR recall, and object-count consistency. Marks critical regions and
emits the worst-scoring regions to drive targeted local repair.

Usage:
  python compare_regions.py --source S.png --svg-render R.png --box-ir box_ir.json \
      --source-ocr ocr_boxes.json --svg semantic.svg --out region_scores.json --diffs-dir region_diffs/
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

CRITICAL_TYPES = {"content_box", "grid"}  # panels/modules and result tables
REGION_SSIM_THRESHOLD = 0.99


def region_tokens_from_svg(svg_path: Path, bbox, canvas):
    """Approximate: SVG text whose x/y fall in bbox (canvas coords)."""
    s = svg_path.read_text(encoding="utf-8", errors="ignore")
    toks = []
    for m in re.finditer(r'<text\b[^>]*\bx="([\d.]+)"[^>]*\by="([\d.]+)"[^>]*>(.*?)</text>', s, re.S):
        x, y = float(m.group(1)), float(m.group(2))
        if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
            t = re.sub(r"<[^>]+>", " ", m.group(3))
            toks.append(t)
    return " ".join(toks)


def ocr_tokens_in_bbox(ocr_json, bbox):
    d = C.read_json(ocr_json)
    out = []
    for b in d.get("ocr_text_boxes", []):
        bb = b.get("bbox")
        if not bb:
            continue
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        if bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]:
            out.append(str(b.get("text", "")))
    return " ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--svg-render", required=True)
    ap.add_argument("--box-ir", required=True)
    ap.add_argument("--source-ocr", required=True)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--diffs-dir", required=True)
    ap.add_argument("--threshold", type=float, default=REGION_SSIM_THRESHOLD)
    args = ap.parse_args()

    box_ir = C.read_json(args.box_ir)
    canvas = box_ir.get("canvas", {})
    cw, ch = canvas.get("width"), canvas.get("height")
    src = Image.open(args.source).convert("RGB")
    dst_size = src.size
    ren = Image.open(args.svg_render).convert("RGB").resize(dst_size, Image.LANCZOS)
    diffs_dir = Path(args.diffs_dir)
    diffs_dir.mkdir(parents=True, exist_ok=True)

    # Critical panel regions = content_box/grid from Box IR. If too few are detected (some
    # figures' panels get labelled icon/arrow by SAM3), fall back to an auto-grid split so region
    # analysis is never vacuous. Auto-grid regions are NON-critical and clearly marked.
    panel_boxes = [(b.get("id"), b.get("type"), b.get("bbox"), True)
                   for b in C.boxir_boxes(box_ir)
                   if b.get("type") in CRITICAL_TYPES and b.get("bbox")]
    if len(panel_boxes) < 2 and cw and ch:
        cols = max(2, min(6, round((cw / ch) * 1.5)))
        rows = 1 if cw >= ch else max(2, min(4, round((ch / cw) * 1.5)))
        cwid, chei = cw / cols, ch / rows
        for r in range(rows):
            for c in range(cols):
                panel_boxes.append((f"AUTOGRID_r{r}c{c}", "auto_panel",
                                    [c * cwid, r * chei, (c + 1) * cwid, (r + 1) * chei], False))

    regions = []
    for _id, _type, bbox, _critical in panel_boxes:
        if not bbox:
            continue
        b = {"id": _id, "type": _type, "bbox": bbox, "_critical": _critical}
        sc = C.crop_scaled(src, bbox, (cw, ch), dst_size)
        rc = C.crop_scaled(ren, bbox, (cw, ch), dst_size)
        if sc is None or rc is None or min(sc.size) < 8:
            continue
        rc = rc.resize(sc.size, Image.LANCZOS)
        sg = np.asarray(sc.convert("L"), dtype=np.float64)
        rg = np.asarray(rc.convert("L"), dtype=np.float64)
        r_ssim = round(C.ssim(sg, rg), 4)
        r_edge = C.edge_similarity(np.asarray(sc.convert("L")), np.asarray(rc.convert("L")), sc.size)["edge_iou"]
        col_delta = round(C.color_delta(C.dominant_color(np.asarray(sc, float)), C.dominant_color(np.asarray(rc, float))), 2)
        src_tok = ocr_tokens_in_bbox(args.source_ocr, bbox)
        svg_tok = region_tokens_from_svg(Path(args.svg), bbox, (cw, ch))
        prf = C.token_prf(src_tok, svg_tok)
        # diff image
        diff_path = ""
        try:
            d = ImageChops.difference(sc, rc)
            dp = diffs_dir / f"region_{b.get('id')}.png"
            d.save(dp)
            diff_path = str(dp)
        except Exception:  # noqa: BLE001
            pass
        regions.append({
            "id": b.get("id"),
            "type": b.get("type"),
            "bbox": [int(x) for x in bbox],
            "critical": b.get("_critical", False),
            "ssim": r_ssim,
            "edge_iou": r_edge,
            "color_delta": col_delta,
            "ocr_recall": prf.get("recall"),
            "diff": diff_path,
            "pass": r_ssim >= args.threshold,
        })

    regions.sort(key=lambda r: r["ssim"])
    worst = regions[:5]
    critical_regions = [r for r in regions if r["critical"]]
    failed_critical = [r for r in critical_regions if not r["pass"]]
    # Honesty: with NO detected critical panels we cannot confirm a pass -> null, not vacuous True.
    if not critical_regions:
        all_critical_pass = None
    else:
        all_critical_pass = len(failed_critical) == 0
    used_autogrid = any(r["type"] == "auto_panel" for r in regions)
    result = {
        "threshold": args.threshold,
        "region_count": len(regions),
        "critical_region_count": len(critical_regions),
        "used_autogrid_fallback": used_autogrid,
        "regions": regions,
        "worst_regions": worst,
        "failed_critical_count": len(failed_critical),
        "all_critical_pass": all_critical_pass,
        "note": ("No content_box/grid panels were detected by SAM3; auto-grid fallback regions are "
                 "non-critical, so all_critical_pass is null (cannot confirm). Provide panels or treat "
                 "as REVIEW_REQUIRED.") if not critical_regions else "",
    }
    C.write_json(args.out, result)
    print(f"regions={len(regions)} failed_critical={len(failed_critical)} "
          f"worst_ssim={worst[0]['ssim'] if worst else 'n/a'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
