from __future__ import annotations

import math
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence, get_args

from .registry import DrawAiRegistry, default_registry

ELEMENT_CANDIDATE_SCHEMA = "drawai.element_candidate.v1"
ELEMENT_PLAN_SCHEMA = "drawai.element_plan.v1"
ASSET_PACKAGE_SCHEMA = "drawai.asset_package.v1"
RUN_PACKAGE_SCHEMA = "drawai.run_package.v1"

AssetStatus = Literal["pending", "running", "ok", "failed", "unsupported"]
ReviewStatus = Literal["deterministic", "agent_refined", "user_edited"]
_PLAN_CONFIDENCES = ("low", "medium", "high")

BBox = tuple[float, float, float, float]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ProcessingIntent:
    object_type: str
    processing_type: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "processing_type": self.processing_type,
            "parameters": _json_normalize(self.parameters),
        }


@dataclass(frozen=True)
class ElementCandidate:
    candidate_id: str
    source_parser: str
    source_parser_version: str
    element_type: str
    bbox: BBox
    geometry: Mapping[str, Any]
    confidence: float
    z_hint: int | None
    text: str
    evidence_files: Sequence[str]
    provenance: Mapping[str, Any]
    raw_ref: Mapping[str, Any]
    schema: str = field(init=False, default=ELEMENT_CANDIDATE_SCHEMA)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "source_parser": self.source_parser,
            "source_parser_version": self.source_parser_version,
            "element_type": self.element_type,
            "bbox": _json_normalize(self.bbox),
            "geometry": _json_normalize(self.geometry),
            "confidence": self.confidence,
            "z_hint": self.z_hint,
            "text": self.text,
            "evidence_files": _json_normalize(self.evidence_files),
            "provenance": _json_normalize(self.provenance),
            "raw_ref": _json_normalize(self.raw_ref),
        }


@dataclass(frozen=True)
class ElementPlan:
    element_id: str
    source_candidate_ids: Sequence[str]
    element_type: str
    bbox: BBox
    geometry: Mapping[str, Any]
    z_order: int
    confidence: Literal["low", "medium", "high"]
    processing_intent: ProcessingIntent
    review_status: ReviewStatus
    created_by_stage: str
    change_reason: str
    schema: str = field(init=False, default=ELEMENT_PLAN_SCHEMA)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "element_id": self.element_id,
            "source_candidate_ids": _json_normalize(self.source_candidate_ids),
            "element_type": self.element_type,
            "bbox": _json_normalize(self.bbox),
            "geometry": _json_normalize(self.geometry),
            "z_order": self.z_order,
            "confidence": self.confidence,
            "processing_intent": self.processing_intent.to_dict(),
            "review_status": self.review_status,
            "created_by_stage": self.created_by_stage,
            "change_reason": self.change_reason,
        }


