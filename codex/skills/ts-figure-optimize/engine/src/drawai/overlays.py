from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont

from .asset_selection_loop import normalize_and_validate_asset_decisions
from .domain.box_ir import normalize_box_type

SEMANTIC_OVERLAY_COLORS = {
    "arrow": "#e53935",
    "border": "#1e88e5",
    "content_box": "#43a047",
    "grid": "#8e24aa",
    "symbol": "#fb8c00",
    "icon": "#00acc1",
    "picture": "#6d4c41",
    "text": "#3949ab",
    "unknown": "#757575",
}
SEMANTIC_OVERLAY_LABELS = {
    "arrow": "arrow",
    "border": "border",
    "content_box": "content box",
    "grid": "grid",
    "symbol": "symbol",
    "icon": "icon",
    "picture": "picture",
    "text": "OCR text",
    "unknown": "unknown",
}
TEMPLATE_ASSET_FILL = "#808080"
TEMPLATE_ASSET_LABEL = "#ffffff"
TEMPLATE_SEMANTIC_FILL_ALPHA = 52
DIAGNOSTIC_OUTLINE_DIVISOR = 720


def render_semantic_overlay(
    image_path: str | Path,
    box_ir: Mapping[str, Any],
    out_path: str | Path,
    draw_labels: bool = True,
    draw_legend: bool = False,
) -> dict[str, Any]:
    image_path = Path(image_path)
    out_path = Path(out_path)
    with Image.open(image_path) as image:
        overlay = image.convert("RGB")

    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    line_width = _scaled_line_width(overlay.size)

    semantic_boxes = _ordered_semantic_boxes(box_ir.get("boxes", []))
    for box in semantic_boxes:
        if normalize_box_type(box.get("type")) == "icon":
            continue
        _draw_box(draw, box, overlay.size, line_width, font, default_type="unknown", draw_labels=draw_labels)
    for box in box_ir.get("ocr_text_boxes", []):
        _draw_box(draw, box, overlay.size, line_width, font, default_type="text", draw_labels=draw_labels)
    for box in semantic_boxes:
        if normalize_box_type(box.get("type")) == "icon":
            _draw_box(draw, box, overlay.size, line_width, font, default_type="unknown", draw_labels=draw_labels)

    if draw_legend:
        _draw_color_legend(overlay, _semantic_legend_entries(), title="layout IR colors")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(out_path)
    return {
        "schema": "drawai.box_ir.semantic_overlay_legend.v1",
        "colors": dict(SEMANTIC_OVERLAY_COLORS),
        "legend_drawn": draw_legend,
    }


