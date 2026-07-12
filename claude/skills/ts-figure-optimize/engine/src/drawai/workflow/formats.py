from __future__ import annotations

import json
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree
from PIL import Image

from drawai.page_spec import validate_page_spec_payload
from drawai.v2.schema import (
    ElementCandidate,
    ElementPlan,
    ProcessingIntent,
    validate_asset_package_payload,
    validate_element_candidate,
    validate_element_plan,
)
from drawai.v2.refine import (
    codex_analysis_to_v2_element_plans,
    codex_analysis_to_v2_removal_records,
)


FormatValidator = Callable[[Path], tuple[str, ...]]


@dataclass(frozen=True)
class FormatSpec:
    format_id: str
    label: str
    media_type: str
    artifact_type: str
    validator: FormatValidator
    description: str = ""


@dataclass(frozen=True)
class FormatValidationResult:
    format_id: str
    path: str
    ok: bool
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_id": self.format_id,
            "path": self.path,
            "ok": self.ok,
            "errors": list(self.errors),
        }


def default_format_registry() -> dict[str, FormatSpec]:
    return {
        "drawai.image.v1": FormatSpec(
            format_id="drawai.image.v1",
            label="Image",
            media_type="image/*",
            artifact_type="image",
            validator=_validate_image,
            description=(
                "Openable raster image file, usually PNG/JPEG/WebP. Agent nodes should treat image inputs as visual "
                "evidence and only rewrite an image when an image output is explicitly declared."
            ),
        ),
        "drawai.element_candidates.v1": FormatSpec(
            format_id="drawai.element_candidates.v1",
            label="Element Candidates",
            media_type="application/json",
            artifact_type="element_candidates",
            validator=_validate_element_candidates,
            description=(
                "UTF-8 JSON object with a candidates array, or a JSON array of element candidate objects. Each "
                "candidate should include candidate_id, source_parser, element_type, bbox [x,y,width,height], "
                "geometry, confidence, optional text, evidence_files, provenance, and raw_ref."
            ),
        ),
        "drawai.element_plans.v1": FormatSpec(
            format_id="drawai.element_plans.v1",
            label="Element Plans",
            media_type="application/json",
            artifact_type="element_plans",
            validator=_validate_element_plans,
            description=(
                "UTF-8 JSON object with an elements array, or a JSON array of element plan objects. Each element "
                "contains element_id, source_candidate_ids, element_type, bbox [x,y,width,height], geometry, z_order, "
                "confidence, processing_intent, review_status, created_by_stage, and change_reason."
            ),
        ),
        "drawai.page_spec.v1": FormatSpec(
            format_id="drawai.page_spec.v1",
            label="Page Spec",
            media_type="application/json",
            artifact_type="page_spec",
            validator=_validate_page_spec,
            description=(
                "UTF-8 JSON object with schema drawai.page_spec.v1. It is the canonical page model used by "
                "PageSpec-first DAGs: source, canvas, optional background, and elements. Elements use stable id, "
                "kind text|shape|image|diagram|connector|table|chart|formula|group|unknown, source-pixel geometry "
                "box_px/points_px/polygon_px, z_index, role, build instructions, style, measurement, source_refs, "
                "metadata, and optional materialization outputs. Materialization paths are relative to the "
                "PageSpec JSON bundle directory."
            ),
        ),
        "drawai.codex_element_analysis.v1": FormatSpec(
            format_id="drawai.codex_element_analysis.v1",
            label="Element Analysis",
            media_type="application/json",
            artifact_type="element_analysis",
            validator=_validate_element_analysis,
            description=(
                "UTF-8 JSON object with schema drawai.codex_element_analysis.v1 and an elements array. Retained "
                "elements use box_id or element_id, source_candidate_ids, bbox as [x1,y1,x2,y2], category "
                "svg_self_draw|crop|crop_nobg, type, confidence, reason, evidence, current_pipeline_method, and "
                "recommended_asset_source. Top-level removal_records cover removed/merged source candidates and "
                "must include action or refinement_action removed|merged, source_candidate_ids or "
                "removed_source_candidate_ids, and reason or removal_reason."
            ),
        ),
        "drawai.asset_package.v1": FormatSpec(
            format_id="drawai.asset_package.v1",
            label="Asset Package",
            media_type="application/json",
            artifact_type="asset_package",
            validator=_validate_asset_package,
            description=(
                "UTF-8 JSON object for one DrawAI asset package. It includes asset_id, element_id, processor_type, "
                "status, files, metadata, processor_runs, active_result, editable_payload, and optional failure."
            ),
        ),
        "drawai.asset_packages.v1": FormatSpec(
            format_id="drawai.asset_packages.v1",
            label="Asset Packages",
            media_type="application/json",
            artifact_type="asset_packages",
            validator=_validate_asset_packages,
            description=(
                "UTF-8 JSON object with an asset_packages array, or a JSON array of asset package objects. It is the "
                "collection consumed by SVG generation for local crop/no-background assets."
            ),
        ),
        "drawai.semantic_svg.v1": FormatSpec(
            format_id="drawai.semantic_svg.v1",
            label="Semantic SVG",
            media_type="image/svg+xml",
            artifact_type="semantic_svg",
            validator=_validate_semantic_svg,
            description="SVG XML file whose document root is <svg>; intended to follow the DrawAI editable SVG/PPT profile.",
        ),
        "drawai.pptx.v1": FormatSpec(
            format_id="drawai.pptx.v1",
            label="PPTX",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            artifact_type="pptx",
            validator=_validate_pptx,
            description="Valid zipped PowerPoint Open XML package containing [Content_Types].xml and ppt/presentation.xml.",
        ),
        "drawai.final_outputs.v1": FormatSpec(
            format_id="drawai.final_outputs.v1",
            label="Final Outputs",
            media_type="application/json",
            artifact_type="final_outputs",
            validator=_validate_final_outputs,
            description="UTF-8 JSON object with an outputs array generated by an output node.",
        ),
    }


