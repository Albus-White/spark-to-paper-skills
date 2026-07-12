from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from drawai.asset_geometry import geometry_bbox, normalize_geometry_from_region
from drawai.domain.box_ir import normalize_box_type

from .schema import ElementCandidate, validate_bbox, validate_element_candidate

_COORDINATE_SYSTEM = "figure_image_pixels"
_DEFAULT_SAM_PARSER_ID = "sam3_structure_parser"
_DEFAULT_OCR_PARSER_ID = "ocr_text_parser"
_DEFAULT_SAM_PREFIX = "sam3"
_DEFAULT_OCR_PREFIX = "ocr"
_V2_ELEMENT_TYPES = frozenset(
    {
        "text",
        "icon",
        "picture",
        "table",
        "chart",
        "diagram",
        "arrow",
        "frame",
        "grid",
        "symbol",
        "content_box",
        "unknown",
    }
)
_LEGACY_TO_V2_TYPE = {"border": "frame"}


def sam3_payload_to_candidates(
    payload: Mapping[str, Any],
    source_image: str | Path,
    parser_id: str = _DEFAULT_SAM_PARSER_ID,
    parser_priority: int = 10,
) -> tuple[ElementCandidate, ...]:
    raw_regions = _required_list(payload, "raw_regions", payload_name="SAM3 payload")
    source_image_size = _source_image_size(source_image)
    candidate_prefix = _candidate_prefix(
        parser_id,
        default_parser_id=_DEFAULT_SAM_PARSER_ID,
        default_prefix=_DEFAULT_SAM_PREFIX,
    )
    candidates: list[ElementCandidate] = []
    for index, raw_region in enumerate(raw_regions, start=1):
        if not isinstance(raw_region, Mapping):
            raise ValueError(f"raw_regions[{index - 1}] must be a mapping")
        bbox, geometry = _sam_bbox_and_geometry(
            raw_region,
            field_name=f"raw_regions[{index - 1}].bbox",
            image_size=source_image_size,
        )
        element_type = _sam_element_type(raw_region)
        mask_path = _mask_path_from_region(raw_region)
        candidate = ElementCandidate(
            candidate_id=f"{candidate_prefix}:B{index:03d}",
            source_parser=parser_id,
            source_parser_version="v1",
            element_type=element_type,
            bbox=bbox,
            geometry=geometry,
            confidence=_confidence(
                _confidence_value(raw_region),
                field_name=f"raw_regions[{index - 1}].score",
            ),
            z_hint=_z_hint(
                raw_region.get("z_hint"),
                field_name=f"raw_regions[{index - 1}].z_hint",
            ),
            text="",
            evidence_files=(mask_path,) if mask_path else (),
            provenance={
                "source_image": str(source_image),
                "parser_priority": parser_priority,
                "payload_field": "raw_regions",
                "payload_index": index - 1,
                "bbox_format": "xyxy",
            },
            raw_ref={
                "source_image": str(source_image),
                "field": "raw_regions",
                "index": index - 1,
            },
        )
        validate_element_candidate(candidate)
        candidates.append(candidate)
    return tuple(candidates)


def ocr_payload_to_candidates(
    payload: Mapping[str, Any],
    source_image: str | Path,
    parser_id: str = _DEFAULT_OCR_PARSER_ID,
    parser_priority: int = 5,
) -> tuple[ElementCandidate, ...]:
    raw_boxes = _required_list(payload, "ocr_text_boxes", payload_name="OCR payload")
    candidate_prefix = _candidate_prefix(
        parser_id,
        default_parser_id=_DEFAULT_OCR_PARSER_ID,
        default_prefix=_DEFAULT_OCR_PREFIX,
    )
    candidates: list[ElementCandidate] = []
    for index, raw_box in enumerate(raw_boxes):
        if not isinstance(raw_box, Mapping):
            raise ValueError(f"ocr_text_boxes[{index}] must be a mapping")
        source_id = _required_text(
            raw_box.get("id"),
            field_name=f"ocr_text_boxes[{index}].id",
        )
        bbox = _xyxy_to_bbox(
            raw_box.get("bbox"),
            field_name=f"ocr_text_boxes[{index}].bbox",
        )
        candidate = ElementCandidate(
            candidate_id=f"{candidate_prefix}:{source_id}",
            source_parser=parser_id,
            source_parser_version="v1",
            element_type="text",
            bbox=bbox,
            geometry={
                "kind": "bbox",
                "bbox": _bbox_to_xyxy(bbox),
                "coordinate_system": _COORDINATE_SYSTEM,
            },
            confidence=_confidence(
                raw_box.get("confidence"),
                field_name=f"ocr_text_boxes[{index}].confidence",
            ),
            z_hint=_z_hint(
                raw_box.get("z_hint"),
                field_name=f"ocr_text_boxes[{index}].z_hint",
            ),
            text=str(raw_box.get("text") or ""),
            evidence_files=(),
            provenance={
                "source_image": str(source_image),
                "parser_priority": parser_priority,
                "payload_field": "ocr_text_boxes",
                "payload_index": index,
                "bbox_format": "xyxy",
            },
            raw_ref={
                "source_image": str(source_image),
                "field": "ocr_text_boxes",
                "id": source_id,
                "index": index,
            },
        )
        validate_element_candidate(candidate)
        candidates.append(candidate)
    return tuple(candidates)


def _candidate_prefix(
    parser_id: str,
    *,
    default_parser_id: str,
    default_prefix: str,
) -> str:
    if parser_id == default_parser_id:
        return default_prefix
    slug = _parser_slug(parser_id)
    if slug == default_prefix:
        return f"{slug}_parser"
    return slug