def render_sam_prompt_overlay(
    image_path: str | Path,
    prompt_id: str,
    regions: list[Any],
    out_path: str | Path,
    draw_labels: bool = True,
) -> dict[str, Any]:
    image_path = Path(image_path)
    out_path = Path(out_path)
    with Image.open(image_path) as image:
        base = image.convert("RGBA")

    color = SEMANTIC_OVERLAY_COLORS.get(prompt_id, SEMANTIC_OVERLAY_COLORS["unknown"])
    rgba = _hex_to_rgba(color, 42)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    base_draw = ImageDraw.Draw(base)
    font = ImageFont.load_default()
    line_width = _scaled_line_width(base.size)

    drawn_regions = 0
    for index, region in enumerate(regions, start=1):
        if not isinstance(region, Mapping):
            continue
        bbox = _clamp_bbox(region.get("bbox") or region.get("box") or region.get("xyxy"), base.size)
        if bbox is None:
            continue
        overlay_draw.rectangle(bbox, fill=rgba)
        base_draw.rectangle(bbox, outline=color, width=line_width)
        if draw_labels:
            label = str(region.get("id") or region.get("label") or f"{prompt_id}:{index:03d}")
            base_draw.text((bbox[0] + line_width + 1, bbox[1] + line_width + 1), label, fill=color, font=font)
        drawn_regions += 1

    rendered = Image.alpha_composite(base, overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(out_path)
    return {
        "schema": "drawai.sam3.prompt_overlay_legend.v1",
        "prompt_id": prompt_id,
        "color": color,
        "region_count": len(regions),
        "drawn_region_count": drawn_regions,
    }


def render_visual_template_reference(
    image_path: str | Path,
    box_ir: Mapping[str, Any],
    decisions: Mapping[str, Any],
    out_path: str | Path,
    draw_labels: bool = True,
    asset_selection_config: Any = None,
    *,
    disallow_crop_roles: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    max_area_ratio: float | None = None,
    draw_legend: bool = False,
    semantic_types: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None = None,
    asset_policy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_decisions = normalize_and_validate_asset_decisions(
        box_ir,
        decisions,
        asset_selection_config,
        disallow_crop_roles=disallow_crop_roles,
        max_area_ratio=max_area_ratio,
    )
    image_path = Path(image_path)
    out_path = Path(out_path)
    with Image.open(image_path) as image:
        overlay = image.convert("RGB")

    semantic_fills = _draw_template_semantic_segmentation(overlay, box_ir, semantic_types)
    selected_assets = _selected_crop_assets(normalized_decisions)
    policy_by_asset_id = _asset_policy_by_asset_id(asset_policy_report)
    boxes_by_id = _boxes_by_id(box_ir.get("boxes"))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    legend_assets: dict[str, dict[str, Any]] = {}
    for asset_id, asset in selected_assets.items():
        box_id = asset["box_id"]
        box = boxes_by_id.get(box_id)
        if box is None:
            continue
        bbox = _clamp_bbox(box.get("bbox"), overlay.size)
        if bbox is None:
            continue
        mask_bboxes = _template_asset_mask_bboxes(asset_id, bbox, policy_by_asset_id.get(asset_id), overlay.size)
        for mask_index, mask_bbox in enumerate(mask_bboxes, start=1):
            draw.rectangle(mask_bbox, fill=TEMPLATE_ASSET_FILL)
            if draw_labels:
                label = asset_id if len(mask_bboxes) == 1 else f"{asset_id}.C{mask_index:02d}"
                _draw_template_asset_label(draw, mask_bbox, label, font)
        legend_assets[asset_id] = {
            "box_id": box_id,
            "fill": TEMPLATE_ASSET_FILL,
            "border": None,
            "label": _template_asset_label(asset_id),
            "mask_count": len(mask_bboxes),
        }

    if draw_legend:
        _draw_color_legend(overlay, _visual_template_legend_entries(), title="Template reference")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(out_path)
    return {
        "schema": "drawai.box_ir.visual_template_reference_legend.v1",
        "asset_fill": TEMPLATE_ASSET_FILL,
        "asset_border": None,
        "asset_label": TEMPLATE_ASSET_LABEL,
        "semantic_fills": semantic_fills,
        "assets": legend_assets,
        "legend_drawn": draw_legend,
    }


def _draw_template_semantic_segmentation(
    image: Image.Image,
    box_ir: Mapping[str, Any],
    semantic_types: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None,
) -> dict[str, dict[str, Any]]:
    requested = {normalize_box_type(item) for item in semantic_types or ()}
    requested.discard("unknown")
    if not requested:
        return {}

    fill_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    fill_draw = ImageDraw.Draw(fill_layer)
    rendered_count: dict[str, int] = {}
    for box in _ordered_semantic_boxes(box_ir.get("boxes", [])):
        box_type = normalize_box_type(box.get("type"))
        if box_type not in requested or box_type not in SEMANTIC_OVERLAY_COLORS:
            continue
        bbox = _clamp_bbox(box.get("bbox"), image.size)
        if bbox is None:
            continue
        fill_draw.rectangle(bbox, fill=_hex_to_rgba(SEMANTIC_OVERLAY_COLORS[box_type], TEMPLATE_SEMANTIC_FILL_ALPHA))
        rendered_count[box_type] = rendered_count.get(box_type, 0) + 1

    if not rendered_count:
        return {}

    filled = Image.alpha_composite(image.convert("RGBA"), fill_layer).convert("RGB")
    image.paste(filled)

    return {
        box_type: {
            "fill": SEMANTIC_OVERLAY_COLORS[box_type],
            "alpha": TEMPLATE_SEMANTIC_FILL_ALPHA,
            "box_count": count,
        }
        for box_type, count in sorted(rendered_count.items())
    }


def _draw_box(
    draw: ImageDraw.ImageDraw,
    box: Any,
    image_size: tuple[int, int],
    line_width: int,
    font: ImageFont.ImageFont,
    default_type: str,
    draw_labels: bool,
) -> None:
    if not isinstance(box, Mapping):
        return
    bbox = _clamp_bbox(box.get("bbox"), image_size)
    if bbox is None:
        return
    box_type = box.get("type", default_type)
    if box_type not in SEMANTIC_OVERLAY_COLORS:
        box_type = default_type
    color = SEMANTIC_OVERLAY_COLORS[box_type]
    draw.rectangle(bbox, outline=color, width=line_width)
    if not draw_labels:
        return
    label = _box_label(box, box_type)
    if label:
        label_position = (bbox[0] + line_width + 1, bbox[1] + line_width + 1)
        draw.text(label_position, label, fill=color, font=font)


def _selected_crop_assets(decisions: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for decision in decisions.get("decisions", []):
        if not isinstance(decision, Mapping) or decision.get("decision") != "crop_asset":
            continue
        asset_id = decision.get("asset_id")
        box_id = decision.get("box_id")
        if isinstance(asset_id, str) and isinstance(box_id, str):
            selected[asset_id] = {"box_id": box_id}
    return selected


def _asset_policy_by_asset_id(asset_policy_report: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(asset_policy_report, Mapping):
        return {}
    assets = asset_policy_report.get("assets")
    if not isinstance(assets, list):
        return {}
    by_id: dict[str, Mapping[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        asset_id = asset.get("asset_id")
        if isinstance(asset_id, str) and asset_id:
            by_id[asset_id] = asset
    return by_id


def _template_asset_mask_bboxes(
    asset_id: str,
    parent_bbox: tuple[int, int, int, int],
    asset_policy: Mapping[str, Any] | None,
    image_size: tuple[int, int],
) -> list[tuple[int, int, int, int]]:
    del asset_id
    if not isinstance(asset_policy, Mapping):
        return [parent_bbox]
    if str(asset_policy.get("split_policy") or "") not in {"safe_compound_split", "text_svg_only"}:
        return [parent_bbox]
    components = asset_policy.get("components")
    if not isinstance(components, list):
        return [parent_bbox]
    component_bboxes: list[tuple[int, int, int, int]] = []
    parent_width = max(0, parent_bbox[2] - parent_bbox[0])
    parent_height = max(0, parent_bbox[3] - parent_bbox[1])
    for component in components:
        if not isinstance(component, Mapping):
            continue
        if str(component.get("kind") or "") != "raster_symbol_transparent":
            continue
        local = _component_local_bbox(component.get("bbox"), (parent_width, parent_height))
        if local is None:
            continue
        global_bbox = _component_global_bbox(local, parent_bbox, image_size)
        if global_bbox is not None:
            component_bboxes.append(global_bbox)
    return component_bboxes or [parent_bbox]


def _component_local_bbox(raw_bbox: Any, crop_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(value) for value in raw_bbox]
    except (TypeError, ValueError):
        return None
    width, height = crop_size
    bbox = (
        max(0, min(width, round(min(x1, x2)))),
        max(0, min(height, round(min(y1, y2)))),
        max(0, min(width, round(max(x1, x2)))),
        max(0, min(height, round(max(y1, y2)))),
    )
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _component_global_bbox(
    local_bbox: tuple[int, int, int, int],
    parent_bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    return _clamp_bbox(
        [
            parent_bbox[0] + local_bbox[0],
            parent_bbox[1] + local_bbox[1],
            parent_bbox[0] + local_bbox[2],
            parent_bbox[1] + local_bbox[3],
        ],
        image_size,
    )


def _boxes_by_id(raw_boxes: Any) -> dict[str, Mapping[str, Any]]:
    boxes: dict[str, Mapping[str, Any]] = {}
    iterable = raw_boxes if isinstance(raw_boxes, list) else []
    for box in iterable:
        if not isinstance(box, Mapping):
            continue
        box_id = box.get("id")
        if isinstance(box_id, str) and box_id:
            boxes[box_id] = box
    return boxes


def _box_label(box: Mapping[str, Any], box_type: str) -> str:
    box_id = box.get("id")
    if isinstance(box_id, str) and box_id:
        return f"{box_id}:{box_type}"
    return box_type


def _ordered_semantic_boxes(raw_boxes: Any) -> list[Mapping[str, Any]]:
    boxes = [box for box in raw_boxes if isinstance(box, Mapping)] if isinstance(raw_boxes, list) else []
    return sorted(boxes, key=_semantic_draw_order_key)


def _semantic_draw_order_key(box: Mapping[str, Any]) -> tuple[int, float, float]:
    box_type = normalize_box_type(box.get("type"))
    layer = {
        "border": 0,
        "grid": 1,
        "content_box": 2,
        "picture": 3,
        "symbol": 4,
        "arrow": 5,
        "unknown": 6,
        "icon": 7,
    }.get(box_type, 6)
    bbox = box.get("bbox")
    area = _bbox_area(bbox) if isinstance(bbox, list) and len(bbox) == 4 else 0.0
    return (layer, -area, float(box.get("score", 0.0) or 0.0))


def _bbox_area(bbox: Any) -> float:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return 0.0
    try:
        x1, y1, x2, y2 = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _semantic_legend_entries() -> list[dict[str, str | None]]:
    keys = ["arrow", "border", "content_box", "grid", "symbol", "icon", "picture", "text", "unknown"]
    return [
        {
            "label": SEMANTIC_OVERLAY_LABELS[key],
            "fill": None,
            "outline": SEMANTIC_OVERLAY_COLORS[key],
        }
        for key in keys
    ]


def _visual_template_legend_entries() -> list[dict[str, str | None]]:
    return [
        {"label": "content box semantic fill", "fill": SEMANTIC_OVERLAY_COLORS["content_box"], "outline": None},
        {"label": "crop asset placeholder", "fill": TEMPLATE_ASSET_FILL, "outline": None},
    ]


def _draw_template_asset_label(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    asset_id: str,
    font: ImageFont.ImageFont,
) -> None:
    label = _template_asset_label(asset_id)
    text_width = _text_width(draw, font, label)
    text_height = _text_height(draw, font, label)
    left, top, right, bottom = bbox
    x = left + max(0, (right - left - text_width) // 2)
    y = top + max(0, (bottom - top - text_height) // 2)
    draw.text((x, y), label, fill=TEMPLATE_ASSET_LABEL, font=font)


def _template_asset_label(asset_id: str) -> str:
    suffix = asset_id[2:] if asset_id.startswith("AF") else asset_id
    return f"<AF>{suffix}"


def _draw_color_legend(
    image: Image.Image,
    entries: list[dict[str, str | None]],
    title: str,
) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    font_size = max(11, round(max(width, height) / 120))
    title_size = max(font_size + 2, round(font_size * 1.15))
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", title_size)
    except OSError:
        font = ImageFont.load_default()
        title_font = font

    padding = max(8, round(font_size * 0.55))
    swatch = max(12, round(font_size * 0.9))
    gap = max(5, round(font_size * 0.35))
    row_height = max(swatch, _text_height(draw, font, "Ag")) + gap
    title_height = _text_height(draw, title_font, title)
    text_width = max(_text_width(draw, font, str(entry["label"])) for entry in entries)
    panel_width = padding * 3 + swatch + text_width
    panel_height = padding * 3 + title_height + row_height * len(entries)
    left = padding
    top = padding
    right = min(width - padding, left + panel_width)
    bottom = min(height - padding, top + panel_height)

    draw.rectangle((left, top, right, bottom), fill="#f5f5f5", outline="#222222", width=max(1, round(font_size / 12)))
    y = top + padding
    draw.text((left + padding, y), title, fill="#111111", font=title_font)
    y += title_height + padding

    for entry in entries:
        outline = str(entry["outline"] or "#757575")
        fill = entry["fill"]
        swatch_box = (left + padding, y, left + padding + swatch, y + swatch)
        draw.rectangle(swatch_box, fill=str(fill) if fill else "#ffffff", outline=outline, width=max(2, round(font_size / 10)))
        draw.text((left + padding + swatch + padding, y - 1), str(entry["label"]), fill="#111111", font=font)
        y += row_height


def _scaled_line_width(image_size: tuple[int, int], divisor: int = DIAGNOSTIC_OUTLINE_DIVISOR) -> int:
    return max(1, round(max(image_size) / divisor))


def _text_width(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, text: str) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _text_height(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, text: str) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def _clamp_bbox(raw_bbox: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(value) for value in raw_bbox]
    except (TypeError, ValueError):
        return None
    width, height = image_size
    left = max(0, min(width - 1, round(min(x1, x2))))
    top = max(0, min(height - 1, round(min(y1, y2))))
    right = max(0, min(width - 1, round(max(x1, x2))))
    bottom = max(0, min(height - 1, round(max(y1, y2))))
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _hex_to_rgba(raw_hex: str, alpha: int) -> tuple[int, int, int, int]:
    raw = raw_hex.lstrip("#")
    if len(raw) != 6:
        return (117, 117, 117, alpha)
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), alpha)
