from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from drawai.artifacts import prepare_artifact_paths, write_json
from drawai.asset_geometry import geometry_crop, normalize_asset_geometry
from drawai.asset_materialization import _cleanup_cutout_border_background, materialize_run0_refined_assets
from PIL import Image

from .models import SOURCE_STRATEGIES, SourceStrategy, utc_now

WORKBENCH_ASSET_PLAN_SCHEMA = "drawai.workbench_asset_plan.v1"
COMPAT_ELEMENT_ANALYSIS_SCHEMA = "drawai.codex_element_analysis.v1"
WORKBENCH_PROCESSABLE_STRATEGIES = {"crop", "crop_nobg"}

STRATEGY_ALIASES = {
    "native_svg": "svg_self_draw",
    "svg": "svg_self_draw",
    "svg_direct": "svg_self_draw",
    "self_draw": "svg_self_draw",
    "crop_asset": "crop",
    "direct_crop": "crop",
    "preserve_crop": "crop",
    "crop_no_bg": "crop_nobg",
    "crop_without_background": "crop_nobg",
    "without_background": "crop_nobg",
    "transparent_subject": "crop_nobg",
    "remove_background": "crop_nobg",
    "rmbg": "crop_nobg",
}


def workbench_dir(case_dir: str | Path) -> Path:
    path = Path(case_dir).expanduser().resolve() / "reports" / "workbench"
    path.mkdir(parents=True, exist_ok=True)
    return path


def draft_from_run0_analysis(case_dir: str | Path, *, case_id: str = "") -> dict[str, Any]:
    root = Path(case_dir).expanduser().resolve()
    analysis = _read_json(root / "reports" / "element_analysis_codex" / "element_analysis.json")
    elements = analysis.get("elements")
    if not isinstance(elements, list):
        raise ValueError("run0 element_analysis.json must contain an elements list")
    draft_elements = [_draft_element(element, index) for index, element in enumerate(elements, start=1)]
    return {
        "schema": WORKBENCH_ASSET_PLAN_SCHEMA,
        "case_id": case_id,
        "case_dir": str(root),
        "source": "run0",
        "created_at": utc_now(),
        "elements": draft_elements,
        "categories": dict(Counter(item["source_strategy"] for item in draft_elements)),
    }


def write_asset_draft(case_dir: str | Path, plan: Mapping[str, Any]) -> Path:
    validated = validate_asset_plan(plan)
    path = workbench_dir(case_dir) / "asset_draft.json"
    write_json(path, validated)
    _append_history(case_dir, {"event": "save_draft", "at": utc_now(), "element_count": len(validated["elements"])})
    return path


def read_asset_draft(case_dir: str | Path) -> dict[str, Any]:
    return _read_json(workbench_dir(case_dir) / "asset_draft.json")


