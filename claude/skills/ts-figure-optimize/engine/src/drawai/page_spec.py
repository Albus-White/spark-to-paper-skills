from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from drawai.v2.schema import ElementCandidate

PAGE_SPEC_SCHEMA = "drawai.page_spec.v1"

PAGE_ELEMENT_KINDS = {
    "text",
    "shape",
    "image",
    "diagram",
    "connector",
    "table",
    "chart",
    "formula",
    "group",
    "unknown",
}

_ASSET_PROCESSING_TYPES = {"crop", "crop_nobg", "image_generate", "image_edit"}
_PROCESSING_TO_BUILD_MODE = {
    "no_process": "vector",
    "svg_self_draw": "asset_ref",
    "crop": "asset_ref",
    "crop_nobg": "asset_ref",
    "image_generate": "asset_ref",
    "image_edit": "asset_ref",
    "chart_rebuild_reserved": "structured",
}
_BUILD_MODE_TO_PROCESSING = {
    "vector": "no_process",
    "editable_text": "no_process",
    "vector_shape": "no_process",
    "connector": "no_process",
    "group": "no_process",
    "structured": "no_process",
}


def validate_page_spec_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema") != PAGE_SPEC_SCHEMA:
        raise ValueError(f"invalid page spec schema: {payload.get('schema')}")
    _require_string(payload, "page_id")
    _validate_mapping(payload.get("source", {}), "source")
    _validate_mapping(payload.get("canvas", {}), "canvas")
    background = payload.get("background")
    if background is not None:
        _validate_mapping(background, "background")
    elements = payload.get("elements")
    if isinstance(elements, str) or not isinstance(elements, Sequence):
        raise ValueError("page_spec.elements must be a list")

    seen_ids: set[str] = set()
    parent_ids: dict[str, str] = {}
    child_ids: dict[str, list[str]] = {}
    for index, raw_element in enumerate(elements):
        if not isinstance(raw_element, Mapping):
            raise ValueError(f"elements[{index}] must be a mapping")
        element_id = _require_string(raw_element, "id", field_prefix=f"elements[{index}]")
        if element_id in seen_ids:
            raise ValueError(f"duplicate page element id: {element_id}")
        seen_ids.add(element_id)
        kind = _require_string(raw_element, "kind", field_prefix=f"elements[{index}]")
        if kind not in PAGE_ELEMENT_KINDS:
            raise ValueError(f"elements[{index}].kind is not supported: {kind}")
        _validate_geometry(raw_element, f"elements[{index}]")
        _validate_mapping(raw_element.get("build", {}), f"elements[{index}].build")
        _validate_mapping(raw_element.get("style", {}), f"elements[{index}].style")
        _validate_mapping(raw_element.get("metadata", {}), f"elements[{index}].metadata")
        _validate_mapping(raw_element.get("measurement", {}), f"elements[{index}].measurement")
        _validate_json_value(raw_element.get("source_refs", []), f"elements[{index}].source_refs")
        if raw_element.get("materialization") is not None:
            _validate_mapping(raw_element.get("materialization", {}), f"elements[{index}].materialization")
        parent_id = raw_element.get("parent_id")
        if isinstance(parent_id, str) and parent_id:
            parent_ids[element_id] = parent_id
        children = raw_element.get("children", [])
        if children is not None:
            if isinstance(children, str) or not isinstance(children, Sequence):
                raise ValueError(f"elements[{index}].children must be a list")
            child_ids[element_id] = [str(item) for item in children if str(item)]

    missing_parents = sorted(parent for parent in parent_ids.values() if parent not in seen_ids)
    if missing_parents:
        raise ValueError(f"page_spec references missing parent ids: {', '.join(missing_parents)}")
    missing_children = sorted({child for children in child_ids.values() for child in children if child not in seen_ids})
    if missing_children:
        raise ValueError(f"page_spec references missing child ids: {', '.join(missing_children)}")
    _validate_group_cycles(parent_ids)


def page_spec_from_candidates(
    candidates: Sequence[ElementCandidate | Mapping[str, Any]],
    *,
    page_id: str,
    source_image: str = "",
    canvas: Mapping[str, Any] | None = None,
    producer: str,
) -> dict[str, Any]:
    canvas_payload = _mapping(canvas or {}, "canvas")
    page_spec = {
        "schema": PAGE_SPEC_SCHEMA,
        "page_id": page_id,
        "source": {
            "image": source_image,
            "width_px": canvas_payload.get("width_px", canvas_payload.get("width")),
            "height_px": canvas_payload.get("height_px", canvas_payload.get("height")),
        },
        "canvas": {
            "width_px": canvas_payload.get("width_px", canvas_payload.get("width")),
            "height_px": canvas_payload.get("height_px", canvas_payload.get("height")),
        },
        "background": {},
        "elements": [
            page_element_from_candidate_payload(_candidate_payload(candidate))
            for candidate in candidates
        ],
        "metadata": {},
    }
    validate_page_spec_payload(page_spec)
    return page_spec


