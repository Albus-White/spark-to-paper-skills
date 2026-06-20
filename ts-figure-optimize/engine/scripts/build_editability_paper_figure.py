"""Build a paper-ready figure that visualizes SVG editability.

The figure is intentionally static: it uses the real reconstructed rendering as
the base image and overlays editor-like selection affordances derived from the
semantic SVG object model.
"""

from __future__ import annotations

import argparse
import base64
import html
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE_DIR = (
    REPO_ROOT
    / "runs"
    / "20260607"
    / "204539_aaaaa_full_local"
    / "outputs"
    / "case_001_aaaaa"
)
DEFAULT_OUT_DIR = REPO_ROOT / "figures" / "editability_demo"

CANVAS_W = 3000
CANVAS_H = 1320
BASE_X = 70
BASE_Y = 245
BASE_W = 2048
BASE_H = 1028
PANEL_X = 2190
PANEL_Y = 245
PANEL_W = 740
PANEL_H = 1028

BLUE = "#2563eb"
PURPLE = "#7c3aed"
ORANGE = "#ea580c"
GREEN = "#16a34a"
GRAY = "#6b7280"
INK = "#111827"
MUTED = "#4b5563"
BORDER = "#d1d5db"
BG = "#ffffff"
SOFT = "#f8fafc"


def data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 26,
    weight: int | str = 400,
    fill: str = INK,
    family: str = "Arial, Helvetica, sans-serif",
    anchor: str = "start",
    extra: str = "",
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" {extra}>'
        f"{esc(value)}</text>"
    )


def rect(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fill: str = "none",
    stroke: str = BORDER,
    sw: float = 2,
    rx: float = 0,
    extra: str = "",
) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>'
    )


def selection_box(x: float, y: float, w: float, h: float, color: str) -> str:
    handle = 12
    handle_r = 2
    pieces = [
        rect(
            BASE_X + x,
            BASE_Y + y,
            w,
            h,
            stroke=color,
            sw=4,
            rx=3,
            extra='stroke-dasharray="12 8"',
        )
    ]
    points = [
        (x, y),
        (x + w / 2, y),
        (x + w, y),
        (x, y + h / 2),
        (x + w, y + h / 2),
        (x, y + h),
        (x + w / 2, y + h),
        (x + w, y + h),
    ]
    for px, py in points:
        pieces.append(
            rect(
                BASE_X + px - handle / 2,
                BASE_Y + py - handle / 2,
                handle,
                handle,
                fill=BG,
                stroke=color,
                sw=3,
                rx=handle_r,
            )
        )
    return "\n".join(pieces)


def badge(x: float, y: float, label: str, color: str) -> str:
    cx = BASE_X + x
    cy = BASE_Y + y
    return "\n".join(
        [
            f'<circle cx="{cx}" cy="{cy}" r="21" fill="{color}"/>',
            text(
                cx,
                cy + 9,
                label,
                size=25,
                weight=700,
                fill=BG,
                anchor="middle",
            ),
        ]
    )


def crop_image(
    uri: str,
    crop: tuple[int, int, int, int],
    x: float,
    y: float,
    w: float,
    h: float,
    border_color: str,
) -> str:
    cx, cy, cw, ch = crop
    return "\n".join(
        [
            f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="{cx} {cy} {cw} {ch}" preserveAspectRatio="xMidYMid meet">',
            f'  <image x="0" y="0" width="{BASE_W}" height="{BASE_H}" href="{uri}"/>',
            "</svg>",
            rect(x, y, w, h, stroke=border_color, sw=3, rx=8),
        ]
    )


def metadata_counts(svg_path: Path) -> dict[str, int]:
    root = ET.parse(svg_path).getroot()
    counts = {
        "editable": 0,
        "locked_images": 0,
        "panel": 0,
        "connector": 0,
    }
    for node in root.iter():
        if node.attrib.get("data-pb-editable") == "true":
            counts["editable"] += 1
        if node.tag.endswith("image") and node.attrib.get("data-pb-editable") == "false":
            counts["locked_images"] += 1
        if node.attrib.get("data-pb-role") == "panel":
            counts["panel"] += 1
        if node.attrib.get("data-pb-role") == "connector":
            counts["connector"] += 1
    return counts


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_path = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf"
    )
    return ImageFont.truetype(font_path, size)


