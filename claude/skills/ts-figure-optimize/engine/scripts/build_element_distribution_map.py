from __future__ import annotations

import argparse
import html
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


CATEGORY_ORDER = ("svg_self_draw", "crop", "crop_nobg", "imagegen")

CATEGORY_LABELS = {
    "svg_self_draw": "SVG 自绘",
    "crop": "直接抠图",
    "crop_nobg": "抠图去背景",
    "imagegen": "ImageGen",
    "unknown": "未知",
}

CATEGORY_COLORS = {
    "svg_self_draw": "#13a563",
    "crop": "#f59e0b",
    "crop_nobg": "#2563eb",
    "imagegen": "#d946ef",
    "unknown": "#64748b",
}

CATEGORY_ALIASES = {
    "svg_self_draw": {
        "svg_self_draw",
        "svg-self-draw",
        "native_svg",
        "svg",
        "self_draw",
        "self-draw",
        "draw_svg",
        "ppt_svg",
    },
    "crop": {
        "crop",
        "crop_asset",
        "raster_crop",
        "preserve_crop",
        "crop_preserve",
        "direct_crop",
        "backfill_crop_preserve",
    },
    "crop_nobg": {
        "crop_nobg",
        "crop-nobg",
        "crop_no_bg",
        "crop_without_background",
        "without_background",
        "transparent_subject",
        "rmbg",
        "remove_background",
        "backfill_crop_nobg",
    },
    "imagegen": {
        "imagegen",
        "image_gen",
        "image_generation",
        "generated_image",
        "generate_image",
        "ai_image",
        "text_to_image",
    },
}

CATEGORY_KEYS = (
    "category",
    "method",
    "strategy",
    "render_strategy",
    "render_method",
    "asset_method",
    "action",
    "decision",
    "output_type",
)

TYPE_KEYS = ("element_type", "type", "role", "label", "kind", "class")
REASON_KEYS = ("reason", "reasons", "reason_codes", "explanation", "description", "detail", "notes", "why")


@dataclass(frozen=True)
class ElementRecord:
    element_id: str
    element_type: str
    category: str
    reason: str
    bbox: tuple[float, float, float, float]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    analysis_path = Path(args.element_analysis).expanduser().resolve(strict=False)
    output_path = Path(args.output).expanduser().resolve(strict=False) if args.output else None
    background_image = args.background_image or None
    canvas = _parse_canvas(args.canvas) if args.canvas else None
    result = build_element_distribution_map(
        analysis_path,
        output_path=output_path,
        background_image=background_image,
        canvas=canvas,
        title=args.title,
    )
    print(result)
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render an element_analysis.json file as an interactive element distribution map."
    )
    parser.add_argument("element_analysis", help="Path to an external/generated element_analysis.json file.")
    parser.add_argument(
        "--output",
        default="",
        help="HTML output path. Defaults to ELEMENT_ANALYSIS_DIR/element_distribution_map.html.",
    )
    parser.add_argument(
        "--background-image",
        default="",
        help="Optional source figure/background image path or URL. Relative paths resolve from the JSON directory.",
    )
    parser.add_argument(
        "--canvas",
        default="",
        help="Optional canvas override as WIDTHxHEIGHT, for example 1920x1080.",
    )
    parser.add_argument("--title", default="元素分布图", help="HTML report title.")
    return parser.parse_args(argv)