def fuse_page_specs(
    payloads: Sequence[Mapping[str, Any]],
    *,
    page_id: str,
    source_image: str = "",
    producer: str = "page_spec_fuse",
) -> dict[str, Any]:
    if not payloads:
        raise ValueError("page spec fuse requires at least one PageSpec input")

    validated = [dict(payload) for payload in payloads]
    for payload in validated:
        validate_page_spec_payload(payload)

    canvas = _fused_canvas(validated)
    source = _fused_source(validated, source_image=source_image, canvas=canvas)
    fused_elements: list[dict[str, Any]] = []
    for payload in validated:
        raw_elements = payload.get("elements")
        if isinstance(raw_elements, str) or not isinstance(raw_elements, Sequence):
            continue
        for raw_element in raw_elements:
            if not isinstance(raw_element, Mapping):
                continue
            if _is_duplicate_fused_element(fused_elements, raw_element):
                continue
            fused_elements.append(
                _canonical_fused_element(
                    raw_element,
                    new_id=f"E{len(fused_elements) + 1:03d}",
                    fuse_node_id=producer,
                )
            )

    page_spec = {
        "schema": PAGE_SPEC_SCHEMA,
        "page_id": page_id,
        "source": source,
        "canvas": canvas,
        "background": {},
        "elements": fused_elements,
        "metadata": {},
    }
    validate_page_spec_payload(page_spec)
    return page_spec


def page_element_from_candidate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    candidate_id = _require_string(payload, "candidate_id")
    element_type = str(payload.get("element_type") or "unknown")
    kind = _page_kind_from_element_type(element_type, _candidate_processing_type(element_type))
    bbox = _bbox4(payload.get("bbox"), "candidate.bbox")
    text = str(payload.get("text") or "")
    build: dict[str, Any] = {
        "mode": _candidate_build_mode(kind, element_type),
        "processing_type": _candidate_processing_type(element_type),
    }
    if build["mode"] == "asset_ref":
        build["asset_id"] = _asset_id_from_candidate_id(candidate_id)
    element: dict[str, Any] = {
        "id": _element_id_from_candidate_id(candidate_id),
        "kind": kind,
        "role": element_type,
        "box_px": list(bbox),
        "z_index": int(payload.get("z_hint", 0) or 0),
        "confidence": float(payload.get("confidence", 0.0) or 0.0),
        "geometry": _mapping(payload.get("geometry", {}), "candidate.geometry"),
        "source_refs": [{"kind": "candidate", "id": candidate_id}],
        "build": build,
        "measurement": {
            "text": text,
            "confidence": payload.get("confidence"),
        } if text else {"confidence": payload.get("confidence")},
        "metadata": {
            "source_parser": str(payload.get("source_parser") or ""),
            "source_parser_version": str(payload.get("source_parser_version") or ""),
            "parser_element_type": element_type,
        },
    }
    if text:
        element["text"] = text
    return element