def pil_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    value: str,
    *,
    size: int = 26,
    fill: str = INK,
    bold: bool = False,
    anchor: str | None = None,
) -> None:
    draw.text(xy, value, fill=fill, font=load_font(size, bold=bold), anchor=anchor)


def pil_selection_box(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    w: float,
    h: float,
    color: str,
) -> None:
    x += BASE_X
    y += BASE_Y
    draw.rounded_rectangle((x, y, x + w, y + h), radius=3, outline=color, width=4)
    handle = 12
    points = [
        (x, y),
        (x + w / 2, y),
        (x + w, y),
        (x, y + h / 2),
        (x + w, y + h / 2),
        (x, y + h),
        (x + w / 2, y + h),
        (x + w, y + h),
    ]
    for px, py in points:
        draw.rounded_rectangle(
            (
                px - handle / 2,
                py - handle / 2,
                px + handle / 2,
                py + handle / 2,
            ),
            radius=2,
            fill=BG,
            outline=color,
            width=3,
        )


def pil_badge(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    label: str,
    color: str,
) -> None:
    cx = BASE_X + x
    cy = BASE_Y + y
    draw.ellipse((cx - 21, cy - 21, cx + 21, cy + 21), fill=color)
    pil_text(draw, (cx, cy + 1), label, size=25, fill=BG, bold=True, anchor="mm")


def paste_crop(
    canvas: Image.Image,
    source: Image.Image,
    crop: tuple[int, int, int, int],
    box: tuple[int, int, int, int],
    border_color: str,
) -> None:
    x, y, w, h = box
    cx, cy, cw, ch = crop
    piece = source.crop((cx, cy, cx + cw, cy + ch)).convert("RGBA")
    piece = ImageOps.contain(piece, (w, h), Image.Resampling.LANCZOS)
    px = x + (w - piece.width) // 2
    py = y + (h - piece.height) // 2
    canvas.alpha_composite(piece, (px, py))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=8, outline=border_color, width=3)


