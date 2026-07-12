from __future__ import annotations

from typing import Any, Mapping

from .document import normalize_box_type

SVG_TEMPLATE_IR_SCHEMA = "drawai.box_ir.svg_template_ir.v1"
TEMPLATE_IR_TYPES = frozenset({"content_box", "arrow"})


def build_svg_template_ir(box_ir: Mapping[str, Any]) -> dict[str, Any]:
    """Build the compact IR shown to SVG template generation.

    The template stage should see only layout scaffolding geometry. Icon,
    picture, OCR text content, scores, source ids, and merge traces stay out of
    the model prompt.
    """

    boxes = [_template_box(box) for box in _iter_boxes(box_ir.get("boxes"))]
    boxes = [box for box in boxes if box is not None]
    return {
        "schema": SVG_TEMPLATE_IR_SCHEMA,
        "canvas": _canvas(box_ir.get("canvas")),
        "box_count": len(boxes),
        "boxes": boxes,
    }


def _iter_boxes(raw_boxes: Any) -> list[Mapping[str, Any]]:
    if not isinstance(raw_boxes, list):
        return []
    return [box for box in raw_boxes if isinstance(box, Mapping)]


def _template_box(box: Mapping[str, Any]) -> dict[str, Any] | None:
    box_type = normalize_box_type(box.get("type"))
    if box_type not in TEMPLATE_IR_TYPES:
        return None
    box_id = box.get("id")
    bbox = _bbox(box.get("bbox"))
    if not isinstance(box_id, str) or not box_id.strip() or bbox is None:
        return None
    return {
        "id": box_id.strip(),
        "type": box_type,
        "bbox": bbox,
    }


def _canvas(raw_canvas: Any) -> dict[str, int]:
    if not isinstance(raw_canvas, Mapping):
        return {"width": 0, "height": 0}
    return {
        "width": _int(raw_canvas.get("width")),
        "height": _int(raw_canvas.get("height")),
    }


def _bbox(raw_bbox: Any) -> list[int] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    values: list[int] = []
    for item in raw_bbox:
        try:
            values.append(_int(item))
        except (TypeError, ValueError):
            return None
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        return None
    return values


def _int(value: Any) -> int:
    return max(0, int(round(float(value))))
