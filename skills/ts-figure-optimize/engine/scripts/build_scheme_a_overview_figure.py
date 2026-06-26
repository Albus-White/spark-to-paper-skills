"""Build a Scheme-A overview figure from a real DrawAI case.

This is intended as a first-figure concept: raster input -> semantic editable
SVG reconstruction -> editable SVG/PPT outputs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

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
DEFAULT_OUT_DIR = REPO_ROOT / "figures" / "overview_scheme_a"

CANVAS_W = 3600
CANVAS_H = 1500

INK = "#111827"
MUTED = "#4b5563"
LIGHT = "#f8fafc"
BORDER = "#d1d5db"
BG = "#ffffff"
BLUE = "#2563eb"
PURPLE = "#7c3aed"
ORANGE = "#ea580c"
GREEN = "#16a34a"
GRAY = "#6b7280"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf"
    )
    return ImageFont.truetype(path, size)


def text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    value: str,
    *,
    size: int = 28,
    fill: str = INK,
    bold: bool = False,
    anchor: str | None = None,
) -> None:
    draw.text(xy, value, font=font(size, bold=bold), fill=fill, anchor=anchor)


def card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str = BG,
    outline: str = BORDER,
    width: int = 3,
    radius: int = 24,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def paste_contained(
    canvas: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
    *,
    bg: str = BG,
) -> tuple[int, int, int, int, float]:
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=12, fill=bg)
    thumb = ImageOps.contain(source, (w, h), Image.Resampling.LANCZOS)
    px = x0 + (w - thumb.width) // 2
    py = y0 + (h - thumb.height) // 2
    canvas.alpha_composite(thumb.convert("RGBA"), (px, py))
    scale = thumb.width / source.width
    return px, py, thumb.width, thumb.height, scale


def handles(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    color: str,
    *,
    width: int = 5,
    handle: int = 14,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=5, outline=color, width=width)
    pts = [
        (x0, y0),
        ((x0 + x1) / 2, y0),
        (x1, y0),
        (x0, (y0 + y1) / 2),
        (x1, (y0 + y1) / 2),
        (x0, y1),
        ((x0 + x1) / 2, y1),
        (x1, y1),
    ]
    for px, py in pts:
        draw.rounded_rectangle(
            (px - handle / 2, py - handle / 2, px + handle / 2, py + handle / 2),
            radius=3,
            fill=BG,
            outline=color,
            width=3,
        )


def source_box_to_dest(
    placed: tuple[int, int, int, int, float],
    source_box: tuple[int, int, int, int],
) -> tuple[float, float, float, float]:
    px, py, _w, _h, scale = placed
    sx, sy, sw, sh = source_box
    return px + sx * scale, py + sy * scale, px + (sx + sw) * scale, py + (sy + sh) * scale


def draw_scaled_selection(
    draw: ImageDraw.ImageDraw,
    placed: tuple[int, int, int, int, float],
    source_box: tuple[int, int, int, int],
    color: str,
    *,
    label: str | None = None,
) -> None:
    box = source_box_to_dest(placed, source_box)
    handles(draw, box, color, width=4, handle=12)
    if label:
        x0, y0, _x1, _y1 = box
        draw.ellipse((x0 - 24, y0 - 24, x0 + 24, y0 + 24), fill=color)
        text(draw, (x0, y0 + 1), label, size=24, fill=BG, bold=True, anchor="mm")


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = "#94a3b8",
    label: str = "",
) -> None:
    draw.line((start, end), fill=color, width=8)
    ex, ey = end
    sx, sy = start
    direction = 1 if ex >= sx else -1
    draw.polygon(
        [
            (ex, ey),
            (ex - direction * 30, ey - 18),
            (ex - direction * 30, ey + 18),
        ],
        fill=color,
    )
    if label:
        text(draw, ((sx + ex) / 2, sy - 42), label, size=25, fill=MUTED, bold=True, anchor="mm")


def tag(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    color: str,
    *,
    w: int = 190,
) -> None:
    draw.rounded_rectangle((x, y, x + w, y + 46), radius=23, fill="#ffffff", outline=color, width=3)
    draw.ellipse((x + 18, y + 15, x + 34, y + 31), fill=color)
    text(draw, (x + 48, y + 31), label, size=24, fill=INK, bold=True, anchor="lm")


def pixel_cue(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    colors = ["#e5e7eb", "#cbd5e1", "#94a3b8", "#64748b"]
    size = 24
    for row in range(4):
        for col in range(4):
            draw.rectangle(
                (x + col * size, y + row * size, x + (col + 1) * size - 2, y + (row + 1) * size - 2),
                fill=colors[(row + col) % len(colors)],
            )


def draw_output_window(
    canvas: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
    title: str,
    selections: list[tuple[tuple[int, int, int, int], str]],
) -> None:
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    card(draw, box, fill=BG, radius=18)
    draw.rounded_rectangle((x0, y0, x1, y0 + 58), radius=18, fill="#f1f5f9", outline=BORDER, width=0)
    draw.ellipse((x0 + 26, y0 + 22, x0 + 42, y0 + 38), fill="#ef4444")
    draw.ellipse((x0 + 52, y0 + 22, x0 + 68, y0 + 38), fill="#f59e0b")
    draw.ellipse((x0 + 78, y0 + 22, x0 + 94, y0 + 38), fill="#22c55e")
    text(draw, (x0 + 116, y0 + 39), title, size=26, bold=True, fill=INK, anchor="lm")
    placed = paste_contained(canvas, source, (x0 + 24, y0 + 84, x1 - 24, y1 - 24), bg="#ffffff")
    for source_box, color in selections:
        draw_scaled_selection(draw, placed, source_box, color)


def build_figure(case_dir: Path, out_png: Path, out_pdf: Path) -> None:
    input_img = Image.open(case_dir / "inputs" / "original.png").convert("RGBA")
    rendered_img = Image.open(case_dir / "svg" / "rendered.png").convert("RGBA")

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(canvas)

    text(draw, (90, 70), "DrawAI: from raster scientific figures to editable SVG/PPTX", size=50, bold=True)
    text(
        draw,
        (92, 123),
        "A raster diagram is reconstructed as a semantic vector object graph, then edited through standard document tools.",
        size=28,
        fill=MUTED,
    )

    left = (90, 250, 740, 1110)
    middle = (900, 215, 2315, 1145)
    right = (2500, 215, 3510, 1145)

    card(draw, left, fill=LIGHT)
    text(draw, (left[0] + 34, left[1] + 58), "(a) Raster input", size=34, bold=True)
    text(draw, (left[0] + 34, left[1] + 96), "Image-only scientific figure", size=24, fill=MUTED)
    input_placed = paste_contained(canvas, input_img, (left[0] + 36, left[1] + 150, left[2] - 36, left[1] + 505))
    draw.rounded_rectangle(
        (input_placed[0], input_placed[1], input_placed[0] + input_placed[2], input_placed[1] + input_placed[3]),
        radius=10,
        outline="#cbd5e1",
        width=3,
    )
    pixel_cue(draw, left[0] + 52, left[1] + 560)
    text(draw, (left[0] + 176, left[1] + 604), "Pixels only", size=30, bold=True, fill=INK, anchor="lm")
    text(draw, (left[0] + 52, left[1] + 685), "Text, arrows, and formulas are locked inside the bitmap.", size=26, fill=MUTED)
    text(draw, (left[0] + 52, left[1] + 750), "No object handles", size=26, fill=GRAY, bold=True)
    text(draw, (left[0] + 52, left[1] + 790), "No direct PPT editing", size=26, fill=GRAY, bold=True)

    arrow(draw, (780, 682), (870, 682), label="reconstruct")

    card(draw, middle, fill=BG)
    text(draw, (middle[0] + 34, middle[1] + 58), "(b) Semantic editable reconstruction", size=34, bold=True)
    text(draw, (middle[0] + 34, middle[1] + 96), "Visual fidelity plus object-level structure", size=24, fill=MUTED)
    reconstruction_placed = paste_contained(
        canvas,
        rendered_img,
        (middle[0] + 40, middle[1] + 138, middle[2] - 40, middle[1] + 805),
    )
    draw.rounded_rectangle(
        (
            reconstruction_placed[0],
            reconstruction_placed[1],
            reconstruction_placed[0] + reconstruction_placed[2],
            reconstruction_placed[1] + reconstruction_placed[3],
        ),
        radius=10,
        outline="#cbd5e1",
        width=3,
    )
    draw_scaled_selection(draw, reconstruction_placed, (1728, 33, 302, 78), BLUE, label="T")
    draw_scaled_selection(draw, reconstruction_placed, (1573, 3, 128, 122), PURPLE, label="F")
    draw_scaled_selection(draw, reconstruction_placed, (1488, 348, 142, 48), ORANGE, label="C")
    draw_scaled_selection(draw, reconstruction_placed, (1717, 163, 302, 74), GREEN, label="G")
    tag(draw, middle[0] + 58, middle[1] + 840, "Text", BLUE, w=160)
    tag(draw, middle[0] + 246, middle[1] + 840, "Formula", PURPLE, w=190)
    tag(draw, middle[0] + 464, middle[1] + 840, "Connector", ORANGE, w=220)
    tag(draw, middle[0] + 712, middle[1] + 840, "Shape", GREEN, w=170)
    tag(draw, middle[0] + 904, middle[1] + 840, "Image asset", GRAY, w=230)

    arrow(draw, (2355, 682), (2470, 682), label="export / edit")

    card(draw, right, fill=LIGHT)
    text(draw, (right[0] + 34, right[1] + 58), "(c) Editable outputs", size=34, bold=True)
    text(draw, (right[0] + 34, right[1] + 96), "Same figure, exposed through standard editing surfaces", size=24, fill=MUTED)
    draw_output_window(
        canvas,
        rendered_img,
        (right[0] + 36, right[1] + 142, right[0] + 486, right[1] + 570),
        "SVG editor",
        [((1728, 33, 302, 78), BLUE), ((1573, 3, 128, 122), PURPLE)],
    )
    draw_output_window(
        canvas,
        rendered_img,
        (right[0] + 526, right[1] + 142, right[2] - 36, right[1] + 570),
        "PowerPoint",
        [((1717, 163, 302, 74), GREEN), ((1488, 348, 142, 48), ORANGE)],
    )
    text(draw, (right[0] + 56, right[1] + 662), "Object-level edits enabled", size=31, bold=True)
    tag(draw, right[0] + 56, right[1] + 708, "Edit text", BLUE, w=210)
    tag(draw, right[0] + 296, right[1] + 708, "Move arrows", ORANGE, w=230)
    tag(draw, right[0] + 536, right[1] + 708, "Restyle shapes", GREEN, w=250)
    tag(draw, right[0] + 56, right[1] + 775, "SVG", "#0f766e", w=150)
    tag(draw, right[0] + 226, right[1] + 775, "PPTX", "#be123c", w=170)
    tag(draw, right[0] + 426, right[1] + 775, "Preserved assets", GRAY, w=275)

    draw.rounded_rectangle((90, 1225, 3510, 1328), radius=24, fill="#f8fafc", outline="#e2e8f0", width=3)
    text(
        draw,
        (125, 1267),
        "Output artifacts:",
        size=28,
        bold=True,
        fill=INK,
        anchor="lm",
    )
    text(
        draw,
        (360, 1267),
        "semantic.svg  +  editable PPTX",
        size=30,
        bold=True,
        fill="#0f172a",
        anchor="lm",
    )
    text(
        draw,
        (920, 1267),
        "Text, formulas, connectors, and grouped shapes remain independently selectable after reconstruction.",
        size=26,
        fill=MUTED,
        anchor="lm",
    )

    rgb = canvas.convert("RGB")
    rgb.save(out_png)
    rgb.save(out_pdf, "PDF", resolution=300.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--stem", default="drawai_scheme_a_overview")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_png = args.out_dir / f"{args.stem}.png"
    out_pdf = args.out_dir / f"{args.stem}.pdf"
    build_figure(args.case_dir, out_png, out_pdf)
    print(out_png)
    print(out_pdf)


if __name__ == "__main__":
    main()