def element_plans_from_payload(payload: Any) -> tuple[ElementPlan, ...]:
    if isinstance(payload, Mapping) and payload.get("schema") == "drawai.codex_element_analysis.v1":
        return codex_analysis_to_v2_element_plans(payload)
    raw_plans = _raw_element_plans(payload)
    plans: list[ElementPlan] = []
    for index, raw_plan in enumerate(raw_plans):
        if not isinstance(raw_plan, Mapping):
            raise ValueError(f"elements[{index}] must be a mapping")
        plan = _element_plan_from_payload(raw_plan)
        validate_element_plan(plan)
        plans.append(plan)
    return tuple(plans)


def default_format_contract_descriptions(
    *,
    registry: Mapping[str, FormatSpec] | None = None,
) -> dict[str, str]:
    return {
        format_id: spec.description
        for format_id, spec in (registry or default_format_registry()).items()
    }


def validate_format_file(
    format_id: str,
    path: str | Path,
    *,
    registry: Mapping[str, FormatSpec] | None = None,
) -> FormatValidationResult:
    path_obj = Path(path).expanduser().resolve(strict=False)
    format_registry = registry or default_format_registry()
    spec = format_registry.get(format_id)
    if spec is None:
        return FormatValidationResult(
            format_id=format_id,
            path=str(path_obj),
            ok=False,
            errors=(f"unknown workflow format: {format_id}",),
        )
    if not path_obj.is_file():
        return FormatValidationResult(
            format_id=format_id,
            path=str(path_obj),
            ok=False,
            errors=(f"format file does not exist: {path_obj}",),
        )
    errors = spec.validator(path_obj)
    return FormatValidationResult(
        format_id=format_id,
        path=str(path_obj),
        ok=not errors,
        errors=errors,
    )


def _validate_image(path: Path) -> tuple[str, ...]:
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        return (f"image is not openable: {type(exc).__name__}: {exc}",)
    return ()


