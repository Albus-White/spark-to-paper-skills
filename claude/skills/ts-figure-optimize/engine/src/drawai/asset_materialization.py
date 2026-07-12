from __future__ import annotations

import json
import math
import os
import re
import shutil
from collections import deque
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from .asset_geometry import geometry_crop, normalize_asset_geometry
from .asset_selection_loop import normalize_and_validate_asset_decisions
from .rmbg_client import RmbgResult

ASSET_MANIFEST_SCHEMA = "drawai.asset_manifest.v1"
COMPONENT_INSERTABLE_SPLIT_POLICIES = {"safe_compound_split", "text_svg_only"}
COMPONENT_INSERTABLE_KINDS = {"raster_symbol_transparent"}
RUN0_RASTER_CATEGORIES = {"crop", "crop_nobg"}
RUN0_CATEGORY_ALIASES = {
    "crop_no_bg": "crop_nobg",
    "crop_without_background": "crop_nobg",
    "without_background": "crop_nobg",
    "transparent_subject": "crop_nobg",
    "remove_background": "crop_nobg",
    "rmbg": "crop_nobg",
    "preserve_crop": "crop",
    "direct_crop": "crop",
    "crop_asset": "crop",
    "native_svg": "svg_self_draw",
    "svg": "svg_self_draw",
    "svg_direct": "svg_self_draw",
    "self_draw": "svg_self_draw",
}


