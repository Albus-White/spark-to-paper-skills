from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from .domain.box_ir import normalize_box_type

ASSET_DECISIONS_SCHEMA = "drawai.asset_decisions.v1"
SVG_RECOVERABLE_ASSETS_SCHEMA = "drawai.svg_recoverable_assets.v1"
ASSET_ID_RE = re.compile(r"^AF\d{2}$")
DEFAULT_DISALLOW_CROP_ROLES = frozenset({"arrow", "border", "grid", "text", "content_box"})
DEFAULT_INITIAL_CROP_ROLES = frozenset({"icon", "picture"})
DEFAULT_MAX_AREA_RATIO = 0.35
DEFAULT_MAX_ATTEMPTS = 3


class AssetSelectionError(ValueError):
    """Raised when asset selection cannot produce valid crop/native decisions."""

    def __init__(self, message: str, attempt_issues: list[list[str]] | None = None):
        super().__init__(message)
        self.attempt_issues = attempt_issues or []


def build_initial_asset_decisions(
    box_ir: Mapping[str, Any],
    *,
    initial_crop_roles: set[str] | frozenset[str] | list[str] | tuple[str, ...] = DEFAULT_INITIAL_CROP_ROLES,
) -> dict[str, Any]:
    crop_roles = {normalize_box_type(role) for role in initial_crop_roles}
    used_asset_ids: set[str] = set()
    next_asset_index = 1
    decisions: list[dict[str, Any]] = []
    iterable = box_ir.get("boxes") if isinstance(box_ir, Mapping) else []
    if not isinstance(iterable, list):
        iterable = []
    for box in iterable:
        if not isinstance(box, Mapping):
            continue
        box_id = box.get("id")
        if not isinstance(box_id, str) or not box_id.strip():
            continue
        role = normalize_box_type(box.get("type"))
        if role in crop_roles:
            asset_id, next_asset_index = _next_asset_id(used_asset_ids, next_asset_index)
            used_asset_ids.add(asset_id)
            decisions.append(
                {
                    "box_id": box_id.strip(),
                    "decision": "crop_asset",
                    "asset_id": asset_id,
                    "initial_crop_role": role,
                }
            )
        else:
            decisions.append({"box_id": box_id.strip(), "decision": "native_svg"})
    return {"schema": ASSET_DECISIONS_SCHEMA, "decisions": decisions}


def apply_svg_recoverability_to_asset_decisions(
    initial_decisions: Mapping[str, Any],
    recovery: Mapping[str, Any],
) -> dict[str, Any]:
    recoverable_asset_ids = set(_recoverable_asset_ids(recovery))
    final_decisions: list[dict[str, Any]] = []
    for decision in initial_decisions.get("decisions", []):
        if not isinstance(decision, Mapping):
            continue
        if decision.get("decision") != "crop_asset" or decision.get("asset_id") not in recoverable_asset_ids:
            final_decisions.append(dict(decision))
            continue
        recovered: dict[str, Any] = {
            "box_id": decision.get("box_id"),
            "decision": "native_svg",
            "recovered_asset_id": decision.get("asset_id"),
            "recovery_reason": str(recovery.get("source") or "asset_policy"),
        }
        final_decisions.append(recovered)
    return {"schema": ASSET_DECISIONS_SCHEMA, "decisions": final_decisions}


