from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from drawai.page_spec import validate_page_spec_payload
from drawai.page_spec_assets import page_spec_asset_manifest


def draft_semantic_svg_from_page_spec(
    page_spec_path: str | Path,
    svg_path: str | Path,
    *,
    href_base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Write a baseline semantic SVG from a materialized PageSpec bundle."""

    page_spec_file = Path(page_spec_path).expanduser().resolve(strict=False)
    page_spec = json.loads(page_spec_file.read_text(encoding="utf-8"))
    if not isinstance(page_spec, Mapping):
        raise ValueError("PageSpec must be a JSON object")
    validate_page_spec_payload(page_spec)

    svg_file = Path(svg_path).expanduser().resolve(strict=False)
    svg_dir = Path(href_base_dir).expanduser().resolve(strict=False) if href_base_dir is not None else svg_file.parent
    asset_manifest = page_spec_asset_manifest(page_spec_file, svg_dir=svg_dir)
    active_assets = {
        str(asset.get("element_id")): asset
        for asset in asset_manifest.get("assets", [])
        if isinstance(asset, Mapping) and asset.get("svg_href")
    }
    width, height = _canvas_size(page_spec)
    elements = [element for element in page_spec.get("elements", []) if isinstance(element, Mapping)]

    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(width)}" height="{_num(height)}" '
            f'viewBox="0 0 {_num(width)} {_num(height)}" data-drawai-source="page-spec-svg-draft">'
        ),
        "  <defs>",
        (
            '    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" '
            'orient="auto" markerUnits="strokeWidth">'
        ),
        '      <polygon points="0 0, 10 3.5, 0 7" fill="#334155"/>',
        "    </marker>",
        "  </defs>",
        f'  <rect id="background-page" x="0" y="0" width="{_num(width)}" height="{_num(height)}" fill="#ffffff"/>',
    ]
    image_count = 0
    text_count = 0
    vector_count = 0
    for element in sorted(elements, key=_element_sort_key):
        rendered = _render_element(element, active_assets)
        if rendered is None:
            continue
        lines.append(rendered)
        kind = _element_kind(element)
        if kind == "image":
            image_count += 1
        elif kind == "text":
            text_count += 1
        else:
            vector_count += 1
    lines.append("</svg>")

    svg_file.parent.mkdir(parents=True, exist_ok=True)
    svg_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "schema": "drawai.page_spec_svg_draft.v1",
        "ok": True,
        "page_spec": str(page_spec_file),
        "svg": str(svg_file),
        "href_base_dir": str(svg_dir),
        "canvas": {"width": width, "height": height},
        "elements": len(elements),
        "rendered_elements": image_count + text_count + vector_count,
        "asset_images": image_count,
        "editable_text": text_count,
        "editable_vectors": vector_count,
    }


def _render_element(element: Mapping[str, Any], active_assets: Mapping[str, Mapping[str, Any]]) -> str | None:
    bbox = _element_bbox(element)
    if bbox is None:
        return None
    x, y, width, height = bbox
    if width <= 0 or height <= 0:
        return None
    element_id = _attr(str(element.get("id") or "element"))
    kind = _element_kind(element)
    role = _attr(str(element.get("role") or kind))
    processing_type = _processing_type(element)
    asset = active_assets.get(str(element.get("id") or ""))
    if processing_type in {"crop", "crop_nobg", "image_generate", "image_edit"} and asset is not None:
        href = _attr(str(asset["svg_href"]))
        return (
            f'  <image id="image-{element_id}" href="{href}" x="{_num(x)}" y="{_num(y)}" '
            f'width="{_num(width)}" height="{_num(height)}" preserveAspectRatio="none" '
            f'data-pb-editable="false" data-drawai-element-id="{element_id}" data-drawai-role="{role}" '
            f'data-drawai-source="{_attr(processing_type)}"/>'
        )
    if kind == "text" or _element_text(element):
        return _render_text(element, x, y, width, height, element_id, role)
    if kind == "connector" or str(element.get("role") or "").lower() in {"arrow", "connector", "line"}:
        return _render_connector(x, y, width, height, element_id, role)
    return _render_shape(x, y, width, height, element_id, role, kind, processing_type)


def _render_text(
    element: Mapping[str, Any],
    x: float,
    y: float,
    width: float,
    height: float,
    element_id: str,
    role: str,
) -> str:
    text = _text(_element_text(element))
    font_size = _text_font_size(text, width, height)
    baseline = y + min(height * 0.78, font_size)
    return (
        f'  <text id="label-{element_id}" x="{_num(x)}" y="{_num(baseline)}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{_num(font_size)}" fill="#111827" '
        f'data-pb-editable="true" data-pb-role="text" data-drawai-element-id="{element_id}" '
        f'data-drawai-role="{role}">{text}</text>'
    )


def _render_connector(x: float, y: float, width: float, height: float, element_id: str, role: str) -> str:
    stroke_width = max(2.0, min(5.0, min(width, height) / 5.0))
    if width >= height:
        x1, y1 = x + max(1.0, width * 0.06), y + height / 2.0
        x2, y2 = x + max(width - 1.0, width * 0.94), y + height / 2.0
    else:
        x1, y1 = x + width / 2.0, y + max(1.0, height * 0.06)
        x2, y2 = x + width / 2.0, y + max(height - 1.0, height * 0.94)
    return (
        f'  <line id="connector-{element_id}" x1="{_num(x1)}" y1="{_num(y1)}" x2="{_num(x2)}" y2="{_num(y2)}" '
        f'stroke="#334155" stroke-width="{_num(stroke_width)}" stroke-linecap="round" marker-end="url(#arrowhead)" '
        f'data-pb-editable="true" data-drawai-element-id="{element_id}" data-drawai-role="{role}"/>'
    )


def _render_shape(
    x: float,
    y: float,
    width: float,
    height: float,
    element_id: str,
    role: str,
    kind: str,
    processing_type: str,
) -> str:
    if min(width, height) <= 24 and kind in {"image", "shape"}:
        return (
            f'  <ellipse id="node-{element_id}" cx="{_num(x + width / 2.0)}" cy="{_num(y + height / 2.0)}" '
            f'rx="{_num(width / 2.0)}" ry="{_num(height / 2.0)}" fill="#e2e8f0" stroke="#64748b" '
            f'stroke-width="1.5" data-pb-editable="true" data-drawai-element-id="{element_id}" '
            f'data-drawai-role="{role}" data-drawai-source="{_attr(processing_type)}"/>'
        )
    fill = "#ffffff" if role in {"content_box", "frame", "panel"} else "#f8fafc"
    fill_opacity = "0.72" if role in {"content_box", "frame", "panel"} else "0.42"
    radius = min(12.0, max(2.0, min(width, height) * 0.08))
    return (
        f'  <rect id="shape-{element_id}" x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" '
        f'rx="{_num(radius)}" ry="{_num(radius)}" fill="{fill}" fill-opacity="{fill_opacity}" '
        f'stroke="#94a3b8" stroke-width="1.5" data-pb-editable="true" '
        f'data-drawai-element-id="{element_id}" data-drawai-role="{role}" data-drawai-source="{_attr(processing_type)}"/>'
    )


def _canvas_size(page_spec: Mapping[str, Any]) -> tuple[float, float]:
    canvas = page_spec.get("canvas") if isinstance(page_spec.get("canvas"), Mapping) else {}
    source = page_spec.get("source") if isinstance(page_spec.get("source"), Mapping) else {}
    width = _positive_number(canvas.get("width_px") or canvas.get("width") or source.get("width_px") or source.get("width"))
    height = _positive_number(canvas.get("height_px") or canvas.get("height") or source.get("height_px") or source.get("height"))
    return width, height


def _element_bbox(element: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    box = element.get("box_px")
    if isinstance(box, Sequence) and not isinstance(box, (str, bytes)) and len(box) >= 4:
        return tuple(float(value) for value in box[:4])  # type: ignore[return-value]
    bbox = element.get("bbox")
    if isinstance(bbox, Mapping):
        return (
            float(bbox.get("x") or 0),
            float(bbox.get("y") or 0),
            float(bbox.get("width") or 0),
            float(bbox.get("height") or 0),
        )
    if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)) and len(bbox) >= 4:
        x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
        return x1, y1, x2 - x1, y2 - y1
    geometry = element.get("geometry")
    if isinstance(geometry, Mapping):
        raw_bbox = geometry.get("bbox")
        if isinstance(raw_bbox, Sequence) and not isinstance(raw_bbox, (str, bytes)) and len(raw_bbox) >= 4:
            x1, y1, x2, y2 = [float(value) for value in raw_bbox[:4]]
            return x1, y1, x2 - x1, y2 - y1
    return None


def _element_sort_key(element: Mapping[str, Any]) -> tuple[float, int, str]:
    kind = _element_kind(element)
    processing_type = _processing_type(element)
    if kind == "text" or _element_text(element):
        rank = 40
    elif processing_type in {"crop", "crop_nobg"}:
        rank = 30
    elif kind == "connector":
        rank = 20
    else:
        rank = 10
    return float(element.get("z_index") or 0), rank, str(element.get("id") or "")


def _element_kind(element: Mapping[str, Any]) -> str:
    return str(element.get("kind") or element.get("type") or "shape").lower()


def _processing_type(element: Mapping[str, Any]) -> str:
    build = element.get("build") if isinstance(element.get("build"), Mapping) else {}
    return str(build.get("processing_type") or "svg_self_draw")


def _element_text(element: Mapping[str, Any]) -> str:
    raw_text = element.get("text")
    if raw_text not in (None, ""):
        return str(raw_text)
    measurement = element.get("measurement") if isinstance(element.get("measurement"), Mapping) else {}
    raw_measurement_text = measurement.get("text")
    return str(raw_measurement_text or "")


def _text_font_size(text: str, width: float, height: float) -> float:
    base = max(8.0, min(42.0, height * 0.72))
    if text and width > 0:
        estimated_width = len(text) * base * 0.56
        if estimated_width > width:
            base = max(8.0, min(base, width / max(len(text) * 0.56, 1.0)))
    return base


def _positive_number(value: Any) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("PageSpec canvas width and height must be positive")
    return parsed


def _num(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _text(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})