def approve_asset_plan(case_dir: str | Path, plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    root = Path(case_dir).expanduser().resolve()
    source_plan = dict(plan or read_asset_draft(root))
    source_plan["source"] = "user_edit" if plan is not None else str(source_plan.get("source") or "run0")
    approved = validate_asset_plan(source_plan)
    approved["approved_at"] = utc_now()
    approved_path = workbench_dir(root) / "approved_asset_plan.json"
    write_json(approved_path, approved)
    write_json(root / "reports" / "element_analysis_codex" / "element_analysis.json", to_compatible_element_analysis(approved, case_dir=root))
    _append_history(root, {"event": "approve_assets", "at": approved["approved_at"], "element_count": len(approved["elements"])})
    return approved


def materialize_approved_assets(case_dir: str | Path, *, rmbg_config: Any = None, rmbg_client: Any = None) -> dict[str, Any]:
    root = Path(case_dir).expanduser().resolve()
    approved = _read_json(workbench_dir(root) / "approved_asset_plan.json")
    compatible = to_compatible_element_analysis(approved, case_dir=root)
    paths = prepare_artifact_paths(root)
    return materialize_run0_refined_assets(
        paths.figure_image,
        compatible,
        paths.assets_dir,
        rmbg_config=rmbg_config,
        rmbg_client=rmbg_client,
    )


def process_asset_plan_elements(
    case_dir: str | Path,
    plan: Mapping[str, Any],
    asset_ids: Sequence[str],
    *,
    figure_image_path: str | Path | None = None,
    rmbg_client: Any = None,
    rmbg_timeout_s: float = 600,
    rmbg_model_path: str = "",
) -> dict[str, Any]:
    root = Path(case_dir).expanduser().resolve()
    validated = validate_asset_plan(plan)
    requested_ids = [str(item) for item in asset_ids if str(item)]
    if not requested_ids:
        raise ValueError("asset_ids must contain at least one asset id")
    elements_by_id = {element["box_id"]: element for element in validated["elements"]}
    missing = [asset_id for asset_id in requested_ids if asset_id not in elements_by_id]
    if missing:
        raise ValueError(f"unknown asset ids: {', '.join(missing)}")

    image_path = Path(figure_image_path) if figure_image_path is not None else root / "inputs" / "figure.png"
    image_path = image_path.expanduser().resolve(strict=False)
    if not image_path.is_file():
        raise FileNotFoundError(f"figure image is missing: {image_path}")
    output_dir = workbench_dir(root) / "processed_assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    processed_assets: list[dict[str, Any]] = []

    with Image.open(image_path) as image:
        source = image.convert("RGBA")

    requested_set = set(requested_ids)
    next_elements = []
    for element in validated["elements"]:
        if element["box_id"] not in requested_set:
            next_elements.append(element)
            continue
        strategy = element["source_strategy"]
        if strategy not in WORKBENCH_PROCESSABLE_STRATEGIES:
            raise ValueError(f"{element['box_id']} cannot be processed with strategy {strategy!r}")
        bbox = _clamped_int_bbox(element["bbox"], source.size, element["box_id"])
        geometry = normalize_asset_geometry(element.get("geometry"), fallback_bbox=bbox, image_size=source.size)
        crop = geometry_crop(source, bbox, geometry, base_dir=root)
        safe_id = _safe_asset_filename(element["box_id"])
        suffix = "nobg" if strategy == "crop_nobg" else "crop"
        output_path = output_dir / f"{safe_id}_{suffix}.png"
        update: dict[str, Any] = {
            "processed_asset_source_strategy": strategy,
            "processed_asset_updated_at": now,
            "processing_status": "processed",
            "processing_error": "",
        }
        if strategy == "crop_nobg":
            if rmbg_client is None:
                raise RuntimeError("crop_nobg processing requires an RMBG client")
            result = rmbg_client.remove_background(
                crop,
                f"{safe_id}_nobg.png",
                timeout_s=rmbg_timeout_s,
                model_path=rmbg_model_path,
                artifact_prefix=f"drawai_workbench/{safe_id}",
            )
            processed = _cleanup_cutout_border_background(result.image.convert("RGBA"))
            update["rmbg_elapsed_ms"] = float(result.elapsed_ms)
            update["rmbg_artifacts"] = dict(result.artifacts)
        else:
            processed = crop
            update["rmbg_elapsed_ms"] = 0.0
            update["rmbg_artifacts"] = {}
        processed.save(output_path)
        relative_path = output_path.relative_to(root).as_posix()
        update.update(
            {
                "processed_asset_relative_path": relative_path,
                "processed_asset_width": processed.width,
                "processed_asset_height": processed.height,
            }
        )
        next_element = {**element, **update}
        next_elements.append(next_element)
        processed_assets.append(
            {
                "box_id": element["box_id"],
                "source_strategy": strategy,
                "relative_path": relative_path,
                "width": processed.width,
                "height": processed.height,
                "rmbg_elapsed_ms": update["rmbg_elapsed_ms"],
            }
        )

    next_plan = {
        **validated,
        "updated_at": now,
        "elements": next_elements,
        "categories": dict(Counter(item["source_strategy"] for item in next_elements)),
    }
    return {"asset_plan": next_plan, "processed_assets": processed_assets}


def validate_asset_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("schema") not in {WORKBENCH_ASSET_PLAN_SCHEMA, COMPAT_ELEMENT_ANALYSIS_SCHEMA, None}:
        raise ValueError(f"Unexpected asset plan schema: {plan.get('schema')!r}")
    raw_elements = plan.get("elements")
    if not isinstance(raw_elements, list):
        raise ValueError("asset plan must contain an elements list")
    elements: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_elements, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"element {index} must be an object")
        element_id = _element_id(raw, index)
        if element_id in seen_ids:
            raise ValueError(f"duplicate element id: {element_id}")
        seen_ids.add(element_id)
        bbox = _valid_bbox(raw.get("bbox"), element_id)
        source_strategy = _source_strategy(raw)
        source_candidate_ids = raw.get("source_candidate_ids")
        if source_candidate_ids is None:
            source_candidate_ids = [element_id] if str(raw.get("refinement_action") or "unchanged") != "added" else []
        if not isinstance(source_candidate_ids, list):
            raise ValueError(f"{element_id} source_candidate_ids must be a list")
        element = {
            "box_id": element_id,
            "source_candidate_ids": [str(item) for item in source_candidate_ids if str(item)],
            "refinement_action": str(raw.get("refinement_action") or "unchanged"),
            "bbox": bbox,
            "source_strategy": source_strategy,
            "visual_role": str(raw.get("visual_role") or raw.get("type") or ""),
            "type": str(raw.get("type") or raw.get("visual_role") or "unknown"),
            "confidence": str(raw.get("confidence") or "medium"),
            "reason": str(raw.get("reason") or ""),
            "evidence": list(raw.get("evidence") or []),
            "current_pipeline_method": str(raw.get("current_pipeline_method") or raw.get("source_strategy") or ""),
            "recommended_asset_source": _recommended_asset_source(source_strategy),
        }
        geometry = normalize_asset_geometry(raw.get("geometry"), fallback_bbox=bbox)
        if geometry is not None:
            element["geometry"] = geometry
        _copy_geometry_metadata(raw, element)
        _copy_processing_fields(raw, element)
        elements.append(element)
    return {
        "schema": WORKBENCH_ASSET_PLAN_SCHEMA,
        "case_id": str(plan.get("case_id") or ""),
        "case_dir": str(plan.get("case_dir") or ""),
        "source": str(plan.get("source") or "user_edit"),
        "updated_at": utc_now(),
        "elements": elements,
        "categories": dict(Counter(item["source_strategy"] for item in elements)),
    }