def _validate_element_candidates(path: Path) -> tuple[str, ...]:
    payload, errors = _read_json_object_or_list(path)
    if errors:
        return errors
    raw_candidates = (
        payload.get("candidates") if isinstance(payload, Mapping) else payload
    )
    if isinstance(raw_candidates, str) or not isinstance(raw_candidates, Sequence):
        return ("element candidates payload must contain a candidates list",)
    validation_errors: list[str] = []
    for index, raw_candidate in enumerate(raw_candidates):
        if not isinstance(raw_candidate, Mapping):
            validation_errors.append(f"candidates[{index}] must be a mapping")
            continue
        try:
            validate_element_candidate(_candidate_from_payload(raw_candidate))
        except Exception as exc:
            validation_errors.append(f"candidates[{index}]: {exc}")
    return tuple(validation_errors)


def _validate_element_plans(path: Path) -> tuple[str, ...]:
    payload, errors = _read_json_object_or_list(path)
    if errors:
        return errors
    try:
        raw_plans = _raw_element_plans(payload)
    except ValueError as exc:
        return (str(exc),)
    validation_errors: list[str] = []
    for index, raw_plan in enumerate(raw_plans):
        if not isinstance(raw_plan, Mapping):
            validation_errors.append(f"elements[{index}] must be a mapping")
            continue
        try:
            validate_element_plan(_element_plan_from_payload(raw_plan))
        except Exception as exc:
            validation_errors.append(f"elements[{index}]: {exc}")
    return tuple(validation_errors)


def _raw_element_plans(payload: Any) -> Sequence[Any]:
    raw_plans = payload.get("elements") if isinstance(payload, Mapping) else payload
    if isinstance(raw_plans, str) or not isinstance(raw_plans, Sequence):
        raise ValueError("element plans payload must contain an elements list")
    return raw_plans


def _validate_element_analysis(path: Path) -> tuple[str, ...]:
    payload, errors = _read_json_object(path)
    if errors:
        return errors
    try:
        codex_analysis_to_v2_element_plans(payload)
        codex_analysis_to_v2_removal_records(payload)
    except Exception as exc:
        return (str(exc),)
    return ()


def _validate_page_spec(path: Path) -> tuple[str, ...]:
    payload, errors = _read_json_object(path)
    if errors:
        return errors
    try:
        validate_page_spec_payload(payload)
        from drawai.page_spec_assets import validate_page_spec_bundle_payload

        validate_page_spec_bundle_payload(payload, path.parent)
    except Exception as exc:
        return (str(exc),)
    return ()


def _validate_asset_package(path: Path) -> tuple[str, ...]:
    payload, errors = _read_json_object(path)
    if errors:
        return errors
    try:
        validate_asset_package_payload(payload)
    except Exception as exc:
        return (str(exc),)
    return ()


def _validate_asset_packages(path: Path) -> tuple[str, ...]:
    payload, errors = _read_json_object_or_list(path)
    if errors:
        return errors
    raw_packages = (
        payload.get("asset_packages") if isinstance(payload, Mapping) else payload
    )
    if isinstance(raw_packages, str) or not isinstance(raw_packages, Sequence):
        return ("asset packages payload must contain an asset_packages list",)
    validation_errors: list[str] = []
    for index, raw_package in enumerate(raw_packages):
        if not isinstance(raw_package, Mapping):
            validation_errors.append(f"asset_packages[{index}] must be a mapping")
            continue
        try:
            validate_asset_package_payload(raw_package)
        except Exception as exc:
            validation_errors.append(f"asset_packages[{index}]: {exc}")
    return tuple(validation_errors)


def _validate_semantic_svg(path: Path) -> tuple[str, ...]:
    try:
        root = etree.parse(str(path)).getroot()
    except Exception as exc:
        return (f"SVG XML is not parseable: {type(exc).__name__}: {exc}",)
    if etree.QName(root).localname != "svg":
        return (f"semantic SVG root must be svg, got {etree.QName(root).localname}",)
    return ()


