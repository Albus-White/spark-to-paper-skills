from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from ...asset_geometry import geometry_bbox, normalize_asset_geometry, normalize_geometry_from_region

BOX_IR_SCHEMA = "drawai.box_ir.v1"
BOX_IR_VERSION = 1
BOX_IR_COORDINATE_SYSTEM = "figure_image_pixels"
CONTROLLED_BOX_TYPES = frozenset(
    {
        "arrow",
        "border",
        "content_box",
        "grid",
        "symbol",
        "icon",
        "picture",
        "text",
        "unknown",
    }
)

_TYPE_ALIASES = {
    "arrow": "arrow",
    "arrows": "arrow",
    "border": "border",
    "borders": "border",
    "frame": "border",
    "outline": "border",
    "content": "content_box",
    "content_box": "content_box",
    "content_boxes": "content_box",
    "contentbox": "content_box",
    "box": "content_box",
    "container": "content_box",
    "panel": "content_box",
    "grid": "grid",
    "table": "grid",
    "symbol": "symbol",
    "symbols": "symbol",
    "marker": "symbol",
    "icon": "icon",
    "icons": "icon",
    "picture": "picture",
    "pictures": "picture",
    "image": "picture",
    "photo": "picture",
    "figure": "picture",
    "text": "text",
    "texts": "text",
    "text_box": "text",
    "textbox": "text",
    "label": "text",
    "unknown": "unknown",
}


def build_raw_box_ir(
    canvas: tuple[int | float, int | float] | Mapping[str, Any],
    source_image: str | Path,
    normalized_long_edge: int | float,
    prompt_runs: list[Any],
    raw_regions: list[Any],
) -> dict[str, Any]:
    width, height = _parse_canvas_input(canvas)
    boxes: list[dict[str, Any]] = []

    for index, raw_region in enumerate(raw_regions or []):
        normalized = _normalize_raw_region(raw_region, index, width, height)
        if normalized is not None:
            boxes.append(normalized)

    boxes.sort(key=_reading_order_key)
    for box_index, box in enumerate(boxes, start=1):
        box["id"] = f"B{box_index:03d}"

    return {
        "schema": BOX_IR_SCHEMA,
        "version": BOX_IR_VERSION,
        "canvas": {"width": width, "height": height},
        "source": {
            "image": str(source_image),
            "normalized_long_edge": normalized_long_edge,
            "coordinate_system": BOX_IR_COORDINATE_SYSTEM,
        },
        "prompt_runs": _json_safe(prompt_runs or []),
        "boxes": boxes,
        "ocr_text_boxes": [],
        "merge_trace": {"decisions": []},
    }


