#!/usr/bin/env python3
"""region_crops.py — emit per-small-region SOURCE|RENDER side-by-side crops for VISION comparison.

The metric checks (SSIM/edge/colour) cannot see SEMANTIC defects — text overflowing its box, an arrow
overlapping other graphics, a cycle/loop icon drawn as a plain arrow, misaligned bars, a matrix
overlapping its colourbar. Those need a vision model to LOOK at each region. This tiles the figure into
small regions (Box-IR panels, each optionally sub-tiled) and writes, per region, a side-by-side
[source | render] PNG so Claude/GPT can Read each and enumerate defects.

For EACH region image, the vision model checks this SEMANTIC checklist (font/AA/colour-shade differences
are IGNORED):
  - text overflowing / spilling outside its box or panel
  - any element overlapping/colliding with another (arrow over a figure, matrix over its colourbar, …)
  - wrong/garbled ICON semantics (e.g. a cycle/loop ↻ drawn as a straight arrow; ↔ drawn as →)
  - misaligned / unevenly-sized repeated shapes (bars, rows, badges)
  - missing / duplicated / wrongly-positioned elements vs the source

Usage:
  python region_crops.py --source S.png --render R.png [--box-ir box_ir.json] --out-dir comparisons/regions \
      [--subtile 2] [--grid 4] [--min-frac 0.02]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402


def _pair(src, ren, box, scale):
    sc = src.crop(box); rc = ren.crop(box)
    cw, ch = sc.size
    if cw < 4 or ch < 4:
        return None
    canvas = Image.new("RGB", (cw * 2 + 14, ch + 18), "white")
    canvas.paste(sc, (0, 18)); canvas.paste(rc, (cw + 14, 18))
    d = ImageDraw.Draw(canvas)
    d.text((2, 4), "SOURCE", fill="black"); d.text((cw + 16, 4), "RENDER", fill="black")
    if scale != 1.0:
        canvas = canvas.resize((int(canvas.width * scale), int(canvas.height * scale)))
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--render", required=True)
    ap.add_argument("--box-ir", default="")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--subtile", type=int, default=1, help="split each panel into NxN finer cells")
    ap.add_argument("--grid", type=int, default=4, help="fallback grid when no box-ir")
    ap.add_argument("--min-frac", type=float, default=0.02, help="skip regions smaller than this area frac")
    ap.add_argument("--scale", type=float, default=2.0)
    a = ap.parse_args()

    src = Image.open(a.source).convert("RGB")
    W, H = src.size
    ren = Image.open(a.render).convert("RGB").resize((W, H), Image.LANCZOS)
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

    regions = []
    if a.box_ir and Path(a.box_ir).exists():
        bir = C.read_json(a.box_ir)
        cw, ch = bir.get("canvas", {}).get("width"), bir.get("canvas", {}).get("height")
        sx, sy = (W / cw, H / ch) if cw and ch else (1, 1)
        for b in bir.get("boxes", []):
            if b.get("type") not in ("content_box", "grid"):
                continue
            x1, y1, x2, y2 = b["bbox"]
            regions.append((b.get("id"), (x1 * sx, y1 * sy, x2 * sx, y2 * sy)))
    if not regions:
        g = max(2, a.grid)
        for r in range(g):
            for c in range(g):
                regions.append((f"r{r}c{c}", (c * W / g, r * H / g, (c + 1) * W / g, (r + 1) * H / g)))

    # optional sub-tiling for finer granularity
    final = []
    n = max(1, a.subtile)
    for rid, (x1, y1, x2, y2) in regions:
        if n == 1:
            final.append((rid, (x1, y1, x2, y2)))
        else:
            for sr in range(n):
                for sc_ in range(n):
                    fx1 = x1 + (x2 - x1) * sc_ / n; fx2 = x1 + (x2 - x1) * (sc_ + 1) / n
                    fy1 = y1 + (y2 - y1) * sr / n; fy2 = y1 + (y2 - y1) * (sr + 1) / n
                    final.append((f"{rid}_{sr}{sc_}", (fx1, fy1, fx2, fy2)))

    index = []
    for rid, box in final:
        bx = tuple(int(v) for v in box)
        if (bx[2] - bx[0]) * (bx[3] - bx[1]) < a.min_frac * W * H:
            continue
        img = _pair(src, ren, bx, a.scale)
        if img is None:
            continue
        fp = out / f"region_{rid}.png"
        img.save(fp)
        index.append({"id": rid, "bbox": list(bx), "image": str(fp)})
    C.write_json(out / "index.json", {"count": len(index), "regions": index,
                 "semantic_checklist": ["text_overflow", "element_overlap", "wrong_icon",
                                        "misaligned_shapes", "missing_or_duplicated", "wrong_position"]})
    print(f"wrote {len(index)} region pair(s) to {out} — Read each region_*.png and enumerate semantic defects.")
    for r in index:
        print(f"  {r['id']:10} bbox={r['bbox']}  {r['image']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
