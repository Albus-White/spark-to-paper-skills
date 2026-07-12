from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .schema import ElementPlan, ProcessingIntent, validate_element_plan

CODEX_ELEMENT_ANALYSIS_SCHEMA = "drawai.codex_element_analysis.v1"
REFINED_ELEMENT_PLANS_EXPORT_SCHEMA = "drawai.refined_element_plans.v1"
REMOVAL_ACTIONS = {"removed", "merged"}
CORE_ELEMENT_TYPES = {
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
ELEMENT_TYPE_ALIASES = {
    "asset": "unknown",
    "border": "frame",
    "box": "content_box",
    "container": "content_box",
    "content": "content_box",
    "contentbox": "content_box",
    "image": "picture",
    "photo": "picture",
    "photograph": "picture",
    "shape": "symbol",
}


@dataclass(frozen=True)
class RefineConfig:
    enabled: bool = True
    provider: str = "codex_element_refiner"


class RefinementValidationError(ValueError):
    """Raised when agent-refined elements violate the v2 refinement contract."""


class CodexElementRefiner:
    def __init__(self, config: RefineConfig | None = None) -> None:
        self.config = config or RefineConfig()

    def convert_analysis(
        self,
        analysis: Mapping[str, Any],
        *,
        expected_candidate_ids: set[str],
        locked_geometry_by_candidate: Mapping[str, Mapping[str, Any]],
    ) -> tuple[ElementPlan, ...]:
        plans = codex_analysis_to_v2_element_plans(analysis)
        removal_records = codex_analysis_to_v2_removal_records(analysis)
        return validate_refined_elements(
            (*plans, *removal_records),
            expected_candidate_ids=expected_candidate_ids,
            locked_geometry_by_candidate=locked_geometry_by_candidate,
        )


def validate_refined_elements(
    elements: Sequence[ElementPlan | Mapping[str, Any]],
    *,
    expected_candidate_ids: set[str],
    locked_geometry_by_candidate: Mapping[str, Mapping[str, Any]],
) -> tuple[ElementPlan, ...]:
    expected = _normalize_id_set(expected_candidate_ids, "expected_candidate_ids")
    locked_geometry = _normalize_locked_geometry(locked_geometry_by_candidate)
    retained: list[ElementPlan] = []
    retained_ids: list[str] = []
    covered_source_ids: set[str] = set()
    removed_source_ids: set[str] = set()

    for item in elements:
        if isinstance(item, ElementPlan):
            _validate_plan(item)
            _validate_locked_geometry(item, locked_geometry)
            source_ids = tuple(
                str(source_id) for source_id in item.source_candidate_ids
            )
            unexpected = sorted(set(source_ids) - expected)
            if unexpected:
                raise RefinementValidationError(
                    f"unexpected source candidates: {unexpected[:20]}"
                )
            retained.append(item)
            retained_ids.append(item.element_id)
            covered_source_ids.update(source_ids)
            continue

        if isinstance(item, Mapping):
            source_ids = _removal_source_ids(item)
            unexpected = sorted(set(source_ids) - expected)
            if unexpected:
                raise RefinementValidationError(
                    f"unexpected source candidates: {unexpected[:20]}"
                )
            removed_source_ids.update(source_ids)
            continue

        raise RefinementValidationError(
            f"refined element records must be ElementPlan or removal mappings: {type(item).__name__}"
        )

    duplicates = sorted(
        element_id
        for element_id in set(retained_ids)
        if retained_ids.count(element_id) > 1
    )
    if duplicates:
        raise RefinementValidationError(f"duplicate element_ids: {duplicates[:20]}")

    retained_and_removed = sorted(covered_source_ids & removed_source_ids)
    if retained_and_removed:
        raise RefinementValidationError(
            f"source candidates both retained and removed: {retained_and_removed[:20]}"
        )

    missing = sorted(expected - covered_source_ids - removed_source_ids)
    if missing:
        raise RefinementValidationError(f"missing source candidates: {missing[:20]}")

    return tuple(retained)


def codex_analysis_to_v2_element_plans(
    analysis: Mapping[str, Any],
) -> tuple[ElementPlan, ...]:
    raw_elements = _codex_analysis_elements(analysis)

    plans: list[ElementPlan] = []
    for raw_element in raw_elements:
        if _is_removal_record(raw_element):
            continue
        plans.append(_codex_element_to_plan(raw_element, z_order=len(plans)))
    return tuple(plans)


def codex_analysis_to_v2_removal_records(
    analysis: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    element_records, top_level_records = _codex_analysis_removal_records(analysis)
    return tuple(
        (
            *(_normalized_removal_record(raw_record) for raw_record in element_records),
            *(
                _normalized_removal_record(raw_record, trust_removal_container=True)
                for raw_record in top_level_records
            ),
        )
    )


def _codex_analysis_elements(
    analysis: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    if analysis.get("schema") != CODEX_ELEMENT_ANALYSIS_SCHEMA:
        raise ValueError(
            f"unexpected Codex element analysis schema: {analysis.get('schema')!r}"
        )
    raw_elements = analysis.get("elements")
    if not isinstance(raw_elements, list):
        raise ValueError("Codex element analysis must contain an elements list")

    elements: list[Mapping[str, Any]] = []
    for index, raw_element in enumerate(raw_elements):
        if not isinstance(raw_element, Mapping):
            raise ValueError(f"element analysis record {index} must be a mapping")
        elements.append(raw_element)
    return tuple(elements)


def _codex_analysis_removal_records(
    analysis: Mapping[str, Any],
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    element_records = tuple(
        raw_element
        for raw_element in _codex_analysis_elements(analysis)
        if _is_removal_record(raw_element)
    )
    raw_removal_records = analysis.get("removal_records", [])
    if raw_removal_records is None:
        raw_removal_records = []
    if not isinstance(raw_removal_records, list):
        raise ValueError("Codex element analysis removal_records must be a list")
    top_level_records: list[Mapping[str, Any]] = []
    for index, raw_record in enumerate(raw_removal_records):
        if not isinstance(raw_record, Mapping):
            raise ValueError(f"removal_records[{index}] must be a mapping")
        top_level_records.append(raw_record)
    return element_records, tuple(top_level_records)


def _codex_element_to_plan(
    element: Mapping[str, Any],
    *,
    z_order: int,
) -> ElementPlan:
    element_id = _required_string(
        element.get("element_id") or element.get("box_id"),
        "element_id",
    )
    bbox_xyxy = _xyxy_bbox(element.get("bbox"), f"{element_id} bbox", allow_line=True)
    processing_type = _required_string(
        element.get("category"), f"{element_id} category"
    )
    element_type = normalize_codex_element_type(
        element.get("element_type") or element.get("type"),
        processing_type=processing_type,
        visual_role=str(element.get("visual_role") or ""),
    )
    reason = _required_string(
        element.get("change_reason") or element.get("reason"),
        f"{element_id} reason",
    )
    confidence = _confidence_string(
        element.get("confidence"), f"{element_id} confidence"
    )
    geometry = element.get("geometry")
    if not isinstance(geometry, Mapping):
        geometry = {"kind": "bbox", "bbox": list(bbox_xyxy)}
    source_candidate_ids = _plan_source_candidate_ids(element, element_id)

    plan = ElementPlan(
        element_id=element_id,
        source_candidate_ids=source_candidate_ids,
        element_type=element_type,
        bbox=_xyxy_to_xywh(bbox_xyxy),
        geometry=dict(geometry),
        z_order=z_order,
        confidence=confidence,
        processing_intent=ProcessingIntent(
            object_type=element_type,
            processing_type=processing_type,
        ),
        review_status="agent_refined",
        created_by_stage="refine_elements",
        change_reason=reason,
    )
    validate_element_plan(plan)
    return plan


def _plan_source_candidate_ids(
    element: Mapping[str, Any],
    element_id: str,
) -> tuple[str, ...]:
    raw_source_ids = element.get("source_candidate_ids")
    refinement_action = str(element.get("refinement_action") or "").strip()
    if raw_source_ids is None:
        if refinement_action == "added":
            return ()
        return (element_id,)
    source_ids = _normalize_id_sequence(
        raw_source_ids,
        f"{element_id} source_candidate_ids",
        allow_empty=True,
    )
    if refinement_action == "added" and source_ids:
        raise ValueError(
            f"{element_id} added element must not include source_candidate_ids"
        )
    return source_ids


def normalize_codex_element_type(
    raw_type: Any,
    *,
    processing_type: str = "",
    visual_role: str = "",
) -> str:
    normalized = (
        str(raw_type or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .strip("_")
    )
    if normalized == "added_asset":
        return _infer_added_asset_element_type(
            processing_type=processing_type,
            visual_role=visual_role,
        )
    if not normalized:
        return "unknown"
    normalized = ELEMENT_TYPE_ALIASES.get(normalized, normalized)
    if normalized in CORE_ELEMENT_TYPES:
        return normalized
    return "unknown"


def _infer_added_asset_element_type(*, processing_type: str, visual_role: str) -> str:
    role = visual_role.strip().lower().replace("-", " ").replace("_", " ")
    if processing_type in {"crop", "crop_nobg"}:
        return "picture"
    if any(
        token in role
        for token in ("text", "title", "subtitle", "caption", "label", "word")
    ):
        return "text"
    if "arrow" in role:
        return "arrow"
    if any(token in role for token in ("table", "spreadsheet")):
        return "table"
    if any(token in role for token in ("chart", "plot", "graph")):
        return "chart"
    if any(token in role for token in ("grid", "matrix")):
        return "grid"
    if any(token in role for token in ("frame", "border", "panel", "card", "box")):
        return "content_box"
    if any(token in role for token in ("icon", "symbol", "accent", "badge", "marker")):
        return "icon"
    return "unknown"


def _validate_plan(plan: ElementPlan) -> None:
    try:
        validate_element_plan(plan)
    except ValueError as exc:
        raise RefinementValidationError(str(exc)) from exc


def _validate_locked_geometry(
    plan: ElementPlan,
    locked_geometry_by_candidate: Mapping[str, Mapping[str, Any]],
) -> None:
    plan_xyxy = _xywh_to_xyxy(plan.bbox)
    for source_id in plan.source_candidate_ids:
        locked_geometry = locked_geometry_by_candidate.get(str(source_id))
        if (
            not locked_geometry
            or str(locked_geometry.get("kind") or "").lower() != "mask"
        ):
            continue
        source_bbox = _xyxy_bbox(
            locked_geometry.get("bbox"),
            f"locked geometry for {source_id}",
        )
        if not _bbox_close(plan_xyxy, source_bbox):
            raise RefinementValidationError(
                f"{plan.element_id} changed locked geometry for source candidate {source_id}"
            )
        if (
            not isinstance(plan.geometry, Mapping)
            or str(plan.geometry.get("kind") or "").lower() != "mask"
        ):
            raise RefinementValidationError(
                f"{plan.element_id} changed locked geometry for source candidate {source_id}"
            )
        if (
            isinstance(plan.geometry, Mapping)
            and str(plan.geometry.get("kind") or "").lower() == "mask"
        ):
            plan_geometry_bbox = _xyxy_bbox(
                plan.geometry.get("bbox"),
                f"{plan.element_id} geometry bbox",
            )
            if not _bbox_close(plan_geometry_bbox, source_bbox):
                raise RefinementValidationError(
                    f"{plan.element_id} changed locked geometry for source candidate {source_id}"
                )
            _validate_mask_geometry_fields(plan, source_id, locked_geometry)


def _validate_mask_geometry_fields(
    plan: ElementPlan,
    source_id: str,
    locked_geometry: Mapping[str, Any],
) -> None:
    if not isinstance(plan.geometry, Mapping):
        return
    for key, expected_value in locked_geometry.items():
        if key in {"bbox", "preview_path"}:
            continue
        if _jsonish(plan.geometry.get(key)) != _jsonish(expected_value):
            raise RefinementValidationError(
                f"{plan.element_id} changed locked geometry for source candidate {source_id}"
            )


def _removal_source_ids(record: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(_normalized_removal_record(record)["source_candidate_ids"])


def _normalized_removal_record(
    record: Mapping[str, Any],
    *,
    trust_removal_container: bool = False,
) -> dict[str, Any]:
    if not trust_removal_container and not _is_removal_record(record):
        raise RefinementValidationError(
            "mapping refinement records must be removal records with action removed/merged"
        )
    action = str(record.get("refinement_action") or record.get("action") or "").strip()
    if action not in REMOVAL_ACTIONS:
        raise RefinementValidationError(
            "removal records must use action/refinement_action removed or merged"
        )
    reason = str(record.get("removal_reason") or record.get("reason") or "").strip()
    if not reason:
        raise RefinementValidationError("removal records must include a reason")
    raw_source_ids = record.get(
        "removed_source_candidate_ids",
        record.get("source_candidate_ids"),
    )
    source_ids = _normalize_id_sequence(raw_source_ids, "removed_source_candidate_ids")
    if not source_ids:
        raise RefinementValidationError(
            "removal records must include source candidate ids"
        )
    return {
        "action": action,
        "source_candidate_ids": source_ids,
        "reason": reason,
    }


def _is_removal_record(record: Mapping[str, Any]) -> bool:
    action = str(record.get("refinement_action") or record.get("action") or "").strip()
    if action == "removed":
        return True
    if action != "merged":
        return False
    if "removed_source_candidate_ids" in record:
        return True
    return not _has_retained_element_payload(record)


def _has_retained_element_payload(record: Mapping[str, Any]) -> bool:
    return any(
        record.get(key) not in (None, "", [])
        for key in ("category", "bbox", "element_type", "type", "geometry")
    )


def _normalize_id_set(raw_ids: object, field_name: str) -> set[str]:
    return set(_normalize_id_sequence(raw_ids, field_name, allow_empty=True))


def _normalize_id_sequence(
    raw_ids: object,
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if (
        isinstance(raw_ids, str)
        or isinstance(raw_ids, Mapping)
        or not isinstance(raw_ids, Iterable)
    ):
        raise ValueError(f"{field_name} must be a non-string sequence")
    values = tuple(raw_ids)
    if not values and not allow_empty:
        raise ValueError(f"{field_name} must contain non-empty strings")
    for item in values:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} must contain non-empty strings")
    return values


def _normalize_locked_geometry(
    locked_geometry_by_candidate: Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(locked_geometry_by_candidate, Mapping):
        raise ValueError("locked_geometry_by_candidate must be a mapping")
    locked: dict[str, Mapping[str, Any]] = {}
    for candidate_id, geometry in locked_geometry_by_candidate.items():
        if not isinstance(geometry, Mapping):
            raise ValueError(f"locked geometry for {candidate_id} must be a mapping")
        locked[str(candidate_id)] = geometry
    return locked


def _xyxy_bbox(
    raw_bbox: object,
    field_name: str,
    *,
    allow_line: bool = False,
) -> tuple[float, float, float, float]:
    if (
        not isinstance(raw_bbox, Sequence)
        or isinstance(raw_bbox, str)
        or len(raw_bbox) != 4
    ):
        raise ValueError(f"{field_name} must contain exactly four numbers")
    values = tuple(_finite_number(value, field_name) for value in raw_bbox)
    x1, y1, x2, y2 = values
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
        raise ValueError(f"{field_name} must have positive area")
    return (left, top, right, bottom)


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name} must contain only numbers")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must contain only finite numbers")
    return number


def _xyxy_to_xywh(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    left, top, right, bottom = bbox
    return (left, top, right - left, bottom - top)


def _xywh_to_xyxy(bbox: Sequence[float]) -> tuple[float, float, float, float]:
    if len(bbox) != 4:
        raise ValueError("bbox must contain exactly four numbers")
    left, top, width, height = (float(value) for value in bbox)
    return (left, top, left + width, top + height)


def _bbox_close(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
        for a, b in zip(left, right, strict=True)
    )


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _optional_string(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _confidence_string(value: object, field_name: str) -> str:
    if value is None:
        return "medium"
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not value.strip():
        return "medium"
    return value.strip()


def _jsonish(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonish(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_jsonish(item) for item in value]
    return value