def validate_box_ir(document: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(document, Mapping):
        return ["layout IR document must be a mapping"]

    for field_name in (
        "schema",
        "version",
        "canvas",
        "source",
        "prompt_runs",
        "boxes",
        "ocr_text_boxes",
        "merge_trace",
    ):
        if field_name not in document:
            issues.append(f"Missing top-level field: {field_name}")

    if document.get("schema") != BOX_IR_SCHEMA:
        issues.append(f"schema must be {BOX_IR_SCHEMA!r}")
    if document.get("version") != BOX_IR_VERSION:
        issues.append(f"version must be {BOX_IR_VERSION}")

    canvas_size = _parse_canvas_document(document.get("canvas"), issues)
    source = document.get("source")
    if not isinstance(source, Mapping):
        issues.append("source must be a mapping")
    else:
        _validate_source_document(source, issues)
    if not isinstance(document.get("prompt_runs"), list):
        issues.append("prompt_runs must be a list")
    if not isinstance(document.get("merge_trace"), Mapping):
        issues.append("merge_trace must be a mapping")

    boxes = document.get("boxes")
    if not isinstance(boxes, list):
        issues.append("boxes must be a list")
        boxes = []
    ocr_text_boxes = document.get("ocr_text_boxes")
    if not isinstance(ocr_text_boxes, list):
        issues.append("ocr_text_boxes must be a list")
        ocr_text_boxes = []

    box_ids = _validate_box_records(boxes, "boxes", canvas_size, issues, require_type=True)
    _validate_box_records(ocr_text_boxes, "ocr_text_boxes", canvas_size, issues, require_type=False)
    _validate_relationships(boxes, box_ids, issues)
    return issues


def _validate_source_document(source: Mapping[str, Any], issues: list[str]) -> None:
    coordinate_system = source.get("coordinate_system")
    if coordinate_system is None:
        issues.append("source.coordinate_system is required")
    elif coordinate_system != BOX_IR_COORDINATE_SYSTEM:
        issues.append(
            f"source.coordinate_system must be {BOX_IR_COORDINATE_SYSTEM!r}, got {coordinate_system!r}"
        )


def normalize_box_type(raw: Any) -> str:
    if raw is None:
        return "unknown"
    normalized = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    normalized = normalized.strip("_")
    return _TYPE_ALIASES.get(normalized, "unknown")


def _normalize_raw_region(
    raw_region: Any,
    index: int,
    canvas_width: float,
    canvas_height: float,
) -> dict[str, Any] | None:
    if not isinstance(raw_region, Mapping):
        return None

    bbox = _extract_bbox(raw_region)
    geometry = normalize_geometry_from_region(
        raw_region,
        fallback_bbox=bbox,
        image_size=(canvas_width, canvas_height),
    )
    if bbox is None:
        bbox = geometry_bbox(geometry)
    if bbox is None:
        return None
    clamped = _clamp_bbox(bbox, canvas_width, canvas_height)
    if clamped is None:
        return None

    box: dict[str, Any] = {
        "id": "",
        "type": _box_type_from_region(raw_region),
        "bbox": clamped,
        "parent_ids": [],
        "child_ids": [],
        "source_region_index": index,
    }
    if geometry is not None:
        box["geometry"] = geometry
        if geometry.get("kind") == "mask" and isinstance(geometry.get("mask_path"), str):
            box["mask_path"] = geometry["mask_path"]
    if "score" in raw_region and _is_finite_number(raw_region["score"]):
        box["score"] = float(raw_region["score"])
    if "source_prompt" in raw_region:
        box["source_prompt"] = _normalize_source_prompt(raw_region["source_prompt"])
    return box


def _box_type_from_region(raw_region: Mapping[str, Any]) -> str:
    for field_name in ("source_prompt",):
        box_type = normalize_box_type(raw_region.get(field_name))
        if box_type in CONTROLLED_BOX_TYPES and box_type != "unknown":
            return box_type
    for field_name in ("type", "label", "text", "class", "class_name", "category", "name"):
        box_type = normalize_box_type(raw_region.get(field_name))
        if box_type in CONTROLLED_BOX_TYPES and box_type != "unknown":
            return box_type
    return "unknown"


def _normalize_source_prompt(raw: Any) -> str:
    prompt_type = _source_prompt_type(raw)
    if prompt_type != "unknown":
        return prompt_type
    if isinstance(raw, str):
        return raw.strip()
    return _stable_json_text(_json_safe(raw))


def _source_prompt_type(raw: Any) -> str:
    box_type = normalize_box_type(raw)
    if box_type != "unknown":
        return box_type
    if isinstance(raw, Mapping):
        for field_name in ("id", "type", "label", "text", "class", "class_name", "category", "name"):
            box_type = normalize_box_type(raw.get(field_name))
            if box_type != "unknown":
                return box_type
    return "unknown"


def _stable_json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(value)


def _extract_bbox(raw_region: Mapping[str, Any]) -> list[float] | None:
    for field_name in ("bbox", "box", "coordinates", "xyxy"):
        parsed = _parse_bbox_sequence(raw_region.get(field_name))
        if parsed is not None:
            return parsed

    parsed = _parse_coordinate_mapping(raw_region, ("x1", "y1", "x2", "y2"))
    if parsed is not None:
        return parsed
    parsed = _parse_coordinate_mapping(raw_region, ("left", "top", "right", "bottom"))
    if parsed is not None:
        return parsed

    xywh = _parse_coordinate_mapping(raw_region, ("x", "y", "width", "height"))
    if xywh is not None:
        x, y, width, height = xywh
        return [x, y, x + width, y + height]
    return None


def _parse_bbox_sequence(raw: Any) -> list[float] | None:
    if isinstance(raw, Mapping):
        parsed = _parse_coordinate_mapping(raw, ("x1", "y1", "x2", "y2"))
        if parsed is not None:
            return parsed
        parsed = _parse_coordinate_mapping(raw, ("left", "top", "right", "bottom"))
        if parsed is not None:
            return parsed
        xywh = _parse_coordinate_mapping(raw, ("x", "y", "width", "height"))
        if xywh is not None:
            x, y, width, height = xywh
            return [x, y, x + width, y + height]
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    values: list[float] = []
    for value in raw:
        if not _is_finite_number(value):
            return None
        values.append(float(value))
    return values


def _parse_coordinate_mapping(raw: Mapping[str, Any], field_names: tuple[str, str, str, str]) -> list[float] | None:
    if not all(field_name in raw for field_name in field_names):
        return None
    values: list[float] = []
    for field_name in field_names:
        value = raw[field_name]
        if not _is_finite_number(value):
            return None
        values.append(float(value))
    return values


def _clamp_bbox(
    bbox: list[float],
    canvas_width: float,
    canvas_height: float,
) -> list[float] | None:
    x1, y1, x2, y2 = bbox
    left = max(0.0, min(x1, x2))
    top = max(0.0, min(y1, y2))
    right = min(canvas_width, max(x1, x2))
    bottom = min(canvas_height, max(y1, y2))
    if right <= left or bottom <= top:
        return None
    return [left, top, right, bottom]


def _parse_canvas_input(canvas: tuple[int | float, int | float] | Mapping[str, Any]) -> tuple[float, float]:
    if isinstance(canvas, Mapping):
        raw_width = canvas.get("width")
        raw_height = canvas.get("height")
    elif isinstance(canvas, (list, tuple)) and len(canvas) == 2:
        raw_width, raw_height = canvas
    else:
        raise ValueError("canvas must be a (width, height) pair or mapping")
    if not _is_finite_number(raw_width) or not _is_finite_number(raw_height):
        raise ValueError("canvas width and height must be finite numbers")
    width = float(raw_width)
    height = float(raw_height)
    if width <= 0 or height <= 0:
        raise ValueError("canvas width and height must be positive")
    return width, height


def _parse_canvas_document(raw_canvas: Any, issues: list[str]) -> tuple[float, float] | None:
    if not isinstance(raw_canvas, Mapping):
        issues.append("canvas must be a mapping")
        return None
    width = raw_canvas.get("width")
    height = raw_canvas.get("height")
    if not _is_finite_number(width) or not _is_finite_number(height):
        issues.append("canvas width and height must be finite numbers")
        return None
    width = float(width)
    height = float(height)
    if width <= 0 or height <= 0:
        issues.append("canvas width and height must be positive")
        return None
    return width, height


def _validate_box_records(
    records: list[Any],
    field_name: str,
    canvas_size: tuple[float, float] | None,
    issues: list[str],
    require_type: bool,
) -> set[str]:
    seen_ids: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"{field_name}[{index}]"
        if not isinstance(record, Mapping):
            issues.append(f"{prefix} must be a mapping")
            continue

        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            issues.append(f"{prefix}.id must be a non-empty string")
        elif record_id in seen_ids:
            issues.append(f"{prefix}.id duplicates {record_id!r}")
        else:
            seen_ids.add(record_id)

        if require_type:
            box_type = record.get("type")
            if box_type not in CONTROLLED_BOX_TYPES:
                issues.append(f"{prefix}.type must be one of {sorted(CONTROLLED_BOX_TYPES)}")

        bbox = _parse_bbox_sequence(record.get("bbox"))
        if bbox is None:
            issues.append(f"{prefix}.bbox must contain four finite numbers")
        else:
            _validate_bbox_bounds(prefix, bbox, canvas_size, issues)
        if "geometry" in record:
            geometry = normalize_asset_geometry(record.get("geometry"), fallback_bbox=bbox, image_size=canvas_size)
            if geometry is None:
                issues.append(f"{prefix}.geometry must be a bbox, polygon, or mask geometry")
    return seen_ids


def _validate_bbox_bounds(
    prefix: str,
    bbox: list[float],
    canvas_size: tuple[float, float] | None,
    issues: list[str],
) -> None:
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        issues.append(f"{prefix}.bbox must have positive area")
        return
    if canvas_size is None:
        return
    width, height = canvas_size
    if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        issues.append(f"{prefix}.bbox must be clamped inside the canvas")


def _validate_relationships(records: list[Any], box_ids: set[str], issues: list[str]) -> None:
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        record_id = record.get("id")
        for field_name in ("parent_ids", "child_ids"):
            value = record.get(field_name, [])
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                issues.append(f"boxes[{index}].{field_name} must be a list of strings")
                continue
            for related_id in value:
                if related_id == record_id:
                    issues.append(f"boxes[{index}].{field_name} must not reference itself")
                elif related_id not in box_ids:
                    issues.append(f"boxes[{index}].{field_name} references unknown box id {related_id!r}")


def _reading_order_key(box: Mapping[str, Any]) -> tuple[float, float, float, float, int]:
    bbox = box["bbox"]
    return (bbox[1], bbox[0], bbox[3], bbox[2], int(box.get("source_region_index", 0)))


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return deepcopy(value)
    return repr(value)