def validate_asset_decisions(
    box_ir: Mapping[str, Any],
    decisions: Any,
    disallow_crop_roles: set[str] | frozenset[str] | list[str] | tuple[str, ...],
    max_area_ratio: float,
) -> list[str]:
    issues: list[str] = []
    if not isinstance(box_ir, Mapping):
        return ["box_ir must be a mapping"]
    if not isinstance(decisions, Mapping):
        return ["asset decisions must be a mapping"]

    schema = decisions.get("schema")
    if schema is not None and schema != ASSET_DECISIONS_SCHEMA:
        issues.append(f"schema must be {ASSET_DECISIONS_SCHEMA!r}, got {schema!r}")

    raw_decisions = decisions.get("decisions")
    if not isinstance(raw_decisions, list):
        issues.append("decisions must be a list")
        return issues

    boxes_by_id = _boxes_by_id(box_ir.get("boxes"))
    ocr_box_ids = _box_ids(box_ir.get("ocr_text_boxes"))
    canvas_width, canvas_height = _canvas_size(box_ir.get("canvas"))
    canvas_area = canvas_width * canvas_height if canvas_width > 0 and canvas_height > 0 else 0.0
    disallowed_roles = {normalize_box_type(role) for role in disallow_crop_roles}
    seen_asset_ids: set[str] = set()

    for index, decision_record in enumerate(raw_decisions):
        field = f"decisions[{index}]"
        if not isinstance(decision_record, Mapping):
            issues.append(f"{field} must be a mapping")
            continue

        box_id = decision_record.get("box_id")
        decision = decision_record.get("decision")
        asset_id = decision_record.get("asset_id")

        if not isinstance(box_id, str) or not box_id.strip():
            issues.append(f"{field}.box_id must be a non-empty string")
            box = None
        elif box_id in ocr_box_ids:
            issues.append(f"{field}.box_id {box_id!r} is an OCR text box and cannot be a crop target")
            box = None
        elif box_id not in boxes_by_id:
            issues.append(f"Unknown box_id {box_id!r} in {field}")
            box = None
        else:
            box = boxes_by_id[box_id]

        if decision not in {"crop_asset", "native_svg"}:
            issues.append(f"{field}.decision must be 'crop_asset' or 'native_svg', got {decision!r}")

        if asset_id is None or asset_id == "":
            if decision == "crop_asset":
                issues.append(f"{field}.asset_id is required for crop_asset decisions")
        elif not isinstance(asset_id, str):
            issues.append(f"{field}.asset_id must be a string")
        elif not ASSET_ID_RE.fullmatch(asset_id):
            issues.append(f"{field}.asset_id {asset_id!r} must match AF01, AF02, etc.")
        elif asset_id in seen_asset_ids:
            issues.append(f"Duplicate asset_id {asset_id!r} in {field}")
        else:
            seen_asset_ids.add(asset_id)

        if decision != "crop_asset" or box is None:
            continue

        role = normalize_box_type(box.get("type"))
        if role in disallowed_roles:
            issues.append(f"box_id {box_id!r} has disallowed crop role {role!r}")

        bbox = _parse_bbox(box.get("bbox"))
        if bbox is None:
            issues.append(f"box_id {box_id!r} has invalid bbox")
            continue
        area = _bbox_area(bbox)
        if canvas_area <= 0:
            issues.append("box_ir.canvas width and height must be positive for area validation")
            continue

        area_ratio = area / canvas_area
        if area_ratio > max_area_ratio:
            issues.append(
                f"box_id {box_id!r} area ratio {area_ratio:.3f} exceeds max_area_ratio {max_area_ratio:.3f}"
            )
        if _is_near_whole_canvas(bbox, canvas_width, canvas_height, area_ratio):
            issues.append(f"box_id {box_id!r} is near-whole canvas and cannot be cropped as one asset")

    return issues


def normalize_and_validate_asset_decisions(
    box_ir: Mapping[str, Any],
    decisions: Any,
    asset_selection_config: Any = None,
    *,
    disallow_crop_roles: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    max_area_ratio: float | None = None,
) -> dict[str, Any]:
    settings = _asset_selection_settings(asset_selection_config)
    effective_disallow_crop_roles = (
        settings["disallow_crop_roles"] if disallow_crop_roles is None else set(disallow_crop_roles)
    )
    effective_max_area_ratio = (
        settings["max_area_ratio"] if max_area_ratio is None else float(max_area_ratio)
    )
    normalized = normalize_asset_decisions(decisions)
    issues = validate_asset_decisions(
        box_ir,
        normalized,
        disallow_crop_roles=effective_disallow_crop_roles,
        max_area_ratio=effective_max_area_ratio,
    )
    if issues:
        raise AssetSelectionError(
            "Invalid asset decisions: " + "; ".join(issues),
            attempt_issues=[issues],
        )
    return normalized


def normalize_asset_decisions(decisions: Any) -> dict[str, Any]:
    if not isinstance(decisions, Mapping):
        raise AssetSelectionError(f"asset decisions must be a mapping, got {type(decisions).__name__}")

    raw_decisions = decisions.get("decisions")
    if not isinstance(raw_decisions, list):
        raise AssetSelectionError("asset decisions response must contain a decisions list")

    normalized_decisions: list[dict[str, Any]] = []
    used_asset_ids = {
        item.get("asset_id")
        for item in raw_decisions
        if isinstance(item, Mapping)
        and isinstance(item.get("asset_id"), str)
        and ASSET_ID_RE.fullmatch(item["asset_id"])
    }
    next_asset_index = 1

    for item in raw_decisions:
        if not isinstance(item, Mapping):
            normalized_decisions.append(deepcopy(item))
            continue

        normalized: dict[str, Any] = {}
        if "box_id" in item:
            normalized["box_id"] = item["box_id"]
        if "decision" in item:
            normalized["decision"] = item["decision"]
        asset_id = item.get("asset_id")
        if isinstance(asset_id, str) and asset_id.strip():
            normalized["asset_id"] = asset_id.strip()
        elif item.get("decision") == "crop_asset":
            generated, next_asset_index = _next_asset_id(used_asset_ids, next_asset_index)
            normalized["asset_id"] = generated
            used_asset_ids.add(generated)
        for optional_key in ("complexity", "reason", "render_strategy"):
            optional_value = item.get(optional_key)
            if isinstance(optional_value, str) and optional_value.strip():
                normalized[optional_key] = optional_value.strip()
        normalized_decisions.append(normalized)

    return {
        "schema": ASSET_DECISIONS_SCHEMA,
        "decisions": normalized_decisions,
    }