def materialize_assets(
    figure_image_path: str | Path,
    box_ir: Mapping[str, Any],
    decisions: Mapping[str, Any],
    assets_dir: str | Path,
    asset_selection_config: Any = None,
    *,
    disallow_crop_roles: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    max_area_ratio: float | None = None,
    svg_dir: str | Path | None = None,
    rmbg_config: Any = None,
    rmbg_client: Any = None,
    asset_policy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assets_root = Path(assets_dir).expanduser().resolve()
    svg_root = Path(svg_dir).expanduser().resolve() if svg_dir is not None else _default_svg_root(assets_root)
    normalized_decisions = normalize_and_validate_asset_decisions(
        box_ir,
        decisions,
        asset_selection_config,
        disallow_crop_roles=disallow_crop_roles,
        max_area_ratio=max_area_ratio,
    )
    boxes_by_id = _boxes_by_id(box_ir.get("boxes"))
    manifest: dict[str, Any] = {
        "schema": ASSET_MANIFEST_SCHEMA,
        "assets": [],
    }
    rmbg_settings = _rmbg_settings(rmbg_config)
    policy_by_asset_id = _asset_policy_by_asset_id(asset_policy_report)

    crops_dir = assets_root / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(figure_image_path) as image:
        source = image.copy()
    geometry_base_dir = _case_root_from_figure_image(figure_image_path)

    for decision in normalized_decisions["decisions"]:
        if not isinstance(decision, Mapping) or decision.get("decision") != "crop_asset":
            continue
        box_id = decision.get("box_id")
        asset_id = decision.get("asset_id")
        if not isinstance(box_id, str) or box_id not in boxes_by_id:
            raise ValueError(f"Cannot materialize asset for unknown box_id: {box_id!r}")
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError(f"Cannot materialize asset for box_id {box_id!r} without asset_id")

        bbox = _crop_bbox(boxes_by_id[box_id].get("bbox"), source.size)
        if bbox is None:
            raise ValueError(f"Cannot materialize asset {asset_id!r}: box_id {box_id!r} has invalid bbox")

        geometry = normalize_asset_geometry(boxes_by_id[box_id].get("geometry"), fallback_bbox=bbox, image_size=source.size)
        crop = geometry_crop(source, bbox, geometry, base_dir=geometry_base_dir)
        crop_path = crops_dir / f"{asset_id}.png"
        crop.save(crop_path)
        crop_href = _relative_href(crop_path, svg_root)
        asset_record: dict[str, Any] = {
            "asset_id": asset_id,
            "box_id": box_id,
            "bbox": list(bbox),
            "source_svg_href": crop_href,
            "source_width": crop.width,
            "source_height": crop.height,
            "svg_href": crop_href,
            "width": crop.width,
            "height": crop.height,
            "active_variant": "with_background",
        }
        if geometry is not None:
            asset_record["geometry"] = geometry
        asset_policy = policy_by_asset_id.get(asset_id)
        if asset_policy is not None:
            _attach_asset_policy(asset_record, asset_policy)

        component_specs = _insertable_component_specs(asset_policy, bbox, source.size)
        if component_specs:
            asset_record["insertable"] = False
            asset_record["restore_strategy"] = "component_assets"
            asset_record.pop("svg_href", None)
            asset_record["insertable_components"] = _materialize_insertable_components(
                source,
                component_specs,
                crops_dir,
                svg_root,
                rmbg_settings,
                rmbg_client,
            )

        if not component_specs and rmbg_settings["enabled"]:
            if rmbg_client is None:
                raise RuntimeError("RMBG asset materialization is enabled but no RMBG client was provided")
            rmbg_result = _remove_background(
                rmbg_client,
                crop,
                asset_id,
                timeout_s=rmbg_settings["timeout_seconds"],
                model_path=rmbg_settings["model_path"],
            )
            nobg = _cleanup_cutout_border_background(rmbg_result.image.convert("RGBA"))
            nobg_path = crops_dir / f"{asset_id}_nobg.png"
            nobg.save(nobg_path)
            nobg_href = _relative_href(nobg_path, svg_root)
            asset_record["nobg_svg_href"] = nobg_href
            asset_record["nobg_width"] = nobg.width
            asset_record["nobg_height"] = nobg.height
            asset_record["svg_href"] = nobg_href
            asset_record["width"] = nobg.width
            asset_record["height"] = nobg.height
            asset_record["active_variant"] = "without_background"
            asset_record["rmbg_elapsed_ms"] = rmbg_result.elapsed_ms
            asset_record["rmbg_artifacts"] = rmbg_result.artifacts

        manifest["assets"].append(asset_record)

    _write_json(assets_root / "asset_manifest.json", manifest)
    return manifest


def materialize_run0_refined_assets(
    figure_image_path: str | Path,
    element_analysis: Mapping[str, Any],
    assets_dir: str | Path,
    *,
    svg_dir: str | Path | None = None,
    rmbg_config: Any = None,
    rmbg_client: Any = None,
) -> dict[str, Any]:
    """Materialize final raster assets from Codex run0 refined elements."""

    assets_root = Path(assets_dir).expanduser().resolve()
    svg_root = Path(svg_dir).expanduser().resolve() if svg_dir is not None else _default_svg_root(assets_root)
    refined_crops_dir = assets_root / "crops" / "run0_refined"
    if refined_crops_dir.exists():
        shutil.rmtree(refined_crops_dir)
    refined_crops_dir.mkdir(parents=True, exist_ok=True)

    elements = element_analysis.get("elements")
    if not isinstance(elements, list):
        raise ValueError("run0 element_analysis.json must contain an elements list")

    with Image.open(figure_image_path) as image:
        source = image.convert("RGBA")

    rmbg_settings = _rmbg_settings(rmbg_config)
    analysis_root = _element_analysis_root(element_analysis)
    geometry_base_dir = analysis_root or _case_root_from_figure_image(figure_image_path)
    manifest: dict[str, Any] = {
        "schema": ASSET_MANIFEST_SCHEMA,
        "source": "codex_run0_refined_assets",
        "assets": [],
    }
    seen_asset_ids: dict[str, int] = {}

    for index, element in enumerate(elements, start=1):
        if not isinstance(element, Mapping):
            continue
        category = _run0_category(element)
        if category not in RUN0_RASTER_CATEGORIES:
            continue
        bbox = _crop_bbox(element.get("bbox"), source.size)
        if bbox is None:
            raise ValueError(f"Run0 element has invalid bbox: {element.get('box_id') or element.get('id') or index!r}")
        asset_id = _unique_run0_asset_id(element, index, seen_asset_ids)
        geometry = normalize_asset_geometry(element.get("geometry"), fallback_bbox=bbox, image_size=source.size)
        crop = geometry_crop(source, bbox, geometry, base_dir=geometry_base_dir)
        processed_asset = _load_processed_asset(element, analysis_root, category)
        if category == "crop" and processed_asset is not None:
            crop = processed_asset
        crop_path = refined_crops_dir / f"{asset_id}.png"
        crop.save(crop_path)
        crop_href = _relative_href(crop_path, svg_root)
        record: dict[str, Any] = {
            "asset_id": asset_id,
            "box_id": _run0_element_id(element, index),
            "bbox": list(bbox),
            "source_svg_href": crop_href,
            "source_width": crop.width,
            "source_height": crop.height,
            "svg_href": crop_href,
            "width": crop.width,
            "height": crop.height,
            "active_variant": "with_background",
            "render_policy": "raster_png",
            "background_policy": "transparent_subject" if category == "crop_nobg" else "preserve_crop",
            "run0_category": category,
            "run0_refinement_action": element.get("refinement_action"),
            "run0_visual_role": element.get("visual_role"),
            "run0_confidence": element.get("confidence"),
            "run0_reason": element.get("reason"),
        }
        if geometry is not None:
            record["geometry"] = geometry
        source_candidate_ids = element.get("source_candidate_ids")
        if isinstance(source_candidate_ids, list):
            record["source_candidate_ids"] = list(source_candidate_ids)
        element_type = element.get("type")
        if isinstance(element_type, str) and element_type:
            record["type"] = element_type

        if category == "crop_nobg":
            if processed_asset is not None:
                nobg = processed_asset
                nobg_path = refined_crops_dir / f"{asset_id}_nobg.png"
                nobg.save(nobg_path)
                nobg_href = _relative_href(nobg_path, svg_root)
                record["nobg_svg_href"] = nobg_href
                record["nobg_width"] = nobg.width
                record["nobg_height"] = nobg.height
                record["svg_href"] = nobg_href
                record["width"] = nobg.width
                record["height"] = nobg.height
                record["active_variant"] = "without_background"
                record["rmbg_elapsed_ms"] = float(element.get("rmbg_elapsed_ms") or 0.0)
                artifacts = element.get("rmbg_artifacts")
                record["rmbg_artifacts"] = dict(artifacts) if isinstance(artifacts, Mapping) else {}
                record["processed_asset_relative_path"] = str(element.get("processed_asset_relative_path") or "")
            elif rmbg_settings["enabled"]:
                if rmbg_client is None:
                    raise RuntimeError("Run0 requested crop_nobg materialization but no RMBG client was provided")
                rmbg_result = _remove_background(
                    rmbg_client,
                    crop,
                    asset_id,
                    timeout_s=rmbg_settings["timeout_seconds"],
                    model_path=rmbg_settings["model_path"],
                )
                nobg = _cleanup_cutout_border_background(rmbg_result.image.convert("RGBA"))
                nobg_path = refined_crops_dir / f"{asset_id}_nobg.png"
                nobg.save(nobg_path)
                nobg_href = _relative_href(nobg_path, svg_root)
                record["nobg_svg_href"] = nobg_href
                record["nobg_width"] = nobg.width
                record["nobg_height"] = nobg.height
                record["svg_href"] = nobg_href
                record["width"] = nobg.width
                record["height"] = nobg.height
                record["active_variant"] = "without_background"
                record["rmbg_elapsed_ms"] = rmbg_result.elapsed_ms
                record["rmbg_artifacts"] = rmbg_result.artifacts
            else:
                record["nobg_unavailable_reason"] = "rmbg_disabled"

        manifest["assets"].append(record)

    manifest["asset_count"] = len(manifest["assets"])
    _write_json(assets_root / "asset_manifest.json", manifest)
    return manifest


def _element_analysis_root(element_analysis: Mapping[str, Any]) -> Path | None:
    raw = element_analysis.get("case_dir")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return Path(raw).expanduser().resolve(strict=False)


def _case_root_from_figure_image(figure_image_path: str | Path) -> Path:
    path = Path(figure_image_path).expanduser().resolve(strict=False)
    if path.parent.name == "inputs":
        return path.parent.parent
    return path.parent


def _load_processed_asset(element: Mapping[str, Any], analysis_root: Path | None, category: str) -> Image.Image | None:
    raw_path = element.get("processed_asset_relative_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    if str(element.get("processed_asset_source_strategy") or "") != category:
        return None
    if str(element.get("processing_status") or "") != "processed":
        return None
    if analysis_root is None:
        raise ValueError("processed asset path requires element_analysis.case_dir")
    relative_path = Path(raw_path)
    if relative_path.is_absolute():
        raise ValueError(f"processed asset path must be relative to case_dir: {raw_path}")
    candidate = (analysis_root / relative_path).resolve(strict=False)
    try:
        candidate.relative_to(analysis_root)
    except ValueError as exc:
        raise ValueError(f"processed asset path escapes case_dir: {raw_path}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"processed asset file is missing: {candidate}")
    with Image.open(candidate) as image:
        return image.convert("RGBA")


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


def _run0_category(element: Mapping[str, Any]) -> str:
    for key in ("category", "recommended_asset_source", "method", "current_pipeline_method"):
        raw = element.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        normalized = raw.strip().lower().replace("-", "_")
        return RUN0_CATEGORY_ALIASES.get(normalized, normalized)
    return ""


def _run0_element_id(element: Mapping[str, Any], index: int) -> str:
    for key in ("box_id", "element_id", "id", "asset_id"):
        value = element.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"E{index:03d}"


def _unique_run0_asset_id(element: Mapping[str, Any], index: int, seen_asset_ids: dict[str, int]) -> str:
    base = f"R0_{_safe_asset_token(_run0_element_id(element, index))}"
    count = seen_asset_ids.get(base, 0) + 1
    seen_asset_ids[base] = count
    return base if count == 1 else f"{base}_{count:02d}"


def _safe_asset_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    return token or "asset"


def _crop_bbox(raw_bbox: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(value) for value in raw_bbox]
    except (TypeError, ValueError):
        return None
    width, height = image_size
    left = max(0, min(width, round(min(x1, x2))))
    top = max(0, min(height, round(min(y1, y2))))
    right = max(0, min(width, round(max(x1, x2))))
    bottom = max(0, min(height, round(max(y1, y2))))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _relative_href(path: Path, start_dir: Path) -> str:
    relative = os.path.relpath(str(path.resolve(strict=False)), start=str(start_dir.resolve(strict=False)))
    return relative.replace(os.sep, "/").replace("\\", "/")


def _default_svg_root(assets_root: Path) -> Path:
    if assets_root.name == "assets" and assets_root.parent.name == "svg_to_ppt":
        return assets_root.parent.parent / "svg"
    if assets_root.name == "assets" and assets_root.parent.name == "svg":
        return assets_root.parent
    return assets_root.parent / "svg"


def _rmbg_settings(config: Any) -> dict[str, Any]:
    if config is None:
        return {
            "enabled": False,
            "timeout_seconds": 600.0,
            "model_path": "",
        }
    raw = config.get("rmbg", config) if isinstance(config, Mapping) else config
    return {
        "enabled": bool(_setting(raw, "enabled", False)),
        "timeout_seconds": float(_setting(raw, "timeout_seconds", 600.0)),
        "model_path": str(_setting(raw, "model_path", "")),
    }


def _setting(raw: Any, key: str, default: Any) -> Any:
    if isinstance(raw, Mapping):
        return raw.get(key, default)
    return getattr(raw, key, default)


def _asset_policy_by_asset_id(asset_policy_report: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(asset_policy_report, Mapping):
        return {}
    assets = asset_policy_report.get("assets")
    if not isinstance(assets, list):
        return {}
    by_id: dict[str, Mapping[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        asset_id = asset.get("asset_id")
        if isinstance(asset_id, str) and asset_id:
            by_id[asset_id] = asset
    return by_id


def _attach_asset_policy(asset_record: dict[str, Any], asset_policy: Mapping[str, Any]) -> None:
    for key in (
        "render_policy",
        "background_policy",
        "split_policy",
        "confidence",
        "current_label",
        "should_run_rmbg",
    ):
        if key in asset_policy:
            asset_record[key] = asset_policy[key]
    reason_codes = asset_policy.get("reason_codes")
    if isinstance(reason_codes, list):
        asset_record["policy_reason_codes"] = list(reason_codes)
    components = asset_policy.get("components")
    if isinstance(components, list):
        asset_record["components"] = components


def _insertable_component_specs(
    asset_policy: Mapping[str, Any] | None,
    parent_bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> list[dict[str, Any]]:
    if not isinstance(asset_policy, Mapping):
        return []
    if str(asset_policy.get("split_policy") or "") not in COMPONENT_INSERTABLE_SPLIT_POLICIES:
        return []
    components = asset_policy.get("components")
    if not isinstance(components, list):
        return []
    parent_width = max(0, parent_bbox[2] - parent_bbox[0])
    parent_height = max(0, parent_bbox[3] - parent_bbox[1])
    specs: list[dict[str, Any]] = []
    for index, component in enumerate(components, start=1):
        if not isinstance(component, Mapping):
            continue
        if str(component.get("kind") or "") not in COMPONENT_INSERTABLE_KINDS:
            continue
        local_bbox = _component_local_bbox(component.get("bbox"), (parent_width, parent_height))
        if local_bbox is None:
            continue
        global_bbox = _component_global_bbox(local_bbox, parent_bbox, image_size)
        if global_bbox is None:
            continue
        specs.append(
            {
                "index": index,
                "parent_asset_id": asset_policy.get("asset_id"),
                "kind": component.get("kind"),
                "source": component.get("source"),
                "confidence": component.get("confidence") or asset_policy.get("confidence"),
                "reason_codes": component.get("reason_codes") if isinstance(component.get("reason_codes"), list) else [],
                "local_bbox": local_bbox,
                "bbox": global_bbox,
                "render_policy": "raster_png",
                "background_policy": "transparent_subject",
                "split_policy": asset_policy.get("split_policy"),
            }
        )
    return specs


def _component_local_bbox(raw_bbox: Any, crop_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(value) for value in raw_bbox]
    except (TypeError, ValueError):
        return None
    width, height = crop_size
    left = max(0, min(width, round(min(x1, x2))))
    top = max(0, min(height, round(min(y1, y2))))
    right = max(0, min(width, round(max(x1, x2))))
    bottom = max(0, min(height, round(max(y1, y2))))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _component_global_bbox(
    local_bbox: tuple[int, int, int, int],
    parent_bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    raw = (
        parent_bbox[0] + local_bbox[0],
        parent_bbox[1] + local_bbox[1],
        parent_bbox[0] + local_bbox[2],
        parent_bbox[1] + local_bbox[3],
    )
    return _crop_bbox(raw, image_size)


def _materialize_insertable_components(
    source: Image.Image,
    component_specs: list[dict[str, Any]],
    crops_dir: Path,
    svg_root: Path,
    rmbg_settings: Mapping[str, Any],
    rmbg_client: Any,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for component_number, spec in enumerate(component_specs, start=1):
        parent_asset_id = str(spec.get("parent_asset_id") or "asset")
        component_id = f"{parent_asset_id}_C{component_number:02d}"
        bbox = spec["bbox"]
        crop = source.crop(bbox)
        crop_path = crops_dir / f"{component_id}.png"
        crop.save(crop_path)
        crop_href = _relative_href(crop_path, svg_root)
        active_href = crop_href
        active_variant = "with_background"
        width = crop.width
        height = crop.height
        rmbg_metadata: dict[str, Any] = {}

        if rmbg_settings["enabled"]:
            if rmbg_client is None:
                raise RuntimeError("RMBG asset materialization is enabled but no RMBG client was provided")
            rmbg_result = _remove_background(
                rmbg_client,
                crop,
                component_id,
                timeout_s=rmbg_settings["timeout_seconds"],
                model_path=rmbg_settings["model_path"],
            )
            nobg = _cleanup_cutout_border_background(rmbg_result.image.convert("RGBA"))
            nobg_path = crops_dir / f"{component_id}_nobg.png"
            nobg.save(nobg_path)
            active_href = _relative_href(nobg_path, svg_root)
            active_variant = "without_background"
            width = nobg.width
            height = nobg.height
            rmbg_metadata = {
                "nobg_svg_href": active_href,
                "nobg_width": width,
                "nobg_height": height,
                "rmbg_elapsed_ms": rmbg_result.elapsed_ms,
                "rmbg_artifacts": rmbg_result.artifacts,
            }

        record = {
            "component_id": component_id,
            "asset_id": component_id,
            "parent_asset_id": parent_asset_id,
            "kind": spec.get("kind"),
            "source": spec.get("source"),
            "confidence": spec.get("confidence"),
            "reason_codes": list(spec.get("reason_codes") or []),
            "local_bbox": list(spec["local_bbox"]),
            "bbox": list(bbox),
            "source_svg_href": crop_href,
            "source_width": crop.width,
            "source_height": crop.height,
            "svg_href": active_href,
            "width": width,
            "height": height,
            "active_variant": active_variant,
            "render_policy": spec.get("render_policy") or "raster_png",
            "background_policy": spec.get("background_policy") or "transparent_subject",
            "split_policy": spec.get("split_policy"),
        }
        record.update(rmbg_metadata)
        records.append(record)
    return records


def _remove_background(
    rmbg_client: Any,
    crop: Image.Image,
    asset_id: str,
    *,
    timeout_s: float,
    model_path: str,
) -> RmbgResult:
    result = rmbg_client.remove_background(
        crop,
        asset_id,
        timeout_s=timeout_s,
        model_path=model_path,
        artifact_prefix=f"drawai_assets/{asset_id}",
    )
    if isinstance(result, RmbgResult):
        return result
    if isinstance(result, Mapping):
        image = result.get("image")
        if not isinstance(image, Image.Image):
            raise RuntimeError("RMBG client response mapping must include a PIL image")
        artifacts = result.get("artifacts")
        return RmbgResult(
            image=image,
            artifacts=dict(artifacts) if isinstance(artifacts, Mapping) else {},
            elapsed_ms=float(result.get("elapsed_ms", 0.0)),
        )
    if isinstance(result, Image.Image):
        return RmbgResult(image=result, artifacts={}, elapsed_ms=0.0)
    raise RuntimeError(f"RMBG client returned unsupported result type: {type(result).__name__}")


def _cleanup_cutout_border_background(image: Image.Image) -> Image.Image:
    """Remove edge-connected pale crop background that RMBG leaves behind."""

    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width <= 0 or height <= 0:
        return rgba

    pixels = rgba.load()
    border_colors = _background_like_border_colors(rgba)
    if not border_colors:
        return rgba

    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    def add_seed(x: int, y: int) -> None:
        if (x, y) in visited:
            return
        if not _is_pale_background_pixel(pixels[x, y], border_colors):
            return
        visited.add((x, y))
        queue.append((x, y))

    for x in range(width):
        add_seed(x, 0)
        add_seed(x, height - 1)
    for y in range(1, height - 1):
        add_seed(0, y)
        add_seed(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) in visited:
                continue
            if not _is_pale_background_pixel(pixels[nx, ny], border_colors):
                continue
            visited.add((nx, ny))
            queue.append((nx, ny))

    if not visited:
        return rgba

    cleaned = rgba.copy()
    cleaned_pixels = cleaned.load()
    for x, y in visited:
        red, green, blue, _alpha = cleaned_pixels[x, y]
        cleaned_pixels[x, y] = (red, green, blue, 0)
    return cleaned


def _background_like_border_colors(image: Image.Image) -> list[tuple[int, int, int]]:
    pixels = image.load()
    width, height = image.size
    colors: list[tuple[int, int, int]] = []
    for x in range(width):
        for y in (0, height - 1):
            red, green, blue, alpha = pixels[x, y]
            if alpha > 8 and _is_pale_low_saturation(red, green, blue):
                colors.append((red, green, blue))
    for y in range(height):
        for x in (0, width - 1):
            red, green, blue, alpha = pixels[x, y]
            if alpha > 8 and _is_pale_low_saturation(red, green, blue):
                colors.append((red, green, blue))
    return colors


def _is_pale_background_pixel(pixel: tuple[int, int, int, int], border_colors: list[tuple[int, int, int]]) -> bool:
    red, green, blue, alpha = pixel
    if alpha <= 8:
        return True
    if _is_pale_low_saturation(red, green, blue):
        return True
    if _luma(red, green, blue) < 180:
        return False
    return any(_color_distance((red, green, blue), border_color) <= 42.0 for border_color in border_colors)


def _is_pale_low_saturation(red: int, green: int, blue: int) -> bool:
    channel_max = max(red, green, blue)
    channel_min = min(red, green, blue)
    return channel_min >= 208 and _luma(red, green, blue) >= 222 and channel_max - channel_min <= 48


def _luma(red: int, green: int, blue: int) -> float:
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _color_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second, strict=True)))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