def load_page_spec(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("page spec must be a JSON object")
    page_spec = dict(payload)
    validate_page_spec_payload(page_spec)
    return page_spec


def write_page_spec(path: str | Path, payload: Mapping[str, Any]) -> Path:
    validate_page_spec_payload(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _page_kind_from_element_type(element_type: str, processing_type: str) -> str:
    if element_type == "text":
        return "text"
    if element_type in {"arrow"}:
        return "connector"
    if element_type == "diagram":
        return "diagram"
    if element_type in {"table", "chart"}:
        return element_type
    if processing_type in _ASSET_PROCESSING_TYPES or element_type in {"icon", "picture", "symbol"}:
        return "image"
    if element_type in {"frame", "grid", "content_box"}:
        return "shape"
    return "unknown"


def _candidate_payload(candidate: ElementCandidate | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(candidate, ElementCandidate):
        return candidate.to_dict()
    if isinstance(candidate, Mapping):
        return dict(candidate)
    raise ValueError("candidate must be an ElementCandidate or mapping")


def _candidate_build_mode(kind: str, element_type: str) -> str:
    if kind == "text":
        return "editable_text"
    if kind in {"shape", "diagram", "connector", "table", "chart", "formula"}:
        return "vector"
    if element_type in {"picture", "icon", "symbol", "unknown"}:
        return "asset_ref"
    return "vector"


def _candidate_processing_type(element_type: str) -> str:
    if element_type in {"picture", "icon", "symbol", "unknown"}:
        return "crop"
    return "no_process"


def _element_id_from_candidate_id(candidate_id: str) -> str:
    slug = candidate_id.replace(":", "_").replace("-", "_")
    return f"C_{slug}"


def _asset_id_from_candidate_id(candidate_id: str) -> str:
    slug = candidate_id.replace(":", "_").replace("-", "_")
    return f"A_{slug}"


def _fused_canvas(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for payload in payloads:
        canvas = _mapping(payload.get("canvas", {}), "canvas")
        width = canvas.get("width_px", canvas.get("width"))
        height = canvas.get("height_px", canvas.get("height"))
        if width is not None and height is not None:
            return {"width_px": width, "height_px": height}
    return {}


def _fused_source(
    payloads: Sequence[Mapping[str, Any]],
    *,
    source_image: str,
    canvas: Mapping[str, Any],
) -> dict[str, Any]:
    for payload in payloads:
        source = _mapping(payload.get("source", {}), "source")
        image = source_image or str(source.get("image") or "")
        if image or source:
            return {
                "image": image,
                "width_px": source.get("width_px", canvas.get("width_px")),
                "height_px": source.get("height_px", canvas.get("height_px")),
            }
    return {
        "image": source_image,
        "width_px": canvas.get("width_px"),
        "height_px": canvas.get("height_px"),
    }


def _canonical_fused_element(
    raw_element: Mapping[str, Any],
    *,
    new_id: str,
    fuse_node_id: str,
) -> dict[str, Any]:
    old_id = _require_string(raw_element, "id")
    kind = _require_string(raw_element, "kind")
    build = _mapping(raw_element.get("build", {}), f"{old_id}.build")
    build = _normalized_build(build, new_id)
    source_label = _element_source_label(raw_element)
    source_refs = _normalized_source_refs(raw_element.get("source_refs"), old_id=old_id, source_label=source_label)
    element: dict[str, Any] = {
        "id": new_id,
        "kind": kind,
        "role": str(raw_element.get("role") or kind),
        "box_px": list(_bbox4(raw_element.get("box_px"), f"{old_id}.box_px")),
        "z_index": int(raw_element.get("z_index", 0) or 0),
        "confidence": raw_element.get("confidence", "medium"),
        "geometry": _mapping(raw_element.get("geometry", {}), f"{old_id}.geometry"),
        "source_refs": source_refs,
        "build": build,
        "style": _mapping(raw_element.get("style", {}), f"{old_id}.style"),
        "measurement": _mapping(raw_element.get("measurement", {}), f"{old_id}.measurement"),
        "metadata": {
            **_mapping(raw_element.get("metadata", {}), f"{old_id}.metadata"),
            "fusion": {
                "fused_by": fuse_node_id,
                "source_element_id": old_id,
                "source": source_label,
            },
        },
    }
    for optional_field in ("text", "points_px", "polygon_px", "parent_id", "children"):
        if optional_field in raw_element:
            element[optional_field] = raw_element[optional_field]
    return element


def _normalized_build(build: Mapping[str, Any], element_id: str) -> dict[str, Any]:
    mode = str(build.get("mode") or "")
    processing_type = str(build.get("processing_type") or "")
    if not mode:
        mode = _PROCESSING_TO_BUILD_MODE.get(processing_type, "vector")
    if not processing_type:
        processing_type = "crop" if mode == "asset_ref" else _BUILD_MODE_TO_PROCESSING.get(mode, "no_process")
    normalized = dict(build)
    normalized["mode"] = mode
    normalized["processing_type"] = processing_type
    if mode == "asset_ref" and not str(normalized.get("asset_id") or ""):
        normalized["asset_id"] = f"A{element_id.removeprefix('E')}"
    return normalized


def _normalized_source_refs(raw_refs: Any, *, old_id: str, source_label: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = [
        {
            "kind": "page_spec_element",
            "id": old_id,
            "source": source_label,
        }
    ]
    if isinstance(raw_refs, str) or not isinstance(raw_refs, Sequence):
        return refs
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, Mapping):
            continue
        ref = dict(raw_ref)
        if ref not in refs:
            refs.append(ref)
    return refs


def _element_source_label(element: Mapping[str, Any]) -> str:
    metadata = element.get("metadata")
    if isinstance(metadata, Mapping):
        parser = metadata.get("source_parser")
        if isinstance(parser, str) and parser:
            return parser
    for raw_ref in element.get("source_refs", []):
        if not isinstance(raw_ref, Mapping):
            continue
        ref_id = raw_ref.get("id")
        if isinstance(ref_id, str) and ref_id:
            if ref_id.startswith("sam") or ref_id.startswith("SAM"):
                return "sam"
            if ref_id.startswith("ocr") or ref_id.startswith("OCR"):
                return "ocr"
    return "page_spec"


def _is_duplicate_fused_element(
    existing_elements: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
) -> bool:
    candidate_kind = str(candidate.get("kind") or "")
    candidate_role = str(candidate.get("role") or "")
    candidate_text = str(candidate.get("text") or "")
    candidate_bbox = _bbox4(candidate.get("box_px"), "candidate.box_px")
    for existing in existing_elements:
        if str(existing.get("kind") or "") != candidate_kind:
            continue
        if candidate_kind == "text" and candidate_text and str(existing.get("text") or "") != candidate_text:
            continue
        if candidate_role and str(existing.get("role") or "") not in {"", candidate_role}:
            continue
        existing_bbox = _bbox4(existing.get("box_px"), "existing.box_px")
        if _bbox_iou_xywh(existing_bbox, candidate_bbox) >= 0.92:
            return True
    return False


def _bbox_iou_xywh(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    first_x1, first_y1, first_w, first_h = first
    second_x1, second_y1, second_w, second_h = second
    first_x2 = first_x1 + first_w
    first_y2 = first_y1 + first_h
    second_x2 = second_x1 + second_w
    second_y2 = second_y1 + second_h
    inter_w = max(0.0, min(first_x2, second_x2) - max(first_x1, second_x1))
    inter_h = max(0.0, min(first_y2, second_y2) - max(first_y1, second_y1))
    intersection = inter_w * inter_h
    union = first_w * first_h + second_w * second_h - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _validate_geometry(payload: Mapping[str, Any], field_prefix: str) -> None:
    if "box_px" in payload:
        _bbox4(payload["box_px"], f"{field_prefix}.box_px")
    if "points_px" in payload:
        _points4(payload["points_px"], f"{field_prefix}.points_px")
    if "polygon_px" in payload:
        polygon = payload["polygon_px"]
        if isinstance(polygon, str) or not isinstance(polygon, Sequence):
            raise ValueError(f"{field_prefix}.polygon_px must be a list")
        for index, point in enumerate(polygon):
            if isinstance(point, str) or not isinstance(point, Sequence) or len(point) != 2:
                raise ValueError(f"{field_prefix}.polygon_px[{index}] must contain two numbers")
            _finite_float(point[0], f"{field_prefix}.polygon_px[{index}][0]")
            _finite_float(point[1], f"{field_prefix}.polygon_px[{index}][1]")


def _validate_group_cycles(parent_ids: Mapping[str, str]) -> None:
    for element_id in parent_ids:
        seen: set[str] = set()
        current = element_id
        while current in parent_ids:
            current = parent_ids[current]
            if current in seen:
                raise ValueError(f"page_spec group cycle detected at {current}")
            seen.add(current)


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return dict(value)


def _validate_mapping(value: object, field_name: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    _validate_json_value(value, field_name)


def _validate_json_value(value: object, field_name: str) -> None:
    if value is None or isinstance(value, str | bool):
        return
    if isinstance(value, int | float) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError(f"{field_name} must be finite")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} keys must be strings")
            _validate_json_value(item, f"{field_name}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{field_name}[{index}]")
        return
    raise ValueError(f"{field_name} must be JSON-compatible")


def _require_string(payload: Mapping[str, Any], field_name: str, *, field_prefix: str = "") -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        prefix = f"{field_prefix}." if field_prefix else ""
        raise ValueError(f"{prefix}{field_name} is required")
    return value


def _bbox4(value: Any, field_name: str) -> tuple[float, float, float, float]:
    if isinstance(value, str) or not isinstance(value, Sequence) or len(value) != 4:
        raise ValueError(f"{field_name} must contain four numbers")
    x, y, width, height = (_finite_float(item, field_name) for item in value)
    if width <= 0 or height <= 0:
        raise ValueError(f"{field_name} must have positive width and height")
    return (x, y, width, height)


def _points4(value: Any, field_name: str) -> tuple[float, float, float, float]:
    if isinstance(value, str) or not isinstance(value, Sequence) or len(value) != 4:
        raise ValueError(f"{field_name} must contain four numbers")
    return tuple(_finite_float(item, field_name) for item in value)  # type: ignore[return-value]


def _finite_float(value: Any, field_name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must contain finite numbers")
    return result
