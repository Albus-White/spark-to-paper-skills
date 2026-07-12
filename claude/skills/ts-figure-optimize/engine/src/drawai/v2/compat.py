from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from drawai.artifacts import prepare_artifact_paths, write_json
from drawai.asset_geometry import normalize_asset_geometry
from drawai.domain.box_ir import BOX_IR_SCHEMA, BOX_IR_VERSION, build_svg_template_ir, validate_box_ir

from .schema import AssetPackage, ElementPlan


def write_box_ir_compat(
    root: str | Path,
    elements: Sequence[ElementPlan],
    source_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    paths = prepare_artifact_paths(root)
    box_ir = _box_ir_payload(paths.figure_image, elements, source_metadata)
    issues = validate_box_ir(box_ir)
    if issues:
        raise ValueError("Invalid v2-derived BoxIR compatibility payload: " + "; ".join(issues))
    write_json(paths.box_ir_json, box_ir)
    write_json(paths.box_ir_merged_json, box_ir)
    write_json(paths.box_ir_raw_json, box_ir)
    write_json(paths.merge_trace_json, box_ir["merge_trace"])
    write_json(paths.box_merge_diagnostics_json, _merge_diagnostics(box_ir))
    write_json(paths.svg_template_ir_json, build_svg_template_ir(box_ir))
    return box_ir


def write_element_analysis_compat(
    root: str | Path,
    elements: Sequence[ElementPlan],
) -> dict[str, Any]:
    paths = prepare_artifact_paths(root)
    payload = {
        "schema": "drawai.codex_element_analysis.v1",
        "source": "v2.refined_elements",
        "elements": [_element_analysis_record(element) for element in elements],
    }
    write_json(paths.element_analysis_json, payload)
    write_json(
        paths.element_analysis_validation_json,
        {
            "schema": "drawai.codex_element_analysis_validation.v1",
            "status": "ok",
            "source": "v2.compat",
            "element_count": len(elements),
        },
    )
    write_json(
        paths.element_analysis_status_json,
        {
            "schema": "drawai.codex_element_analysis_status.v1",
            "status": "ok",
            "source": "v2.compat",
        },
    )
    return payload


def write_asset_manifest_compat(
    root: str | Path,
    asset_packages: Sequence[AssetPackage | Mapping[str, Any]],
) -> dict[str, Any]:
    paths = prepare_artifact_paths(root)
    payload = {
        "schema": "drawai.asset_manifest.v1",
        "source": "v2.asset_packages",
        "assets": [_asset_manifest_record(package) for package in asset_packages],
    }
    write_json(paths.asset_manifest_json, payload)
    return payload


def _box_ir_payload(
    source_image: Path,
    elements: Sequence[ElementPlan],
    source_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    width, height = _canvas_size(source_metadata)
    boxes: list[dict[str, Any]] = []
    ocr_text_boxes: list[dict[str, Any]] = []
    for element in sorted(elements, key=lambda item: (item.z_order, item.element_id)):
        bbox_xyxy = _xywh_to_xyxy(element.bbox)
        if element.element_type == "text":
            ocr_text_boxes.append(
                {
                    "id": element.element_id,
                    "bbox": bbox_xyxy,
                    "text": _element_text(element),
                    "confidence": _confidence_score(element.confidence),
                    "source": "v2",
                    "source_candidate_ids": list(element.source_candidate_ids),
                }
            )
            continue
        geometry = _box_ir_geometry(
            element.geometry,
            bbox_xyxy,
            image_size=(width, height),
        )
        record = {
            "id": element.element_id,
            "type": _legacy_box_type(element.element_type),
            "bbox": bbox_xyxy,
            "geometry": geometry,
            "parent_ids": [],
            "child_ids": [],
            "source_candidate_ids": list(element.source_candidate_ids),
            "score": _confidence_score(element.confidence),
        }
        if _jsonable(element.geometry) != geometry:
            record["v2_geometry"] = _jsonable(element.geometry)
        boxes.append(
            record
        )
    return {
        "schema": BOX_IR_SCHEMA,
        "version": BOX_IR_VERSION,
        "canvas": {"width": width, "height": height},
        "source": {
            "image": str(source_image),
            "normalized_long_edge": max(width, height),
            "coordinate_system": "figure_image_pixels",
        },
        "prompt_runs": [],
        "boxes": boxes,
        "ocr_text_boxes": ocr_text_boxes,
        "merge_trace": {
            "schema": "drawai.box_ir.merge_trace.v1",
            "source": "v2.fuse_elements",
            "decisions": [],
        },
    }


def _element_analysis_record(element: ElementPlan) -> dict[str, Any]:
    return {
        "box_id": element.element_id,
        "element_id": element.element_id,
        "source_candidate_ids": list(element.source_candidate_ids),
        "refinement_action": "unchanged",
        "category": element.processing_intent.processing_type,
        "confidence": element.confidence,
        "visual_role": element.element_type,
        "reason": element.change_reason,
        "bbox": _xywh_to_xyxy(element.bbox),
        "type": element.element_type,
        "geometry": _jsonable(element.geometry),
        "processing_parameters": _jsonable(element.processing_intent.parameters),
        "review_status": element.review_status,
    }


def _box_ir_geometry(
    geometry: Mapping[str, Any],
    fallback_bbox: Sequence[float],
    *,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    normalized = normalize_asset_geometry(geometry, fallback_bbox=fallback_bbox, image_size=image_size)
    if normalized is not None:
        return normalized
    return {
        "kind": "bbox",
        "bbox": [float(value) for value in fallback_bbox],
        "coordinate_system": "figure_image_pixels",
    }


def _asset_manifest_record(package: AssetPackage | Mapping[str, Any]) -> dict[str, Any]:
    payload = package.to_dict() if isinstance(package, AssetPackage) else dict(package)
    active_result = payload.get("active_result") if isinstance(payload.get("active_result"), Mapping) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    path = active_result.get("path") if isinstance(active_result, Mapping) else None
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    record: dict[str, Any] = {
        "asset_id": payload.get("asset_id"),
        "element_id": payload.get("element_id"),
        "box_id": payload.get("element_id"),
        "processor_type": payload.get("processor_type"),
        "status": payload.get("status"),
        "files": files,
        "active_variant": "v2_active_result" if path else None,
        "metadata": _jsonable(metadata),
    }
    if isinstance(path, str) and path:
        record["path"] = path
        record["svg_href"] = _svg_href(path)
    if isinstance(active_result, Mapping):
        for key in ("width", "height"):
            if key in active_result:
                record[key] = active_result[key]
    return record


def _canvas_size(source_metadata: Mapping[str, Any]) -> tuple[int, int]:
    raw_size = source_metadata.get("normalized_size")
    if not isinstance(raw_size, Sequence) or isinstance(raw_size, str) or len(raw_size) != 2:
        raise ValueError("source metadata must contain normalized_size [width, height]")
    width = int(raw_size[0])
    height = int(raw_size[1])
    if width <= 0 or height <= 0:
        raise ValueError("source metadata normalized_size must be positive")
    return width, height


def _xywh_to_xyxy(bbox: Sequence[float]) -> list[float]:
    left, top, width, height = (float(value) for value in bbox)
    return [left, top, left + width, top + height]


def _legacy_box_type(element_type: str) -> str:
    if element_type == "frame":
        return "border"
    if element_type == "table":
        return "grid"
    if element_type in {"chart", "diagram"}:
        return "content_box"
    return element_type


def _element_text(element: ElementPlan) -> str:
    text = element.processing_intent.parameters.get("text")
    return text if isinstance(text, str) else ""


def _confidence_score(confidence: str) -> float:
    if confidence == "high":
        return 0.95
    if confidence == "medium":
        return 0.7
    return 0.4


def _merge_diagnostics(box_ir: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "drawai.box_ir.merge_diagnostics.v1",
        "status": "ok",
        "source": "v2.compat",
        "raw_box_count": len(box_ir.get("boxes", [])),
        "merged_box_count": len(box_ir.get("boxes", [])),
        "removed_or_merged_box_count": 0,
        "warnings": [],
    }


def _svg_href(path: str) -> str:
    if path.startswith("svg_to_ppt/assets/"):
        return path.removeprefix("svg_to_ppt/")
    return path


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value
