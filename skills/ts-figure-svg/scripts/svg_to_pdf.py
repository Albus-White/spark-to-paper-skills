#!/usr/bin/env python3
"""svg_to_pdf.py — native SVG -> vector PDF for \\includegraphics, whichever backend the box has.

Tries rsvg-convert, inkscape, a headless browser, then cairosvg. Fails loudly rather than emitting a
rasterised PDF: the figure's whole point is that its text stays vector and extractable.

  python3 svg_to_pdf.py fig.svg fig.pdf
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _try(cmd, timeout=180) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# Ladder order is evidence-based, not alphabetical. Inkscape's SVG->PDF outlined every glyph even with
# --export-text-to-path=false: pdffonts came back EMPTY and it scored RMSE 0.127 against the reference
# render, while the browser's page.pdf kept four embedded font subsets and scored 0.087. So Inkscape is
# last before cairosvg, and `is_vector` below demands /Font rather than merely "no raster".
def _backends(svg: Path, pdf: Path):
    if shutil.which("rsvg-convert"):
        yield "rsvg-convert", ["rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg)]
    for b in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser"):
        exe = shutil.which(b)
        if exe:
            yield b, [exe, "--headless=new", "--disable-gpu", "--no-sandbox",
                      f"--print-to-pdf={pdf}", "--no-pdf-header-footer", svg.resolve().as_uri()]
    ink = shutil.which("inkscape")
    if ink:
        yield "inkscape", [ink, str(svg), "--export-type=pdf", "--export-text-to-path=false",
                           f"--export-filename={pdf}"]


def convert(svg: Path, pdf: Path) -> str:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    tried = []
    for name, cmd in _backends(svg, pdf):
        if _try(cmd) and pdf.exists():
            ok, _ = is_vector(pdf)
            if ok:
                return name
            tried.append(f"{name} (outlined the text)")
            pdf.unlink(missing_ok=True)
        else:
            tried.append(f"{name} (failed)")
    try:
        import cairosvg
        cairosvg.svg2pdf(url=str(svg), write_to=str(pdf))
        return "cairosvg"
    except Exception:  # noqa: BLE001
        tried.append("cairosvg (absent or failed)")
    raise SystemExit(
        f"no SVG->PDF backend produced a text-preserving PDF (tried: {', '.join(tried) or 'none'}). "
        f"Install one:  apt install librsvg2-bin  (rsvg-convert, smallest)  |  a headless Chrome  |  "
        f"apt install inkscape  |  pip install cairosvg")


def is_vector(pdf: Path) -> tuple[bool, str]:
    """A figure PDF must keep LIVE TEXT, so /Font is the test — not merely "no raster".

    An exporter that converts every glyph to a path yields zero raster objects AND zero fonts, which a
    naive `pdfimages -list is empty` check reads as a clean vector. It is not: the labels stop being
    text, `pdftotext` finds nothing on the figure, and nobody can edit it again.
    """
    d = pdf.read_bytes()
    images = d.count(b"/Subtype /Image") + d.count(b"/Subtype/Image")
    fonts = b"/Font" in d
    if not fonts:
        return False, ("no /Font — every glyph was outlined to paths; the labels are no longer text "
                       "(verify with `pdffonts`, which will print an empty table)")
    if images == 0:
        return True, "vector text, no embedded raster"
    return True, f"vector text + {images} embedded raster(s)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svg")
    ap.add_argument("pdf")
    a = ap.parse_args()
    svg, pdf = Path(a.svg), Path(a.pdf)
    if not svg.is_file():
        print(f"no such file: {svg}", file=sys.stderr)
        return 2
    backend = convert(svg, pdf)
    ok, why = is_vector(pdf)
    print(f"{'ok' if ok else 'FAIL'}  {pdf}  via {backend} — {why}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
