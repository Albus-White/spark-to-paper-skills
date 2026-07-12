#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont


CATEGORY_COLORS = {
    "svg_self_draw": "#13a563",
    "crop": "#f59e0b",
    "crop_nobg": "#2563eb",
    "imagegen": "#d946ef",
    "unknown": "#64748b",
}

ACTION_COLORS = {
    "unchanged": "#2563eb",
    "adjusted": "#f59e0b",
    "split": "#8b5cf6",
    "added": "#ef4444",
    "agent_refined": "#0891b2",
    "user_confirmed": "#16a34a",
    "unknown": "#64748b",
}

CATEGORY_ALIASES = {
    "native_svg": "svg_self_draw",
    "svg": "svg_self_draw",
    "svg_direct": "svg_self_draw",
    "self_draw": "svg_self_draw",
    "crop_asset": "crop",
    "direct_crop": "crop",
    "preserve_crop": "crop",
    "crop_no_bg": "crop_nobg",
    "crop_without_background": "crop_nobg",
    "without_background": "crop_nobg",
    "transparent_subject": "crop_nobg",
    "remove_background": "crop_nobg",
    "rmbg": "crop_nobg",
    "image_gen": "imagegen",
    "image_generation": "imagegen",
    "generated_image": "imagegen",
}


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    image_path = Path(args.image).expanduser().resolve(strict=False)
    json_path = Path(args.json_path).expanduser().resolve(strict=False)
    output_path = (
        Path(args.output).expanduser().resolve(strict=False)
        if args.output
        else json_path.with_name(f"{json_path.stem}_assets_visualization.png")
    )
    summary_output = Path(args.summary_output).expanduser().resolve(strict=False) if args.summary_output else None
    result = render_assets_visualization(
        image_path=image_path,
        json_path=json_path,
        output_path=output_path,
        summary_output=summary_output,
        color_mode=args.color_mode,
        label_mode=args.label_mode,
        line_width=args.line_width,
        fill_alpha=args.fill_alpha,
        title=args.title,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draw asset/refined element bboxes from a JSON file onto a source image.")
    parser.add_argument("--image", required=True, help="Source image path, for example inputs/figure.png.")
    parser.add_argument("--json", dest="json_path", required=True, help="JSON file containing elements/items/boxes with bbox.")
    parser.add_argument("--output", default="", help="PNG output path. Defaults to JSON_DIR/JSON_STEM_assets_visualization.png.")
    parser.add_argument(
        "--summary-output",
        default="",
        help="Optional JSON summary output path with counts and skipped records.",
    )
    parser.add_argument(
        "--color-mode",
        choices=("auto", "category", "action", "type"),
        default="auto",
        help="auto uses category when available, otherwise refinement_action.",
    )
    parser.add_argument(
        "--label-mode",
        choices=("id", "id_type", "id_category", "none"),
        default="id",
        help="Text label drawn near each box.",
    )
    parser.add_argument("--line-width", type=int, default=4, help="Outline width in pixels.")
    parser.add_argument("--fill-alpha", type=int, default=36, help="Box fill alpha, 0 disables fill.")
    parser.add_argument("--title", default="", help="Optional title drawn in the top-left corner.")
    parsed = parser.parse_args(argv)
    if parsed.line_width <= 0:
        parser.error("--line-width must be positive")
    if not 0 <= parsed.fill_alpha <= 255:
        parser.error("--fill-alpha must be between 0 and 255")
    return parsed


def render_assets_visualization(
    *,
    image_path: Path,
    json_path: Path,
    output_path: Path,
    summary_output: Path | None,
    color_mode: str,
    label_mode: str,
    line_width: int,
    fill_alpha: int,
    title: str,
) -> dict[str, Any]:
    payload = read_json(json_path)
    records = extract_records(payload)
    image = Image.open(image_path).convert("RGBA")
    drawable_records = []
    skipped = 0
    for index, record in enumerate(records):
        bbox = bbox_from_record(record)
        if bbox is None:
            skipped += 1
            continue
        drawable_records.append(normalize_drawable_record(record, index=index, bbox=bbox, color_mode=color_mode, label_mode=label_mode))

    if not drawable_records:
        raise ValueError(f"No drawable records found in {json_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = draw_records(
        image,
        drawable_records,
        line_width=line_width,
        fill_alpha=fill_alpha,
        title=title,
    )
    canvas.convert("RGB").save(output_path)

    summary = {
        "schema": "drawai.assets_visualization_summary.v1",
        "image_path": str(image_path),
        "json_path": str(json_path),
        "output_path": str(output_path),
        "record_count": len(records),
        "drawn_count": len(drawable_records),
        "skipped_count": skipped,
        "color_mode": color_mode,
        "label_mode": label_mode,
        "category_counts": dict(sorted(Counter(item["category"] for item in drawable_records).items())),
        "action_counts": dict(sorted(Counter(item["action"] for item in drawable_records).items())),
    }
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary["summary_output"] = str(summary_output)
    return summary


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_records(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        raise ValueError("assets JSON must be an object or array")
    for key in ("elements", "items", "boxes", "records", "candidates"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    nested = payload.get("element_analysis") or payload.get("assets")
    if isinstance(nested, (Mapping, list)):
        return extract_records(nested)
    raise ValueError("assets JSON must contain elements/items/boxes/records/candidates")


def bbox_from_record(record: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    for key in ("bbox", "box", "bounds", "rect"):
        raw_bbox = record.get(key)
        bbox = (
            normalize_xywh_bbox(raw_bbox, allow_line=True)
            if is_element_plan_record(record)
            else normalize_bbox(raw_bbox, allow_line=True)
        )
        if bbox is not None:
            return bbox
    x = number(record.get("x"))
    y = number(record.get("y"))
    width = number(record.get("width") or record.get("w"))
    height = number(record.get("height") or record.get("h"))
    if x is not None and y is not None and width is not None and height is not None:
        return normalize_bbox([x, y, x + width, y + height], allow_line=True)
    return None


def is_element_plan_record(record: Mapping[str, Any]) -> bool:
    schema = text(record.get("schema"))
    if schema == "drawai.element_plan.v1":
        return True
    return bool(record.get("processing_intent")) and bool(record.get("element_id")) and bool(record.get("element_type"))


def normalize_xywh_bbox(raw: Any, *, allow_line: bool) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        left, top, width, height = [float(item) for item in raw]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in (left, top, width, height)):
        return None
    if allow_line:
        if width == 0:
            left -= 0.5
            width = 1.0
        if height == 0:
            top -= 0.5
            height = 1.0
    if width <= 0 or height <= 0:
        return None
    return left, top, left + width, top + height


def normalize_bbox(raw: Any, *, allow_line: bool) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(item) for item in raw]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in (x1, y1, x2, y2)):
        return None
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    if allow_line:
        if right == left:
            left -= 0.5
            right += 0.5
        if bottom == top:
            top -= 0.5
            bottom += 0.5
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize_drawable_record(
    record: Mapping[str, Any],
    *,
    index: int,
    bbox: tuple[float, float, float, float],
    color_mode: str,
    label_mode: str,
) -> dict[str, Any]:
    element_id = text(record.get("box_id") or record.get("element_id") or record.get("id") or record.get("asset_id")) or f"E{index + 1:03d}"
    intent = record.get("processing_intent")
    processing_type = intent.get("processing_type") if isinstance(intent, Mapping) else ""
    category = normalize_category(
        record.get("category") or record.get("method") or record.get("current_pipeline_method") or processing_type
    )
    action = normalize_action(record.get("refinement_action") or record.get("action") or record.get("review_status"))
    element_type = text(record.get("type") or record.get("element_type") or record.get("role") or "")
    color = record_color(record, category=category, action=action, color_mode=color_mode)
    return {
        "id": element_id,
        "bbox": bbox,
        "category": category,
        "action": action,
        "type": element_type,
        "color": color,
        "label": record_label(element_id, element_type, category, action, label_mode),
    }


def normalize_category(value: Any) -> str:
    raw = text(value).lower().replace("-", "_")
    raw = CATEGORY_ALIASES.get(raw, raw)
    return raw if raw in CATEGORY_COLORS else "unknown"


def normalize_action(value: Any) -> str:
    raw = text(value).lower().replace("-", "_")
    return raw if raw in ACTION_COLORS else "unknown"


def record_color(record: Mapping[str, Any], *, category: str, action: str, color_mode: str) -> str:
    explicit_color = text(record.get("color") or record.get("stroke"))
    if explicit_color.startswith("#") and len(explicit_color) in {4, 7}:
        return explicit_color
    if color_mode == "category":
        return CATEGORY_COLORS.get(category, CATEGORY_COLORS["unknown"])
    if color_mode == "action":
        return ACTION_COLORS.get(action, ACTION_COLORS["unknown"])
    if color_mode == "type":
        return color_from_text(text(record.get("type") or record.get("element_type") or "unknown"))
    if category != "unknown":
        return CATEGORY_COLORS[category]
    return ACTION_COLORS.get(action, ACTION_COLORS["unknown"])


def color_from_text(value: str) -> str:
    palette = ("#2563eb", "#dc2626", "#f59e0b", "#16a34a", "#8b5cf6", "#0891b2", "#be185d", "#64748b")
    return palette[sum(ord(ch) for ch in value) % len(palette)]


def record_label(element_id: str, element_type: str, category: str, action: str, label_mode: str) -> str:
    if label_mode == "none":
        return ""
    if label_mode == "id_type":
        return f"{element_id} {element_type}".strip()
    if label_mode == "id_category":
        value = category if category != "unknown" else action
        return f"{element_id} {value}".strip()
    return element_id


def text(value: Any) -> str:
    return str(value or "").strip()


def draw_records(
    image: Image.Image,
    records: list[dict[str, Any]],
    *,
    line_width: int,
    fill_alpha: int,
    title: str,
) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(18)
    for record in records:
        draw_box(
            draw,
            record["bbox"],
            record["color"],
            record["label"],
            font=font,
            width=line_width,
            fill_alpha=fill_alpha,
        )
    result = Image.alpha_composite(image, overlay)
    if title:
        draw_title(result, title)
    return result


def draw_box(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[float, float, float, float],
    color: str,
    label: str,
    *,
    font: ImageFont.ImageFont,
    width: int,
    fill_alpha: int,
) -> None:
    xy = [int(round(item)) for item in bbox]
    outline = hex_to_rgba(color, 235)
    fill = hex_to_rgba(color, fill_alpha)
    draw.rectangle(xy, outline=outline, width=width, fill=fill)
    if not label:
        return
    label_bbox = draw.textbbox((0, 0), label, font=font)
    label_w = label_bbox[2] - label_bbox[0] + 8
    label_h = label_bbox[3] - label_bbox[1] + 6
    x = xy[0]
    y = max(0, xy[1] - label_h)
    draw.rectangle([x, y, x + label_w, y + label_h], fill=hex_to_rgba(color, 230))
    draw.text((x + 4, y + 2), label, fill=(255, 255, 255, 255), font=font)


def draw_title(image: Image.Image, title: str) -> None:
    draw = ImageDraw.Draw(image)
    font = load_font(24)
    bbox = draw.textbbox((0, 0), title, font=font)
    width = bbox[2] - bbox[0] + 24
    height = bbox[3] - bbox[1] + 18
    draw.rectangle([12, 12, 12 + width, 12 + height], fill=(17, 24, 39, 210))
    draw.text((24, 21), title, fill=(255, 255, 255, 255), font=font)


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ):
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def hex_to_rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        value = "64748b"
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha


if __name__ == "__main__":
    raise SystemExit(main())