def _validate_pptx(path: Path) -> tuple[str, ...]:
    if not zipfile.is_zipfile(path):
        return ("PPTX is not a zip package",)
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    missing = [
        name
        for name in ("[Content_Types].xml", "ppt/presentation.xml")
        if name not in names
    ]
    if missing:
        return (
            f"PPTX package missing required presentation files: {', '.join(missing)}",
        )
    return ()


def _validate_final_outputs(path: Path) -> tuple[str, ...]:
    payload, errors = _read_json_object(path)
    if errors:
        return errors
    outputs = payload.get("outputs")
    if isinstance(outputs, str) or not isinstance(outputs, Sequence):
        return ("final outputs payload must contain an outputs list",)
    validation_errors: list[str] = []
    for index, output in enumerate(outputs):
        if not isinstance(output, Mapping):
            validation_errors.append(f"outputs[{index}] must be a mapping")
            continue
        for field_name in ("path", "format_id"):
            if not isinstance(output.get(field_name), str) or not output.get(
                field_name
            ):
                validation_errors.append(f"outputs[{index}].{field_name} is required")
    return tuple(validation_errors)


def _read_json_object(path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    payload, errors = _read_json(path)
    if errors:
        return {}, errors
    if not isinstance(payload, dict):
        return {}, ("JSON payload must be an object",)
    return payload, ()


def _read_json_object_or_list(path: Path) -> tuple[Any, tuple[str, ...]]:
    payload, errors = _read_json(path)
    if errors:
        return {}, errors
    if not isinstance(payload, dict | list):
        return {}, ("JSON payload must be an object or list",)
    return payload, ()


def _read_json(path: Path) -> tuple[Any, tuple[str, ...]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ()
    except Exception as exc:
        return None, (f"JSON is not parseable: {type(exc).__name__}: {exc}",)


def _candidate_from_payload(payload: Mapping[str, Any]) -> ElementCandidate:
    return ElementCandidate(
        candidate_id=_required_string(payload, "candidate_id"),
        source_parser=_required_string(payload, "source_parser"),
        source_parser_version=_required_string(payload, "source_parser_version"),
        element_type=_required_string(payload, "element_type"),
        bbox=_bbox4(payload.get("bbox"), "bbox"),
        geometry=_mapping(payload.get("geometry"), "geometry"),
        confidence=float(payload.get("confidence")),
        z_hint=payload.get("z_hint")
        if isinstance(payload.get("z_hint"), int)
        else None,
        text=str(payload.get("text") or ""),
        evidence_files=tuple(str(item) for item in payload.get("evidence_files", ())),
        provenance=_mapping(payload.get("provenance"), "provenance"),
        raw_ref=_mapping(payload.get("raw_ref"), "raw_ref"),
    )


def _element_plan_from_payload(payload: Mapping[str, Any]) -> ElementPlan:
    processing_intent = _mapping(payload.get("processing_intent"), "processing_intent")
    return ElementPlan(
        element_id=_required_string(payload, "element_id"),
        source_candidate_ids=tuple(
            str(item) for item in payload.get("source_candidate_ids", ())
        ),
        element_type=_required_string(payload, "element_type"),
        bbox=_bbox4(payload.get("bbox"), "bbox"),
        geometry=_mapping(payload.get("geometry"), "geometry"),
        z_order=int(payload.get("z_order")),
        confidence=str(payload.get("confidence")),  # type: ignore[arg-type]
        processing_intent=ProcessingIntent(
            object_type=_required_string(processing_intent, "object_type"),
            processing_type=_required_string(processing_intent, "processing_type"),
            parameters=_mapping(processing_intent.get("parameters", {}), "parameters"),
        ),
        review_status=str(payload.get("review_status")),  # type: ignore[arg-type]
        created_by_stage=_required_string(payload, "created_by_stage"),
        change_reason=_required_string(payload, "change_reason"),
    )


def _required_string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")
    return value


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _bbox4(value: Any, field_name: str) -> tuple[float, float, float, float]:
    if isinstance(value, str) or not isinstance(value, Sequence) or len(value) != 4:
        raise ValueError(f"{field_name} must contain four numbers")
    return tuple(float(item) for item in value)  # type: ignore[return-value]
