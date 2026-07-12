#!/usr/bin/env python3
"""diff_overlay.py — guide the targeted visual-refinement (精修) loop.

Renders nothing itself; takes the SOURCE image and a RENDER of the current SVG and produces:
  - a difference HEATMAP (red = where the reconstruction differs most from the original),
  - a side-by-side (source | render | heatmap) for a quick eyeball,
  - a ranked list of the worst GRID CELLS (where to look / what to fix next), as JSON.

Use it each refinement iteration: render the SVG, run this, LOOK at the heatmap + worst cells,
surgically edit ONLY the offending SVG elements (arrow direction, icon/picture position, box align,
colour), re-render, re-run, keep the edit only if global SSIM (+ the touched cells) improved.

Usage:
  python diff_overlay.py --source S.png --render R.png --out-dir comparisons/ [--grid 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--render", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--grid", type=int, default=8)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    src = Image.open(a.source).convert("RGB")
    W, H = src.size
    ren = Image.open(a.render).convert("RGB").resize((W, H), Image.LANCZOS)
    s = np.asarray(src, np.float64)
    r = np.asarray(ren, np.float64)
    diff = np.abs(s - r).mean(axis=2)                       # 0..255 per-pixel mean abs diff

    # heatmap: red overlay on a dimmed source
    norm = np.clip(diff / max(diff.max(), 1e-6), 0, 1)
    heat = (s * 0.35).astype(np.uint8)
    heat[..., 0] = np.clip(heat[..., 0] + (norm * 255).astype(np.uint8), 0, 255)
    heat_img = Image.fromarray(heat)
    heat_img.save(out / "global_diff.png")

    # side-by-side
    sbs = Image.new("RGB", (W * 3 + 20, H), "white")
    sbs.paste(src, (0, 0)); sbs.paste(ren, (W + 10, 0)); sbs.paste(heat_img, (2 * W + 20, 0))
    sbs.save(out / "global_diff_sidebyside.png")

    # worst grid cells
    g = max(2, a.grid)
    cells = []
    overall = round(float(C.ssim(np.asarray(src.convert("L"), np.float64),
                                 np.asarray(ren.convert("L"), np.float64))), 4)
    for gy in range(g):
        for gx in range(g):
            y1, y2 = gy * H // g, (gy + 1) * H // g
            x1, x2 = gx * W // g, (gx + 1) * W // g
            cells.append({"cell": f"r{gy}c{gx}",
                          "bbox": [x1, y1, x2, y2],
                          "mean_diff": round(float(diff[y1:y2, x1:x2].mean()), 2)})
    cells.sort(key=lambda c: -c["mean_diff"])
    report = {"global_ssim": overall, "grid": g, "worst_cells": cells[:8],
              "heatmap": str(out / "global_diff.png"),
              "side_by_side": str(out / "global_diff_sidebyside.png")}
    C.write_json(out / "global_diff.json", report)
    print(f"global_ssim={overall} | worst cells: " +
          ", ".join(f"{c['cell']}({c['mean_diff']})" for c in cells[:5]))
    print(f"heatmap: {out/'global_diff.png'}  side-by-side: {out/'global_diff_sidebyside.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