def to_compatible_element_analysis(plan: Mapping[str, Any], *, case_dir: str | Path) -> dict[str, Any]:
    validated = validate_asset_plan(plan)
    compatible_elements = []
    for element in validated["elements"]:
        source_strategy = element["source_strategy"]
        compatible = dict(element)
        compatible["category"] = source_strategy
        compatible["recommended_asset_source"] = _recommended_asset_source(source_strategy)
        compatible_elements.append(compatible)
    return {
        "schema": COMPAT_ELEMENT_ANALYSIS_SCHEMA,
        "case_dir": str(Path(case_dir).expanduser().resolve()),
        "source": "workbench_approved_asset_plan",
        "strategy_summary": "Approved DrawAI workbench asset plan.",
        "refinement_summary": "User-approved asset plan converted for DrawAI SVG reconstruction.",
        "categories": dict(Counter(item["category"] for item in compatible_elements)),
        "refinement_actions": dict(Counter(item["refinement_action"] for item in compatible_elements)),
        "elements": compatible_elements,
        "notes": [],
    }


def _draft_element(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"run0 element {index} must be an object")
    source_strategy = _source_strategy(raw)
    element_id = _element_id(raw, index)
    bbox = _valid_bbox(raw.get("bbox"), element_id)
    element = {
        "box_id": element_id,
        "source_candidate_ids": list(raw.get("source_candidate_ids") or ([element_id] if element_id else [])),
        "refinement_action": str(raw.get("refinement_action") or "unchanged"),
        "bbox": bbox,
        "source_strategy": source_strategy,
        "visual_role": str(raw.get("visual_role") or raw.get("type") or ""),
        "type": str(raw.get("type") or raw.get("visual_role") or "unknown"),
        "confidence": str(raw.get("confidence") or "medium"),
        "reason": str(raw.get("reason") or ""),
        "evidence": list(raw.get("evidence") or []),
        "current_pipeline_method": str(raw.get("current_pipeline_method") or ""),
        "recommended_asset_source": _recommended_asset_source(source_strategy),
    }
    geometry = normalize_asset_geometry(raw.get("geometry"), fallback_bbox=bbox)
    if geometry is not None:
        element["geometry"] = geometry
    _copy_geometry_metadata(raw, element)
    return element