def _parser_slug(parser_id: str) -> str:
    if not isinstance(parser_id, str) or not parser_id.strip():
        raise ValueError("parser_id is required")
    slug = re.sub(r"[^a-z0-9]+", "_", parser_id.strip().lower()).strip("_")
    if not slug:
        raise ValueError("parser_id must contain at least one alphanumeric character")
    return slug


def _source_image_size(source_image: str | Path) -> tuple[int, int] | None:
    path = Path(source_image)
    if not path.is_file():
        return None
    with Image.open(path) as image:
        return image.size


def _required_list(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    payload_name: str,
) -> list[Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{payload_name} must be a mapping")
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{payload_name} field {field_name!r} must be a list")
    return value


def _xyxy_to_bbox(raw_bbox: Any, *, field_name: str) -> tuple[float, float, float, float]:
    if (
        isinstance(raw_bbox, str | bytes)
        or not isinstance(raw_bbox, Sequence)
        or len(raw_bbox) != 4
    ):
        raise ValueError(f"{field_name} must contain [x1, y1, x2, y2]")
    x1, y1, x2, y2 = (_finite_number(value, field_name=field_name) for value in raw_bbox)
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"{field_name} must have x2 > x1 and y2 > y1")
    return validate_bbox((x1, y1, x2 - x1, y2 - y1))


def _bbox_to_xyxy(bbox: tuple[float, float, float, float]) -> list[float]:
    left, top, width, height = bbox
    return [left, top, left + width, top + height]


def _finite_number(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must contain finite numbers")
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        number = float(value.strip())
    else:
        raise ValueError(f"{field_name} must contain finite numbers")
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must contain finite numbers")
    return number


def _confidence(raw_value: Any, *, field_name: str) -> float:
    if raw_value is None:
        return 0.0
    value = _finite_number(raw_value, field_name=field_name)
    if value < 0 or value > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return value


def _confidence_value(region: Mapping[str, Any]) -> Any:
    if "score" in region:
        return region["score"]
    return region.get("confidence")


def _z_hint(raw_value: Any, *, field_name: str) -> int | None:
    if raw_value is None:
        return None
    value = _finite_number(raw_value, field_name=field_name)
    if not value.is_integer():
        raise ValueError(f"{field_name} must be an integer")
    return int(value)


def _required_text(raw_value: Any, *, field_name: str) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(f"{field_name} is required")
    return raw_value.strip()


def _sam_element_type(region: Mapping[str, Any]) -> str:
    for field_name in ("source_prompt",):
        element_type = _normalized_type_value(region.get(field_name))
        if element_type != "unknown":
            return element_type
    for field_name in (
        "type",
        "label",
        "text",
        "class",
        "class_name",
        "category",
        "name",
    ):
        element_type = _normalized_type_value(region.get(field_name))
        if element_type != "unknown":
            return element_type
    return "unknown"


def _normalized_type_value(raw_value: Any) -> str:
    normalized = normalize_box_type(raw_value)
    normalized = _LEGACY_TO_V2_TYPE.get(normalized, normalized)
    if normalized in _V2_ELEMENT_TYPES and normalized != "unknown":
        return normalized
    if isinstance(raw_value, Mapping):
        for field_name in (
            "id",
            "type",
            "label",
            "text",
            "class",
            "class_name",
            "category",
            "name",
        ):
            element_type = _normalized_type_value(raw_value.get(field_name))
            if element_type != "unknown":
                return element_type
    if isinstance(raw_value, str):
        direct = raw_value.strip().lower().replace("-", "_").replace(" ", "_").strip("_")
        if direct in _V2_ELEMENT_TYPES:
            return direct
    return "unknown"


def _sam_bbox_and_geometry(
    region: Mapping[str, Any],
    *,
    field_name: str,
    image_size: tuple[int, int] | None,
) -> tuple[tuple[float, float, float, float], dict[str, Any]]:
    bbox = _optional_xyxy_to_bbox(region.get("bbox"), field_name=field_name)
    raw_geometry = normalize_geometry_from_region(
        region,
        fallback_bbox=_bbox_to_xyxy(bbox) if bbox is not None else None,
        image_size=image_size,
    )
    if raw_geometry is not None:
        geometry_xyxy = geometry_bbox(raw_geometry)
        if bbox is None:
            if geometry_xyxy is None:
                raise ValueError(f"{field_name} or derivable geometry bbox is required")
            bbox = _xyxy_to_bbox(geometry_xyxy, field_name="geometry.bbox")
        return bbox, _geometry_with_v2_bbox(raw_geometry)
    if bbox is None:
        raise ValueError(f"{field_name} must contain [x1, y1, x2, y2]")
    return bbox, {
        "kind": "bbox",
        "bbox": _bbox_to_xyxy(bbox),
        "coordinate_system": _COORDINATE_SYSTEM,
    }


def _optional_xyxy_to_bbox(
    raw_bbox: Any,
    *,
    field_name: str,
) -> tuple[float, float, float, float] | None:
    if raw_bbox is None:
        return None
    return _xyxy_to_bbox(raw_bbox, field_name=field_name)


def _geometry_with_v2_bbox(geometry: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(geometry)
    raw_bbox = geometry_bbox(geometry)
    if raw_bbox is not None:
        normalized["bbox"] = list(raw_bbox)
    return normalized


def _mask_path_from_region(region: Mapping[str, Any]) -> str:
    mask_path = _raw_mask_path(region)
    raw_geometry = region.get("geometry")
    if mask_path or not isinstance(raw_geometry, Mapping):
        return mask_path
    return _raw_mask_path(raw_geometry)


def _raw_mask_path(raw: Mapping[str, Any]) -> str:
    for field_name in ("mask_path", "path", "alpha_mask_path"):
        value = raw.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