@dataclass(frozen=True)
class AssetPackage:
    asset_id: str
    element_id: str
    processor_type: str
    status: AssetStatus = "pending"
    files: Sequence[str] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    processor_runs: Sequence[Mapping[str, Any]] = ()
    all_results: Sequence[Mapping[str, Any]] = ()
    active_result: Mapping[str, Any] | None = None
    editable_payload: Mapping[str, Any] | None = None
    failure: str | None = None
    created_at: str = field(default_factory=utc_now)
    schema: str = field(init=False, default=ASSET_PACKAGE_SCHEMA)

    @classmethod
    def empty(
        cls,
        *,
        asset_id: str,
        element_id: str,
        processor_type: str,
    ) -> AssetPackage:
        return cls(
            asset_id=asset_id,
            element_id=element_id,
            processor_type=processor_type,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "asset_id": self.asset_id,
            "element_id": self.element_id,
            "processor_type": self.processor_type,
            "status": self.status,
            "files": _json_normalize(self.files),
            "metadata": _json_normalize(self.metadata),
            "processor_runs": _json_normalize(self.processor_runs),
            "all_results": _json_normalize(self.all_results),
            "active_result": _json_normalize(self.active_result),
            "editable_payload": _json_normalize(self.editable_payload),
            "failure": self.failure,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RunPackage:
    run_id: str
    root: Path
    source_image: str
    canvas: Mapping[str, Any]
    created_at: str = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema: str = field(init=False, default=RUN_PACKAGE_SCHEMA)

    @classmethod
    def new(
        cls,
        *,
        run_id: str,
        root: str | Path,
        source_image: str,
        canvas: Mapping[str, Any],
    ) -> RunPackage:
        return cls(
            run_id=run_id,
            root=Path(root),
            source_image=source_image,
            canvas=canvas,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "root": str(self.root),
            "source_image": self.source_image,
            "canvas": _json_normalize(self.canvas),
            "created_at": self.created_at,
            "metadata": _json_normalize(self.metadata),
        }


def _json_normalize(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return {str(key): _json_normalize(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_normalize(item) for item in value]
    return value


def validate_bbox(bbox: Sequence[float]) -> BBox:
    if len(bbox) != 4:
        raise ValueError("bbox must contain exactly four numbers")
    left, top, width, height = (float(value) for value in bbox)
    if not all(math.isfinite(value) for value in (left, top, width, height)):
        raise ValueError("bbox must contain only finite numbers")
    if width <= 0 or height <= 0:
        raise ValueError("bbox must have positive area")
    return (left, top, width, height)


def validate_element_candidate(
    candidate: ElementCandidate,
    *,
    registry: DrawAiRegistry | None = None,
) -> None:
    registry = registry or default_registry()
    if candidate.schema != ELEMENT_CANDIDATE_SCHEMA:
        raise ValueError(f"invalid element candidate schema: {candidate.schema}")
    if not candidate.candidate_id:
        raise ValueError("candidate_id is required")
    if not registry.has_element_type(candidate.element_type):
        raise ValueError(f"unregistered element_type: {candidate.element_type}")
    validate_bbox(candidate.bbox)
    if candidate.confidence < 0 or candidate.confidence > 1:
        raise ValueError("candidate confidence must be between 0 and 1")


def validate_element_plan(
    plan: ElementPlan,
    *,
    registry: DrawAiRegistry | None = None,
) -> None:
    registry = registry or default_registry()
    if plan.schema != ELEMENT_PLAN_SCHEMA:
        raise ValueError(f"invalid element plan schema: {plan.schema}")
    _require_non_empty_string(plan.element_id, "element_id")
    _require_non_empty_string(plan.created_by_stage, "created_by_stage")
    _require_non_empty_string(plan.change_reason, "change_reason")
    _require_non_empty_string(
        plan.processing_intent.object_type,
        "processing_intent.object_type",
    )
    _require_non_empty_string(
        plan.processing_intent.processing_type,
        "processing_intent.processing_type",
    )
    _validate_source_candidate_ids(
        plan.source_candidate_ids,
        allow_empty=(
            plan.review_status == "agent_refined"
            and plan.created_by_stage == "refine_elements"
        ),
    )
    _validate_literal(plan.confidence, _PLAN_CONFIDENCES, "confidence")
    _validate_literal(plan.review_status, get_args(ReviewStatus), "review_status")
    if not registry.has_element_type(plan.element_type):
        raise ValueError(f"unregistered element_type: {plan.element_type}")
    if not registry.has_processing_type(plan.processing_intent.processing_type):
        raise ValueError(
            f"unregistered processing_type: {plan.processing_intent.processing_type}"
        )
    validate_bbox(plan.bbox)


def validate_asset_package(package: AssetPackage) -> None:
    validate_asset_package_payload(package.to_dict())


def validate_asset_package_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, MappingABC):
        raise ValueError("asset package must be a mapping")
    if payload.get("schema") != ASSET_PACKAGE_SCHEMA:
        raise ValueError(f"invalid asset package schema: {payload.get('schema')}")
    _require_non_empty_string(payload.get("asset_id"), "asset_id")
    _require_non_empty_string(payload.get("element_id"), "element_id")
    _require_non_empty_string(payload.get("processor_type"), "processor_type")
    _validate_literal(payload.get("status"), get_args(AssetStatus), "status")
    _validate_string_sequence(payload.get("files", ()), "files")
    _validate_json_mapping(payload.get("metadata", {}), "metadata")
    _validate_processor_runs(payload.get("processor_runs", ()))
    _validate_results(payload.get("all_results", ()), "all_results")

    active_result = payload.get("active_result")
    if active_result is not None:
        _validate_result(active_result, "active_result")

    editable_payload = payload.get("editable_payload")
    if editable_payload is not None:
        _validate_json_mapping(editable_payload, "editable_payload")

    failure = payload.get("failure")
    if failure is not None and not isinstance(failure, str):
        raise ValueError("failure must be a string or null")

    created_at = payload.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        raise ValueError("created_at must be a string")


def validate_run_package(package: RunPackage) -> None:
    validate_run_package_payload(package.to_dict())


def validate_run_package_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, MappingABC):
        raise ValueError("run package must be a mapping")
    if payload.get("schema") != RUN_PACKAGE_SCHEMA:
        raise ValueError(f"invalid run package schema: {payload.get('schema')}")
    _require_non_empty_string(payload.get("run_id"), "run_id")
    _require_non_empty_string(payload.get("root"), "root")
    _require_non_empty_string(payload.get("source_image"), "source_image")
    if not isinstance(payload.get("canvas"), MappingABC):
        raise ValueError("canvas must be a mapping")


def _validate_processor_runs(value: object) -> None:
    runs = _validate_mapping_sequence(value, "processor_runs")
    for index, run in enumerate(runs):
        field_prefix = f"processor_runs[{index}]"
        for field_name in ("processor_type", "status", "started_at", "ended_at"):
            _require_non_empty_string(run.get(field_name), f"{field_prefix}.{field_name}")
        _validate_literal(run.get("status"), get_args(AssetStatus), f"{field_prefix}.status")
        _validate_json_mapping(run.get("input_refs"), f"{field_prefix}.input_refs")
        _validate_json_mapping(run.get("output_refs"), f"{field_prefix}.output_refs")
        _validate_json_mapping(run.get("metadata"), f"{field_prefix}.metadata")


def _validate_results(value: object, field_name: str) -> None:
    results = _validate_mapping_sequence(value, field_name)
    for index, result in enumerate(results):
        _validate_result(result, f"{field_name}[{index}]")


def _validate_result(value: object, field_name: str) -> None:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{field_name} must be a mapping")
    for required in ("result_id", "processor_type", "status", "kind"):
        _require_non_empty_string(value.get(required), f"{field_name}.{required}")
    _validate_literal(value.get("status"), get_args(AssetStatus), f"{field_name}.status")
    path = value.get("path")
    if path is not None and (not isinstance(path, str) or not path):
        raise ValueError(f"{field_name}.path must be a non-empty string or null")
    files = value.get("files", ())
    if isinstance(files, str) or not isinstance(files, SequenceABC):
        raise ValueError(f"{field_name}.files must be a sequence")
    for index, file_ref in enumerate(files):
        item_name = f"{field_name}.files[{index}]"
        if isinstance(file_ref, str):
            if not file_ref:
                raise ValueError(f"{item_name} must be non-empty")
            continue
        if not isinstance(file_ref, MappingABC):
            raise ValueError(f"{item_name} must be a mapping or string")
        file_path = file_ref.get("path")
        if not isinstance(file_path, str) or not file_path:
            raise ValueError(f"{item_name}.path must be a non-empty string")
        _validate_json_value(file_ref, item_name)
    _validate_json_mapping(value.get("metadata", {}), f"{field_name}.metadata")
    _validate_json_value(value, field_name)


def _validate_string_sequence(value: object, field_name: str) -> None:
    if isinstance(value, str) or not isinstance(value, SequenceABC):
        raise ValueError(f"{field_name} must be a sequence")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")


def _validate_mapping_sequence(value: object, field_name: str) -> list[MappingABC[str, Any]]:
    if isinstance(value, str) or not isinstance(value, SequenceABC):
        raise ValueError(f"{field_name} must be a sequence")
    mappings: list[MappingABC[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, MappingABC):
            raise ValueError(f"{field_name}[{index}] must be a mapping")
        mappings.append(item)
    return mappings


def _validate_json_mapping(value: object, field_name: str) -> None:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{field_name} must be a mapping")
    _validate_json_value(value, field_name)


def _validate_json_value(value: object, field_name: str) -> None:
    if value is None or isinstance(value, str | bool):
        return
    if isinstance(value, int | float) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError(f"{field_name} must be JSON-compatible")
        return
    if isinstance(value, MappingABC):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} keys must be strings")
            _validate_json_value(item, f"{field_name}.{key}")
        return
    if isinstance(value, SequenceABC) and not isinstance(value, str | bytes | bytearray):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{field_name}[{index}]")
        return
    raise ValueError(f"{field_name} must be JSON-compatible")


def _validate_source_candidate_ids(value: object, *, allow_empty: bool = False) -> None:
    if isinstance(value, str) or not isinstance(value, SequenceABC):
        raise ValueError("source_candidate_ids must be a non-string sequence")
    if not value:
        if allow_empty:
            return
        raise ValueError("source_candidate_ids must be a non-string sequence")
    for candidate_id in value:
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError("source_candidate_ids must contain non-empty strings")


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")


def _validate_literal(value: str, allowed: tuple[str, ...], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"invalid {field_name}: {value}")
