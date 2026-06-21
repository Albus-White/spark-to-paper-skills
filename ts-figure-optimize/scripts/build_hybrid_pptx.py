#!/usr/bin/env python3
"""build_hybrid_pptx.py — HIGH-FIDELITY HYBRID export: pixel-exact graphics + editable text.

Mechanism (deterministic, NO LLM/Codex — fast & cheap): keep the source figure's GRAPHICS as a
pixel-exact raster with the text removed, and re-create every OCR'd text run as a genuinely editable
PPTX text box (and selectable PDF/SVG text) placed/coloured/sized to match. This reaches ~0.90 SSIM —
the editable-redraw ceiling — with ZERO text doubling/offset, because the only re-rendered pixels are
the text (graphics are the original). It is strictly better than a full LLM redraw for "faithful +
editable text" (full redraw ~0.67-0.8), at near-zero cost.

Trade-off (honest): graphics (boxes/arrows/icons/matrices/waveforms) stay raster (not vector-editable);
only TEXT is editable. 0.95+ is NOT reachable with re-typed text (font/AA/sub-pixel) — that needs keeping
the original text pixels (not editable). See SKILL.md "High-fidelity hybrid export".

RESOLUTION-ADAPTIVE: OCR/box bboxes are scaled from the box_ir CANVAS space to the actual SOURCE pixel
space at runtime (sx = W_src/canvas.width, sy = H_src/canvas.height), so any input resolution works as
long as ocr_boxes.json + box_ir.json come from the same pipeline run. (Skipping this scale is exactly
what causes text duplication/offset.)

Usage:
  python build_hybrid_pptx.py --source S.png --ocr ocr_boxes.json [--box-ir box_ir.json] \
      --out-pptx editable_hybrid.pptx [--out-pdf editable_hybrid.pdf] [--out-svg editable_hybrid.svg] \
      [--out-bg _hybrid_bg.png] [--report hybrid_report.json] [--font /path/to/Sans.ttf]
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/**/Arial.ttf",
    "/usr/share/fonts/**/*Sans*.ttf",
]


def find_font(explicit: str | None) -> str:
    if explicit and Path(explicit).exists():
        return explicit
    for pat in FONT_CANDIDATES:
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    raise SystemExit("FATAL: no usable .ttf font found; pass --font /path/to/Sans.ttf")


def load_ocr_boxes(path: str) -> list[dict]:
    d = json.loads(Path(path).read_text())
    if isinstance(d, dict):
        for k in ("ocr_text_boxes", "boxes", "text_boxes"):
            if isinstance(d.get(k), list):
                return d[k]
    return d if isinstance(d, list) else []


def canvas_scale(box_ir: str | None, W: int, H: int) -> tuple[float, float]:
    if box_ir and Path(box_ir).exists():
        cv = json.loads(Path(box_ir).read_text()).get("canvas", {})
        cw, ch = cv.get("width"), cv.get("height")
        if cw and ch:
            return W / float(cw), H / float(ch)
    return 1.0, 1.0


def build(source: str, ocr: str, box_ir: str | None, font_path: str):
    src = Image.open(source).convert("RGB")
    W, H = src.size
    arr = np.asarray(src).astype(np.int16)
    orig = np.asarray(src)
    sx, sy = canvas_scale(box_ir, W, H)
    boxes = load_ocr_boxes(ocr)
    meas = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    out = orig.copy()
    runs: list[dict] = []
    for b in boxes:
        bb = b.get("bbox") or b.get("box")
        if not bb or len(bb) < 4:
            continue
        x1, y1, x2, y2 = bb[0] * sx, bb[1] * sy, bb[2] * sx, bb[3] * sy
        x1, x2 = sorted((int(max(0, min(W, x1))), int(max(0, min(W, x2)))))
        y1, y2 = sorted((int(max(0, min(H, y1))), int(max(0, min(H, y2)))))
        if x2 - x1 < 3 or y2 - y1 < 3:
            continue
        reg = arr[y1:y2, x1:x2]
        lum = reg.mean(2)
        bgc = np.median(reg[lum >= np.percentile(lum, 60)].reshape(-1, 3), axis=0)
        bglum = float(bgc.mean())
        dist = np.sqrt(((reg - bgc) ** 2).sum(2))
        ink = (lum < bglum - 22) | (dist > 60)          # text ink: darker than bg OR clearly coloured
        if ink.sum() < 4:
            continue
        out[y1:y2, x1:x2][ink] = bgc.astype(np.uint8)   # erase text from the graphics background
        # colour from CENTRAL vertical band (avoids graphics intruding at the box's top/bottom edges)
        hh = y2 - y1
        ry1, ry2 = int(hh * 0.22), max(int(hh * 0.78), 1)
        cb = orig[y1 + ry1:y1 + ry2, x1:x2]
        cbink = ink[ry1:ry2]
        px = cb[cbink] if cbink.any() else orig[y1:y2, x1:x2][ink]
        pl = px.mean(1)
        core = px[pl <= np.percentile(pl, 30)] if len(px) > 6 else px
        col = tuple(int(v) for v in np.median(core, axis=0))
        txt = (b.get("text") or "").strip()
        if not txt:
            continue
        fh = max(8, int(hh * 0.86))
        while fh > 6:
            f = ImageFont.truetype(font_path, fh)
            gb = f.getbbox(txt)
            if (gb[3] - gb[1]) <= hh * 1.02 and meas.textlength(txt, font=f) <= (x2 - x1) * 1.06:
                break
            fh -= 1
        runs.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "txt": txt, "col": col, "fh": fh})
    return src, Image.fromarray(out), runs, (W, H)


def write_pptx(bg_path: str, runs: list[dict], W: int, H: int, out_pptx: str) -> None:
    from pptx import Presentation
    from pptx.util import Emu, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR
    EMU = 914400 / 96.0
    prs = Presentation()
    prs.slide_width = Emu(int(W * EMU))
    prs.slide_height = Emu(int(H * EMU))
    sl = prs.slides.add_slide(prs.slide_layouts[6])
    sl.shapes.add_picture(bg_path, Emu(0), Emu(0), Emu(int(W * EMU)), Emu(int(H * EMU)))
    for r in runs:
        tx = sl.shapes.add_textbox(Emu(int(r["x1"] * EMU)), Emu(int(r["y1"] * EMU)),
                                   Emu(int((r["x2"] - r["x1"]) * EMU)), Emu(int((r["y2"] - r["y1"]) * EMU)))
        tf = tx.text_frame
        tf.word_wrap = False
        for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            setattr(tf, m, Emu(0))
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        run = tf.paragraphs[0].add_run()
        run.text = r["txt"]
        run.font.size = Pt(r["fh"] * 0.75)
        run.font.name = "Arial"
        run.font.color.rgb = RGBColor(*r["col"])
    prs.save(out_pptx)


def write_svg_pdf(bg_path: str, runs: list[dict], W: int, H: int,
                  out_svg: str | None, out_pdf: str | None) -> str:
    esc = html.escape
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             f'<image x="0" y="0" width="{W}" height="{H}" xlink:href="file://{os.path.abspath(bg_path)}"/>']
    for r in runs:
        ymid = (r["y1"] + r["y2"]) / 2
        c = "#%02x%02x%02x" % tuple(r["col"])
        parts.append(f'<text x="{r["x1"]}" y="{ymid + r["fh"] * 0.34:.1f}" '
                     f'font-family="Arial, Liberation Sans, sans-serif" font-size="{r["fh"]}" '
                     f'fill="{c}">{esc(r["txt"])}</text>')
    parts.append("</svg>")
    svg = "".join(parts)
    if out_svg:
        Path(out_svg).write_text(svg)
    if out_pdf:
        import cairosvg
        cairosvg.svg2pdf(bytestring=svg.encode(), write_to=out_pdf, unsafe=True)
    return svg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--box-ir", default="")
    ap.add_argument("--out-pptx", required=True)
    ap.add_argument("--out-pdf", default="")
    ap.add_argument("--out-svg", default="")
    ap.add_argument("--out-bg", default="")
    ap.add_argument("--report", default="")
    ap.add_argument("--font", default="")
    a = ap.parse_args()

    font_path = find_font(a.font or None)
    for p in (a.out_pptx, a.out_pdf, a.out_svg, a.out_bg, a.report):
        if p:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
    src, bg, runs, (W, H) = build(a.source, a.ocr, a.box_ir or None, font_path)
    bg_path = a.out_bg or (str(Path(a.out_pptx).with_suffix("")) + "_bg.png")
    Path(bg_path).parent.mkdir(parents=True, exist_ok=True)
    bg.save(bg_path)

    write_pptx(bg_path, runs, W, H, a.out_pptx)
    if a.out_pdf or a.out_svg:
        write_svg_pdf(bg_path, runs, W, H, a.out_svg or None, a.out_pdf or None)

    report = {"source_size": [W, H], "text_runs": len(runs), "font": font_path,
              "outputs": {"pptx": a.out_pptx, "pdf": a.out_pdf, "svg": a.out_svg, "bg": bg_path}}
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"hybrid: {len(runs)} editable text boxes + 1 graphics picture -> {a.out_pptx}"
          + (f", {a.out_pdf}" if a.out_pdf else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