def build_element_distribution_map(
    analysis_path: Path,
    *,
    output_path: Path | None = None,
    background_image: str | Path | None = None,
    canvas: tuple[int, int] | None = None,
    title: str = "元素分布图",
) -> Path:
    payload = _read_json(analysis_path)
    raw_elements = _extract_element_items(payload)
    elements = _normalize_elements(raw_elements)
    if not elements:
        raise ValueError("No drawable elements found. Expected records with a bbox/box/bounds field.")

    width, height = canvas or _payload_canvas(payload) or _infer_canvas(elements)
    resolved_background = _resolve_background_image(payload, analysis_path, output_path, background_image)
    destination = output_path or (analysis_path.parent / "element_distribution_map.html")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        _html_document(
            title=title,
            analysis_path=analysis_path,
            width=width,
            height=height,
            elements=elements,
            background_href=resolved_background,
        ),
        encoding="utf-8",
    )
    return destination


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_element_items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        raise ValueError("element_analysis.json must be a JSON object or array.")
    for key in ("elements", "items", "boxes", "decisions", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    nested = payload.get("element_analysis")
    if isinstance(nested, (Mapping, list)):
        return _extract_element_items(nested)
    raise ValueError("element_analysis.json must contain elements/items/boxes/decisions/records.")


def _normalize_elements(records: Sequence[Mapping[str, Any]]) -> list[ElementRecord]:
    elements: list[ElementRecord] = []
    for index, record in enumerate(records):
        bbox = _bbox(record)
        if bbox is None:
            continue
        category = _record_category(record)
        element_type = _record_type(record, category)
        elements.append(
            ElementRecord(
                element_id=_record_id(record, index),
                element_type=element_type,
                category=category,
                reason=_record_reason(record),
                bbox=bbox,
            )
        )
    return elements


def _record_id(record: Mapping[str, Any], index: int) -> str:
    value = _first_text(record, ("id", "element_id", "box_id", "asset_id", "name"))
    return value or f"E{index + 1:03d}"


def _record_category(record: Mapping[str, Any]) -> str:
    for key in CATEGORY_KEYS:
        value = record.get(key)
        category = _normalize_category(value)
        if category != "unknown":
            return category
        if isinstance(value, Mapping):
            nested = _record_category(value)
            if nested != "unknown":
                return nested
    for key in ("asset_decision", "analysis", "policy", "classification"):
        value = record.get(key)
        if isinstance(value, Mapping):
            nested = _record_category(value)
            if nested != "unknown":
                return nested
    return "unknown"


def _normalize_category(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    for category, aliases in CATEGORY_ALIASES.items():
        if normalized in aliases:
            return category
    return "unknown"


def _record_type(record: Mapping[str, Any], category: str) -> str:
    for key in TYPE_KEYS:
        value = _text(record.get(key))
        if value and _normalize_category(value) != category:
            return value
    return ""


def _record_reason(record: Mapping[str, Any]) -> str:
    for key in REASON_KEYS:
        value = record.get(key)
        text = _reason_text(value)
        if text:
            return text
    for key in ("asset_decision", "analysis", "policy", "classification"):
        value = record.get(key)
        if isinstance(value, Mapping):
            text = _record_reason(value)
            if text:
                return text
    return ""


def _bbox(record: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    for key in ("bbox", "box", "bounds", "rect"):
        value = record.get(key)
        bbox = _bbox_from_value(value)
        if bbox is not None:
            return bbox
    return _bbox_from_value(record)


def _bbox_from_value(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, Mapping):
        if all(key in value for key in ("x", "y", "width", "height")):
            x = _number(value["x"])
            y = _number(value["y"])
            width = _number(value["width"])
            height = _number(value["height"])
            if x is None or y is None or width is None or height is None:
                return None
            return _valid_bbox((x, y, x + width, y + height))
        for keys in (("x1", "y1", "x2", "y2"), ("left", "top", "right", "bottom")):
            if all(key in value for key in keys):
                numbers = [_number(value[key]) for key in keys]
                if any(item is None for item in numbers):
                    return None
                return _valid_bbox(tuple(item for item in numbers if item is not None))
    if isinstance(value, (list, tuple)) and len(value) == 4:
        numbers = [_number(item) for item in value]
        if any(item is None for item in numbers):
            return None
        return _valid_bbox(tuple(item for item in numbers if item is not None))
    return None


def _valid_bbox(raw: tuple[float, float, float, float]) -> tuple[float, float, float, float] | None:
    if not all(math.isfinite(item) for item in raw):
        return None
    left, right = sorted((raw[0], raw[2]))
    top, bottom = sorted((raw[1], raw[3]))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return None


def _payload_canvas(payload: Any) -> tuple[int, int] | None:
    if not isinstance(payload, Mapping):
        return None
    for value in (
        payload.get("canvas"),
        payload.get("image"),
        payload.get("figure"),
        payload.get("page"),
    ):
        canvas = _canvas_from_mapping(value)
        if canvas is not None:
            return canvas
    return _canvas_from_mapping(payload)


def _canvas_from_mapping(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, Mapping):
        return None
    width = value.get("width", value.get("w"))
    height = value.get("height", value.get("h"))
    parsed_width = _number(width)
    parsed_height = _number(height)
    if parsed_width is None or parsed_height is None:
        return None
    if parsed_width <= 0 or parsed_height <= 0:
        return None
    return int(round(parsed_width)), int(round(parsed_height))


def _infer_canvas(elements: Sequence[ElementRecord]) -> tuple[int, int]:
    max_x = max(element.bbox[2] for element in elements)
    max_y = max(element.bbox[3] for element in elements)
    return max(1, int(math.ceil(max_x))), max(1, int(math.ceil(max_y)))


def _parse_canvas(value: str) -> tuple[int, int]:
    raw = value.lower().replace("*", "x")
    parts = raw.split("x")
    if len(parts) != 2:
        raise ValueError("--canvas must use WIDTHxHEIGHT, for example 1920x1080.")
    width = int(parts[0])
    height = int(parts[1])
    if width <= 0 or height <= 0:
        raise ValueError("--canvas width and height must be positive.")
    return width, height


def _resolve_background_image(
    payload: Any,
    analysis_path: Path,
    output_path: Path | None,
    background_image: str | Path | None,
) -> str:
    value = str(background_image) if background_image else _payload_background_image(payload)
    if not value:
        return ""
    if _is_url_like(value):
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = analysis_path.parent / path
    destination = output_path or (analysis_path.parent / "element_distribution_map.html")
    rel = _relative_path(path, destination.parent)
    return rel if rel is not None else path.resolve(strict=False).as_uri()


def _payload_background_image(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ""
    for key in ("background_image", "image_path", "figure_path", "source_image"):
        value = _text(payload.get(key))
        if value:
            return value
    for key in ("image", "figure", "canvas"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested = _first_text(value, ("path", "href", "url", "src"))
            if nested:
                return nested
    return ""


def _relative_path(path: Path, base_dir: Path) -> str | None:
    absolute_path = path.resolve(strict=False)
    absolute_base = base_dir.resolve(strict=False)
    try:
        return absolute_path.relative_to(absolute_base).as_posix()
    except ValueError:
        return None


def _is_url_like(value: str) -> bool:
    return value.startswith(("http://", "https://", "data:", "file:"))


def _html_document(
    *,
    title: str,
    analysis_path: Path,
    width: int,
    height: int,
    elements: Sequence[ElementRecord],
    background_href: str,
) -> str:
    counts = Counter(element.category for element in elements)
    legend = "\n".join(_legend_item(category, counts.get(category, 0)) for category in CATEGORY_ORDER)
    if counts.get("unknown", 0):
        legend += "\n" + _legend_item("unknown", counts["unknown"])
    rects = "\n".join(_svg_element(element, width, height) for element in elements)
    background = ""
    if background_href:
        background = (
            f'<image href="{html.escape(background_href)}" x="0" y="0" width="{width}" height="{height}" '
            'preserveAspectRatio="none" opacity="0.72" />'
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background: #f6f7f9; color: #182230; }}
header {{ padding: 22px 28px; background: #fff; border-bottom: 1px solid #d0d5dd; }}
h1 {{ margin: 0 0 8px; font-size: 24px; letter-spacing: 0; }}
main {{ max-width: 1500px; margin: 0 auto; padding: 20px; }}
.path {{ color: #667085; font-size: 13px; overflow-wrap: anywhere; }}
.summary {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }}
.legend-item {{ display: inline-flex; align-items: center; gap: 7px; border: 1px solid #d0d5dd; border-radius: 6px; background: #fff; padding: 7px 10px; font-size: 13px; }}
.swatch {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
.map-wrap {{ overflow: auto; border: 1px solid #d0d5dd; border-radius: 8px; background: #111827; padding: 12px; }}
svg {{ display: block; width: min(100%, {width}px); min-width: min({width}px, 100%); height: auto; margin: auto; background: #fff; }}
.element rect {{ fill: color-mix(in srgb, var(--c) 18%, transparent); stroke: var(--c); stroke-width: 2; vector-effect: non-scaling-stroke; }}
.element text {{ fill: #fff; font-size: 12px; paint-order: stroke; stroke: rgba(0,0,0,.76); stroke-width: 3px; stroke-linejoin: round; pointer-events: none; }}
.element:hover rect {{ fill: color-mix(in srgb, var(--c) 34%, transparent); stroke-width: 4; }}
.help {{ margin-top: 10px; color: #475467; font-size: 13px; }}
</style>
</head>
<body>
<header>
  <h1>{html.escape(title)}</h1>
  <div class="path">{html.escape(str(analysis_path))}</div>
</header>
<main>
  <div class="summary">{legend}</div>
  <div class="map-wrap">
    <svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">
      <rect x="0" y="0" width="{width}" height="{height}" fill="#fff" />
      {background}
      {rects}
    </svg>
  </div>
  <div class="help">Hover 元素框可查看分类、类型、原因和 bbox。分类固定为 svg_self_draw、crop、crop_nobg、imagegen；无法识别的记录会以灰色 unknown 暴露出来。</div>
</main>
</body>
</html>
"""


def _legend_item(category: str, count: int) -> str:
    color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["unknown"])
    label = CATEGORY_LABELS.get(category, category)
    return (
        '<span class="legend-item">'
        f'<i class="swatch" style="background:{html.escape(color)}"></i>'
        f"{html.escape(label)} <strong>{count}</strong>"
        "</span>"
    )


def _svg_element(element: ElementRecord, width: int, height: int) -> str:
    color = CATEGORY_COLORS.get(element.category, CATEGORY_COLORS["unknown"])
    left, top, right, bottom = _clamped_bbox(element.bbox, width, height)
    label = element.element_id
    tooltip = "\n".join(
        [
            f"id: {element.element_id}",
            f"category: {element.category}",
            f"type: {element.element_type}",
            f"reason: {element.reason}",
            f"bbox: {_format_bbox(element.bbox)}",
        ]
    )
    return (
        f'<g class="element" data-category="{html.escape(element.category)}" style="--c:{html.escape(color)}">'
        f"<title>{html.escape(tooltip)}</title>"
        f'<rect x="{left:.2f}" y="{top:.2f}" width="{right - left:.2f}" height="{bottom - top:.2f}" rx="2" />'
        f'<text x="{left + 4:.2f}" y="{top + 15:.2f}">{html.escape(label)}</text>'
        "</g>"
    )


def _clamped_bbox(
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    left = min(max(bbox[0], 0.0), float(width))
    top = min(max(bbox[1], 0.0), float(height))
    right = min(max(bbox[2], 0.0), float(width))
    bottom = min(max(bbox[3], 0.0), float(height))
    if right <= left:
        right = min(float(width), left + 1.0)
    if bottom <= top:
        bottom = min(float(height), top + 1.0)
    return left, top, right, bottom


def _format_bbox(bbox: tuple[float, float, float, float]) -> str:
    return "[" + ", ".join(str(round(item, 1)) for item in bbox) + "]"


def _first_text(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = _text(record.get(key))
        if value:
            return value
    return ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _reason_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return ", ".join(str(item) for item in value if item is not None)
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