def _asset_selection_settings(config: Any) -> dict[str, Any]:
    raw = _asset_selection_raw(config)
    provider = _setting(raw, "provider", "deterministic")
    max_attempts = _setting(raw, "max_attempts", DEFAULT_MAX_ATTEMPTS)
    disallow_crop_roles = _setting(raw, "disallow_crop_roles", DEFAULT_DISALLOW_CROP_ROLES)
    max_area_ratio = _setting(raw, "max_area_ratio", DEFAULT_MAX_AREA_RATIO)
    return {
        "provider": str(provider),
        "max_attempts": int(max_attempts),
        "disallow_crop_roles": set(disallow_crop_roles),
        "max_area_ratio": float(max_area_ratio),
    }


def _asset_selection_raw(config: Any) -> Any:
    if isinstance(config, Mapping):
        return config.get("asset_selection", config)
    return getattr(config, "asset_selection", config)


def _setting(raw: Any, key: str, default: Any) -> Any:
    if isinstance(raw, Mapping):
        return raw.get(key, default)
    return getattr(raw, key, default)


def _recoverable_asset_ids(recovery: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for asset_id in recovery.get("recoverable_asset_ids", []):
        if isinstance(asset_id, str) and asset_id.strip():
            ids.append(asset_id.strip())
    return ids


def _boxes_by_id(raw_boxes: Any) -> dict[str, Mapping[str, Any]]:
    boxes: dict[str, Mapping[str, Any]] = {}
    iterable = raw_boxes if isinstance(raw_boxes, list) else []
    for box in iterable:
        if not isinstance(box, Mapping):
            continue
        box_id = box.get("id")
        if isinstance(box_id, str) and box_id:
            boxes[box_id] = box
    return boxes


def _box_ids(raw_boxes: Any) -> set[str]:
    ids: set[str] = set()
    iterable = raw_boxes if isinstance(raw_boxes, list) else []
    for box in iterable:
        if not isinstance(box, Mapping):
            continue
        box_id = box.get("id")
        if isinstance(box_id, str) and box_id:
            ids.add(box_id)
    return ids


def _canvas_size(raw_canvas: Any) -> tuple[float, float]:
    if not isinstance(raw_canvas, Mapping):
        return 0.0, 0.0
    try:
        return float(raw_canvas.get("width")), float(raw_canvas.get("height"))
    except (TypeError, ValueError):
        return 0.0, 0.0


def _parse_bbox(raw_bbox: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(value) for value in raw_bbox]
    except (TypeError, ValueError):
        return None
    left = min(x1, x2)
    top = min(y1, y2)
    right = max(x1, x2)
    bottom = max(y1, y2)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _is_near_whole_canvas(
    bbox: tuple[float, float, float, float],
    canvas_width: float,
    canvas_height: float,
    area_ratio: float,
) -> bool:
    if canvas_width <= 0 or canvas_height <= 0:
        return False
    width_ratio = (bbox[2] - bbox[0]) / canvas_width
    height_ratio = (bbox[3] - bbox[1]) / canvas_height
    edge_aligned = (
        bbox[0] <= max(1.0, canvas_width * 0.01)
        and bbox[1] <= max(1.0, canvas_height * 0.01)
        and bbox[2] >= canvas_width - max(1.0, canvas_width * 0.01)
        and bbox[3] >= canvas_height - max(1.0, canvas_height * 0.01)
    )
    return area_ratio >= 0.90 or (edge_aligned and width_ratio >= 0.90 and height_ratio >= 0.90)


def _next_asset_id(used_asset_ids: set[str], start_index: int) -> tuple[str, int]:
    index = start_index
    while True:
        asset_id = f"AF{index:02d}"
        index += 1
        if asset_id not in used_asset_ids:
            return asset_id, index