def pil_callout_row(
    canvas: Image.Image,
    source: Image.Image,
    index: int,
    y: int,
    *,
    color: str,
    title: str,
    main: str,
    detail: str,
    crop: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(canvas)
    row_x = PANEL_X + 28
    row_w = PANEL_W - 56
    crop_x = row_x + 20
    crop_y = y + 26
    crop_w = 258
    crop_h = 126
    text_x = crop_x + crop_w + 28
    badge_x = row_x + row_w - 36
    badge_y = y + 34
    draw.rounded_rectangle((row_x, y, row_x + row_w, y + 178), radius=12, fill=BG, outline=BORDER, width=2)
    draw.rounded_rectangle((row_x, y, row_x + 8, y + 178), radius=4, fill=color)
    paste_crop(canvas, source, crop, (crop_x, crop_y, crop_w, crop_h), color)
    pil_text(draw, (text_x, y + 25), title, size=27, bold=True, fill=color)
    pil_text(draw, (text_x, y + 66), main, size=24, bold=True)
    pil_text(draw, (text_x, y + 103), detail, size=21, fill=MUTED)
    draw.ellipse((badge_x - 21, badge_y - 21, badge_x + 21, badge_y + 21), fill=color)
    pil_text(draw, (badge_x, badge_y + 1), str(index), size=24, bold=True, fill=BG, anchor="mm")


def build_raster(case_dir: Path, out_png: Path, out_pdf: Path) -> None:
    svg_path = case_dir / "svg" / "semantic.svg"
    rendered_path = case_dir / "svg" / "rendered.png"
    source = Image.open(rendered_path).convert("RGBA")
    counts = metadata_counts(svg_path)
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(canvas)

    pil_text(draw, (70, 46), "Editable SVG reconstruction: static object-level evidence", size=44, bold=True)
    pil_text(
        draw,
        (72, 100),
        "Editor-like handles reveal text, formulas, connectors, and grouped shapes as independent SVG objects.",
        size=25,
        fill=MUTED,
    )

    draw.rounded_rectangle((70, 146, 610, 184), radius=19, fill="#eef2ff", outline="#c7d2fe", width=2)
    pil_text(
        draw,
        (96, 154),
        f'{counts["editable"]} editable text/formula elements in semantic.svg',
        size=22,
        bold=True,
        fill="#3730a3",
    )
    draw.rounded_rectangle((630, 146, 1060, 184), radius=19, fill="#f3f4f6", outline="#d1d5db", width=2)
    pil_text(
        draw,
        (656, 154),
        f'{counts["locked_images"]} preserved raster assets are marked separately',
        size=22,
        bold=True,
        fill="#374151",
    )

    pil_text(draw, (BASE_X, BASE_Y - 26), "(a) Reconstructed figure with editable-object overlay", size=25, bold=True)
    draw.rounded_rectangle(
        (BASE_X - 10, BASE_Y - 10, BASE_X + BASE_W + 10, BASE_Y + BASE_H + 10),
        radius=12,
        fill=BG,
        outline=BORDER,
        width=2,
    )
    canvas.alpha_composite(source, (BASE_X, BASE_Y))
    overlay = Image.new("RGBA", (BASE_W, BASE_H), (255, 255, 255, 12))
    canvas.alpha_composite(overlay, (BASE_X, BASE_Y))

    pil_selection_box(draw, 1728, 33, 302, 78, BLUE)
    pil_badge(draw, 1726, 30, "1", BLUE)
    pil_selection_box(draw, 1573, 3, 128, 122, PURPLE)
    pil_badge(draw, 1574, 4, "2", PURPLE)
    pil_selection_box(draw, 1488, 348, 142, 48, ORANGE)
    pil_badge(draw, 1490, 346, "3", ORANGE)
    pil_selection_box(draw, 1717, 163, 302, 74, GREEN)
    pil_badge(draw, 1716, 163, "4", GREEN)
    draw.rounded_rectangle((BASE_X + 318, BASE_Y + 86, BASE_X + 370, BASE_Y + 144), radius=5, outline=GRAY, width=4)
    pil_text(draw, (BASE_X + 345, BASE_Y + 103), "lock", size=23, bold=True, fill=GRAY, anchor="mt")

    pil_text(draw, (PANEL_X, PANEL_Y - 60), "(b) Object-level edit evidence", size=25, bold=True)
    draw.rounded_rectangle(
        (PANEL_X, PANEL_Y - 10, PANEL_X + PANEL_W, PANEL_Y + PANEL_H + 10),
        radius=18,
        fill=SOFT,
        outline=BORDER,
        width=2,
    )
    pil_text(draw, (PANEL_X + 34, PANEL_Y + 21), "Selected SVG objects", size=34, bold=True)
    pil_text(draw, (PANEL_X + 34, PANEL_Y + 64), "Each highlight maps to a real editable element or group.", size=22, fill=MUTED)
    pil_callout_row(
        canvas,
        source,
        1,
        PANEL_Y + 122,
        color=BLUE,
        title="Text object",
        main='content: "Transformer"',
        detail='data-pb-editable="true"',
        crop=(1695, 12, 350, 125),
    )
    pil_callout_row(
        canvas,
        source,
        2,
        PANEL_Y + 318,
        color=PURPLE,
        title="Formula object",
        main="SVG text with subscript spans",
        detail='role="formula"',
        crop=(1532, 0, 235, 140),
    )
    pil_callout_row(
        canvas,
        source,
        3,
        PANEL_Y + 514,
        color=ORANGE,
        title="Connector object",
        main="stroke and arrow marker editable",
        detail='role="connector"',
        crop=(1452, 328, 240, 110),
    )
    pil_callout_row(
        canvas,
        source,
        4,
        PANEL_Y + 710,
        color=GREEN,
        title="Grouped node",
        main="rect + text stay separable",
        detail='role="node"',
        crop=(1688, 142, 355, 128),
    )
    draw.rounded_rectangle(
        (PANEL_X + 28, PANEL_Y + 920, PANEL_X + PANEL_W - 28, PANEL_Y + 1006),
        radius=12,
        fill="#fff7ed",
        outline="#fed7aa",
        width=2,
    )
    pil_text(draw, (PANEL_X + 58, PANEL_Y + 938), "Raster assets are preserved, not overclaimed", size=24, bold=True, fill="#9a3412")
    pil_text(draw, (PANEL_X + 58, PANEL_Y + 972), 'example: data-pb-editable="false"', size=22, fill="#9a3412")
    lock_x = PANEL_X + PANEL_W - 84
    lock_y = PANEL_Y + 943
    draw.rounded_rectangle((lock_x, lock_y, lock_x + 34, lock_y + 28), radius=5, outline="#9a3412", width=4)
    draw.arc((lock_x + 7, lock_y - 18, lock_x + 27, lock_y + 10), start=180, end=360, fill="#9a3412", width=4)

    rgb = canvas.convert("RGB")
    rgb.save(out_png)
    rgb.save(out_pdf, "PDF", resolution=300.0)


def callout_row(
    uri: str,
    index: int,
    y: float,
    *,
    color: str,
    title: str,
    main: str,
    detail: str,
    crop: tuple[int, int, int, int],
) -> str:
    row_x = PANEL_X + 28
    row_w = PANEL_W - 56
    crop_x = row_x + 20
    crop_y = y + 26
    crop_w = 258
    crop_h = 126
    text_x = crop_x + crop_w + 28
    badge_x = row_x + row_w - 36
    badge_y = y + 34
    return "\n".join(
        [
            rect(row_x, y, row_w, 178, fill=BG, stroke=BORDER, sw=2, rx=12),
            f'<rect x="{row_x}" y="{y}" width="8" height="178" rx="4" fill="{color}"/>',
            crop_image(uri, crop, crop_x, crop_y, crop_w, crop_h, color),
            text(text_x, y + 52, title, size=27, weight=700, fill=color),
            text(text_x, y + 90, main, size=24, weight=600),
            text(text_x, y + 126, detail, size=21, fill=MUTED),
            f'<circle cx="{badge_x}" cy="{badge_y}" r="21" fill="{color}"/>',
            text(badge_x, badge_y + 8, str(index), size=24, weight=700, fill=BG, anchor="middle"),
        ]
    )


def build_svg(case_dir: Path, out_svg: Path) -> None:
    svg_path = case_dir / "svg" / "semantic.svg"
    rendered_path = case_dir / "svg" / "rendered.png"
    uri = data_uri(rendered_path)
    counts = metadata_counts(svg_path)

    body: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">',
        "<defs>",
        '  <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">',
        '    <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#111827" flood-opacity="0.14"/>',
        "  </filter>",
        '  <marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">',
        f'    <path d="M 0 0 L 10 5 L 0 10 z" fill="{GRAY}"/>',
        "  </marker>",
        "</defs>",
        rect(0, 0, CANVAS_W, CANVAS_H, fill=BG, stroke="none"),
        text(70, 82, "Editable SVG reconstruction: static object-level evidence", size=44, weight=700),
        text(
            72,
            124,
            "Editor-like handles reveal text, formulas, connectors, and grouped shapes as independent SVG objects.",
            size=25,
            fill=MUTED,
        ),
        rect(70, 146, 540, 38, fill="#eef2ff", stroke="#c7d2fe", sw=2, rx=19),
        text(
            96,
            173,
            f'{counts["editable"]} editable text/formula elements in semantic.svg',
            size=22,
            weight=700,
            fill="#3730a3",
        ),
        rect(630, 146, 430, 38, fill="#f3f4f6", stroke="#d1d5db", sw=2, rx=19),
        text(
            656,
            173,
            f'{counts["locked_images"]} preserved raster assets are marked separately',
            size=22,
            weight=700,
            fill="#374151",
        ),
        text(BASE_X, BASE_Y - 18, "(a) Reconstructed figure with editable-object overlay", size=25, weight=700),
        rect(BASE_X - 10, BASE_Y - 10, BASE_W + 20, BASE_H + 20, fill=BG, stroke=BORDER, sw=2, rx=12, extra='filter="url(#shadow)"'),
        f'<image x="{BASE_X}" y="{BASE_Y}" width="{BASE_W}" height="{BASE_H}" href="{uri}"/>',
        rect(BASE_X, BASE_Y, BASE_W, BASE_H, fill="#ffffff", stroke="none", extra='opacity="0.05"'),
    ]

    # Main overlay selections use source SVG coordinates.
    body.extend(
        [
            selection_box(1728, 33, 302, 78, BLUE),
            badge(1726, 30, "1", BLUE),
            selection_box(1573, 3, 128, 122, PURPLE),
            badge(1574, 4, "2", PURPLE),
            selection_box(1488, 348, 142, 48, ORANGE),
            badge(1490, 346, "3", ORANGE),
            selection_box(1717, 163, 302, 74, GREEN),
            badge(1716, 163, "4", GREEN),
            rect(BASE_X + 318, BASE_Y + 86, 52, 58, stroke=GRAY, sw=4, rx=5, extra='stroke-dasharray="10 8"'),
            text(BASE_X + 345, BASE_Y + 126, "lock", size=23, weight=700, fill=GRAY, anchor="middle"),
        ]
    )

    # Right evidence panel.
    body.extend(
        [
            text(PANEL_X, PANEL_Y - 30, "(b) Object-level edit evidence", size=25, weight=700),
            rect(PANEL_X, PANEL_Y - 10, PANEL_W, PANEL_H + 20, fill=SOFT, stroke=BORDER, sw=2, rx=18, extra='filter="url(#shadow)"'),
            text(PANEL_X + 34, PANEL_Y + 50, "Selected SVG objects", size=34, weight=700),
            text(PANEL_X + 34, PANEL_Y + 88, "Each highlight maps to a real editable element or group.", size=22, fill=MUTED),
            callout_row(
                uri,
                1,
                PANEL_Y + 122,
                color=BLUE,
                title="Text object",
                main='content: "Transformer"',
                detail='data-pb-editable="true"',
                crop=(1695, 12, 350, 125),
            ),
            callout_row(
                uri,
                2,
                PANEL_Y + 318,
                color=PURPLE,
                title="Formula object",
                main="SVG text with subscript spans",
                detail='role="formula"',
                crop=(1532, 0, 235, 140),
            ),
            callout_row(
                uri,
                3,
                PANEL_Y + 514,
                color=ORANGE,
                title="Connector object",
                main="stroke and arrow marker editable",
                detail='role="connector"',
                crop=(1452, 328, 240, 110),
            ),
            callout_row(
                uri,
                4,
                PANEL_Y + 710,
                color=GREEN,
                title="Grouped node",
                main="rect + text stay separable",
                detail='role="node"',
                crop=(1688, 142, 355, 128),
            ),
            rect(PANEL_X + 28, PANEL_Y + 920, PANEL_W - 56, 86, fill="#fff7ed", stroke="#fed7aa", sw=2, rx=12),
            text(PANEL_X + 58, PANEL_Y + 954, "Raster assets are preserved, not overclaimed", size=24, weight=700, fill="#9a3412"),
            text(PANEL_X + 58, PANEL_Y + 988, 'example: data-pb-editable="false"', size=22, fill="#9a3412"),
            rect(PANEL_X + PANEL_W - 84, PANEL_Y + 943, 34, 28, fill="none", stroke="#9a3412", sw=4, rx=5),
            f'<path d="M {PANEL_X + PANEL_W - 77} {PANEL_Y + 943} C {PANEL_X + PANEL_W - 77} {PANEL_Y + 925}, {PANEL_X + PANEL_W - 57} {PANEL_Y + 925}, {PANEL_X + PANEL_W - 57} {PANEL_Y + 943}" fill="none" stroke="#9a3412" stroke-width="4" stroke-linecap="round"/>',
        ]
    )

    body.append("</svg>")
    out_svg.write_text("\n".join(body), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--stem", default="editable_svg_paper_figure")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_svg = args.out_dir / f"{args.stem}.svg"
    out_png = args.out_dir / f"{args.stem}.png"
    out_pdf = args.out_dir / f"{args.stem}.pdf"

    build_svg(args.case_dir, out_svg)
    build_raster(args.case_dir, out_png, out_pdf)

    print(out_svg)
    print(out_png)
    print(out_pdf)


if __name__ == "__main__":
    main()
