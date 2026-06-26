#!/usr/bin/env python3
"""Adapter: map a finished ts-figure-optimize run into the ts-paper figure contract.

ts-paper-figure step 5b expects, per figure <label>:
  figures/<label>.svg   a self-contained editable HYBRID (the approved render as a whole-canvas
                        <image> + an editable <text> overlay)
  figures/<label>.pdf   the embedded hybrid PDF (render raster + editable text fonts)
  figures/<label>.png   the kept original raster

This takes a ts-figure-optimize HYBRID run dir (runs/<name>, with final/editable_hybrid.svg +
final/editable_hybrid.pdf) and writes those files into <figures-dir>, **inlining the SVG's local
<image> href as base64** so figures/<label>.svg renders standalone (passes
`check_vector_pdf.py lint --render-check`). The PDF is already self-contained. (Legacy full-vector
run dirs with final/semantic.svg + final/publication_figure.pdf are still accepted as a fallback.)

Usage:
  python export_paper_figure.py --run-dir runs/<name> --label <label> --figures-dir <paper>/figures
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import re
import shutil
from pathlib import Path


def inline_images(svg_path: Path) -> str:
    """Return SVG text with local <image href="..."> rewritten to base64 data URIs (self-contained)."""
    svg = svg_path.read_text(encoding="utf-8")
    base = svg_path.parent

    def repl(m):
        attr, href = m.group(1), m.group(2)
        if href.startswith("data:") or href.startswith(("http://", "https://")):
            return m.group(0)
        p = (base / href).resolve()
        if not p.exists():
            return m.group(0)
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return f'{attr}="data:{mime};base64,{b64}"'

    return re.sub(r'(xlink:href|href)="([^"]+)"', repl, svg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--figures-dir", required=True)
    args = ap.parse_args()

    run = Path(args.run_dir)
    figdir = Path(args.figures_dir)
    figdir.mkdir(parents=True, exist_ok=True)
    final = run / "final"
    # HYBRID build emits editable_hybrid.{svg,pdf}; fall back to the legacy full-vector names if present.
    src_svg = final / "editable_hybrid.svg"
    if not src_svg.exists():
        src_svg = final / "semantic.svg"
    src_pdf = final / "editable_hybrid.pdf"
    if not src_pdf.exists():
        src_pdf = final / "publication_figure.pdf"
    src_png = run / "source" / "source.png"  # optional: ts-paper-figure already has figures/<label>.png
    for p, what in ((src_svg, "final/editable_hybrid.svg (or legacy semantic.svg)"),
                    (src_pdf, "final/editable_hybrid.pdf (or legacy publication_figure.pdf)")):
        if not p.exists():
            raise SystemExit(f"FATAL: missing {what} in {run} (run did not finish?)")

    (figdir / f"{args.label}.svg").write_text(inline_images(src_svg), encoding="utf-8")
    shutil.copy2(src_pdf, figdir / f"{args.label}.pdf")
    if src_png.exists():
        shutil.copy2(src_png, figdir / f"{args.label}.png")

    print(f"exported: {args.label}.svg (self-contained) + {args.label}.pdf + {args.label}.png -> {figdir}")
    print("next: run  python ../ts-figure-optimize/scripts/check_vector_pdf.py lint "
          f"--svg {figdir}/{args.label}.svg --type <type> --render-check   (shared gate lint)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