def _source_strategy(raw: Mapping[str, Any]) -> SourceStrategy:
    for key in ("source_strategy", "category", "recommended_asset_source", "method", "current_pipeline_method"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = value.strip().lower().replace("-", "_")
        normalized = STRATEGY_ALIASES.get(normalized, normalized)
        if normalized in SOURCE_STRATEGIES:
            return normalized  # type: ignore[return-value]
    raise ValueError(f"Unknown source strategy for element {raw.get('box_id') or raw.get('id') or ''!r}")


def _element_id(raw: Mapping[str, Any], index: int) -> str:
    for key in ("box_id", "element_id", "id", "asset_id"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"E{index:03d}"


def _valid_bbox(value: Any, element_id: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{element_id} bbox must contain four numbers")
    try:
        x1, y1, x2, y2 = [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{element_id} bbox must contain finite numbers") from exc
    if not all(math.isfinite(item) for item in (x1, y1, x2, y2)):
        raise ValueError(f"{element_id} bbox must contain finite numbers")
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    if right <= left or bottom <= top:
        raise ValueError(f"{element_id} bbox must have positive area")
    return [left, top, right, bottom]


def _recommended_asset_source(source_strategy: str) -> str:
    return "svg" if source_strategy == "svg_self_draw" else source_strategy


def _copy_processing_fields(raw: Mapping[str, Any], target: dict[str, Any]) -> None:
    for key in (
        "processed_asset_relative_path",
        "processed_asset_source_strategy",
        "processed_asset_updated_at",
        "processing_status",
        "processing_error",
    ):
        value = raw.get(key)
        if isinstance(value, str) and value:
            target[key] = value
    for key in ("processed_asset_width", "processed_asset_height"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            target[key] = int(value)
    elapsed = raw.get("rmbg_elapsed_ms")
    if isinstance(elapsed, (int, float)) and math.isfinite(float(elapsed)):
        target["rmbg_elapsed_ms"] = float(elapsed)
    artifacts = raw.get("rmbg_artifacts")
    if isinstance(artifacts, Mapping):
        target["rmbg_artifacts"] = dict(artifacts)


def _copy_geometry_metadata(raw: Mapping[str, Any], target: dict[str, Any]) -> None:
    for key in ("geometry_kind", "geometry_preview_relative_path", "mask_preview"):
        value = raw.get(key)
        if isinstance(value, str) and value:
            target[key] = value
    locked = raw.get("geometry_locked")
    if isinstance(locked, bool):
        target["geometry_locked"] = locked


def _clamped_int_bbox(bbox: Sequence[float], size: tuple[int, int], element_id: str) -> tuple[int, int, int, int]:
    width, height = size
    x1, y1, x2, y2 = [float(value) for value in bbox]
    left = max(0, min(width, math.floor(min(x1, x2))))
    right = max(0, min(width, math.ceil(max(x1, x2))))
    top = max(0, min(height, math.floor(min(y1, y2))))
    bottom = max(0, min(height, math.ceil(max(y1, y2))))
    if right <= left or bottom <= top:
        raise ValueError(f"{element_id} bbox is outside the figure image")
    return left, top, right, bottom


def _safe_asset_filename(asset_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", asset_id).strip("._")
    return safe or "asset"


def _append_history(case_dir: str | Path, event: Mapping[str, Any]) -> None:
    path = workbench_dir(case_dir) / "edit_history.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(event), ensure_ascii=False, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload
