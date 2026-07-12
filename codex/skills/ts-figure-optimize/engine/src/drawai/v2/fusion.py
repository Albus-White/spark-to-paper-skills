from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .schema import (
    ElementCandidate,
    ElementPlan,
    ProcessingIntent,
    validate_element_candidate,
    validate_element_plan,
)


@dataclass(frozen=True)
class FusionConfig:
    duplicate_iou_threshold: float = 0.85

    @classmethod
    def default(cls) -> FusionConfig:
        return cls()


@dataclass(frozen=True)
class FusionResult:
    elements: tuple[ElementPlan, ...]
    trace: dict[str, Any]


def fuse_candidates(
    candidates: Sequence[ElementCandidate],
    config: FusionConfig,
) -> FusionResult:
    _validate_config(config)
    ordered_for_selection = sorted(tuple(candidates), key=_selection_key)
    for candidate in ordered_for_selection:
        validate_element_candidate(candidate)

    accepted: list[ElementCandidate] = []
    decisions: list[dict[str, Any]] = []
    for candidate in ordered_for_selection:
        suppressor: ElementCandidate | None = None
        kept_separate_decisions: list[dict[str, Any]] = []
        for existing in accepted:
            if candidate.element_type != existing.element_type:
                continue
            iou = _bbox_iou(candidate.bbox, existing.bbox)
            if iou < config.duplicate_iou_threshold:
                continue
            if _mask_bbox_conflict(candidate, existing):
                kept_separate_decisions.append(
                    _decision(
                        action="kept_separate",
                        candidate=candidate,
                        other=existing,
                        reason="locked_mask_geometry_conflict",
                        iou=iou,
                    )
                )
                continue
            suppressor = existing
            break

        if suppressor is not None:
            decisions.append(
                _decision(
                    action="suppressed",
                    candidate=candidate,
                    other=suppressor,
                    reason="duplicate_same_type",
                    iou=_bbox_iou(candidate.bbox, suppressor.bbox),
                )
            )
            continue

        if kept_separate_decisions:
            decisions.extend(kept_separate_decisions)
        else:
            decisions.append(
                _decision(
                    action="kept",
                    candidate=candidate,
                    other=None,
                    reason="no_duplicate_conflict",
                    iou=None,
                )
            )
        accepted.append(candidate)

    output_candidates = sorted(accepted, key=_output_key)
    elements = tuple(
        _candidate_to_plan(candidate, element_index=index)
        for index, candidate in enumerate(output_candidates, start=1)
    )
    return FusionResult(
        elements=elements,
        trace={
            "stage": "fuse_elements",
            "config": {"duplicate_iou_threshold": config.duplicate_iou_threshold},
            "decisions": decisions,
        },
    )


def _validate_config(config: FusionConfig) -> None:
    if not isinstance(config, FusionConfig):
        raise ValueError("config must be a FusionConfig")
    threshold = config.duplicate_iou_threshold
    if not isinstance(threshold, int | float) or isinstance(threshold, bool):
        raise ValueError("duplicate_iou_threshold must be a number")
    if not math.isfinite(float(threshold)) or threshold < 0 or threshold > 1:
        raise ValueError("duplicate_iou_threshold must be between 0 and 1")


def _selection_key(
    candidate: ElementCandidate,
) -> tuple[float, float, int, float, float, str, str]:
    left, top, _, _ = candidate.bbox
    return (
        -float(_parser_priority(candidate)),
        -float(candidate.confidence),
        _z_hint(candidate),
        top,
        left,
        candidate.candidate_id,
        candidate.source_parser,
    )


def _output_key(candidate: ElementCandidate) -> tuple[int, float, float, str, str]:
    left, top, _, _ = candidate.bbox
    return (
        _z_hint(candidate),
        top,
        left,
        candidate.candidate_id,
        candidate.source_parser,
    )


def _parser_priority(candidate: ElementCandidate) -> int:
    provenance = candidate.provenance
    if not isinstance(provenance, Mapping) or "parser_priority" not in provenance:
        return 0
    value = provenance["parser_priority"]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{candidate.candidate_id} parser_priority must be numeric")
    if not math.isfinite(float(value)) or not float(value).is_integer():
        raise ValueError(f"{candidate.candidate_id} parser_priority must be an integer")
    return int(value)


def _z_hint(candidate: ElementCandidate) -> int:
    return 0 if candidate.z_hint is None else int(candidate.z_hint)


def _bbox_iou(
    left_bbox: tuple[float, float, float, float],
    right_bbox: tuple[float, float, float, float],
) -> float:
    left_x, left_y, left_width, left_height = left_bbox
    right_x, right_y, right_width, right_height = right_bbox
    intersection_left = max(left_x, right_x)
    intersection_top = max(left_y, right_y)
    intersection_right = min(left_x + left_width, right_x + right_width)
    intersection_bottom = min(left_y + left_height, right_y + right_height)
    intersection_width = max(0.0, intersection_right - intersection_left)
    intersection_height = max(0.0, intersection_bottom - intersection_top)
    intersection_area = intersection_width * intersection_height
    if intersection_area == 0:
        return 0.0
    left_area = left_width * left_height
    right_area = right_width * right_height
    return intersection_area / (left_area + right_area - intersection_area)


def _mask_bbox_conflict(left: ElementCandidate, right: ElementCandidate) -> bool:
    return _is_mask_geometry(left.geometry) != _is_mask_geometry(right.geometry)


def _is_mask_geometry(geometry: Mapping[str, Any]) -> bool:
    return str(geometry.get("kind") or "").strip().lower() == "mask"


def _decision(
    *,
    action: str,
    candidate: ElementCandidate,
    other: ElementCandidate | None,
    reason: str,
    iou: float | None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "action": action,
        "reason": reason,
        "candidate_id": candidate.candidate_id,
        "candidate_source_parser": candidate.source_parser,
        "element_type": candidate.element_type,
        "parser_priority": _parser_priority(candidate),
        "confidence": candidate.confidence,
    }
    if iou is not None:
        item["iou"] = round(iou, 6)
    if other is not None:
        item["other_candidate_id"] = other.candidate_id
        item["other_source_parser"] = other.source_parser
        item["other_parser_priority"] = _parser_priority(other)
        item["other_confidence"] = other.confidence
    return item


def _candidate_to_plan(candidate: ElementCandidate, *, element_index: int) -> ElementPlan:
    plan = ElementPlan(
        element_id=f"E{element_index:03d}",
        source_candidate_ids=(candidate.candidate_id,),
        element_type=candidate.element_type,
        bbox=candidate.bbox,
        geometry=candidate.geometry,
        z_order=element_index - 1,
        confidence=_plan_confidence(candidate.confidence),
        processing_intent=_processing_intent(candidate.element_type),
        review_status="deterministic",
        created_by_stage="fuse_elements",
        change_reason="Selected deterministic parser candidate.",
    )
    validate_element_plan(plan)
    return plan


def _plan_confidence(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _processing_intent(element_type: str) -> ProcessingIntent:
    if element_type in {"icon", "symbol", "arrow"}:
        processing_type = "crop_nobg"
    elif element_type in {"picture", "image"}:
        processing_type = "crop"
    else:
        processing_type = "no_process"
    return ProcessingIntent(object_type=element_type, processing_type=processing_type)
