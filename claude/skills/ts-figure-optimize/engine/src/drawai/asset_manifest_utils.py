from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any


def iter_manifest_image_items(asset_manifest: Mapping[str, Any] | list[Any] | None) -> Iterator[dict[str, Any]]:
    """Yield manifest image entries that are allowed to be inserted into SVG."""

    assets = asset_manifest.get("assets", []) if isinstance(asset_manifest, Mapping) else asset_manifest
    if not isinstance(assets, list):
        return
    all_component_items: list[dict[str, Any]] = []
    regular_items: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        asset_component_items = list(_iter_insertable_components(asset))
        if asset_component_items:
            all_component_items.extend(asset_component_items)
            continue
        if asset.get("insertable") is False:
            continue
        item = _manifest_item_from_mapping(asset)
        if item is not None:
            regular_items.append(item)

    yield from all_component_items
    for item in regular_items:
        if _is_component_duplicate(item, all_component_items):
            continue
        yield item


def manifest_image_paths(asset_manifest: Mapping[str, Any] | list[Any] | None, svg_dir: Path) -> set[Path]:
    paths: set[Path] = set()
    assets = asset_manifest.get("assets", []) if isinstance(asset_manifest, Mapping) else asset_manifest
    if not isinstance(assets, list):
        return paths

    component_items: list[dict[str, Any]] = []
    regular_items: list[Mapping[str, Any] | str] = []
    for asset in assets:
        if not isinstance(asset, Mapping):
            regular_items.append(asset)
            continue
        asset_component_items = list(_iter_insertable_components(asset))
        if asset_component_items:
            component_items.extend(asset_component_items)
            for component in asset_component_items:
                _add_manifest_path(paths, component, svg_dir)
            continue
        if asset.get("insertable") is False:
            continue
        regular_items.append(asset)

    for item in regular_items:
        if isinstance(item, Mapping) and _is_component_duplicate(item, component_items):
            continue
        _add_manifest_path(paths, item, svg_dir)
    return paths


def extend_asset_manifest_for_svg_export(
    run_root: str | Path,
    asset_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an export-time manifest that includes native backfill assets used by SVG generation."""

    base_assets = asset_manifest.get("assets") if isinstance(asset_manifest.get("assets"), list) else []
    native_assets = native_backfill_validation_assets_for_export(run_root)
    if not native_assets:
        return dict(asset_manifest), {
            "native_backfill_asset_count": 0,
            "native_backfill_request_count": 0,
            "manifest_extended": False,
        }

    schema = str(asset_manifest.get("schema") or "drawai.asset_manifest.v1")
    request_paths = {
        str(asset.get("native_backfill_request"))
        for asset in native_assets
        if str(asset.get("native_backfill_request") or "").strip()
    }
    return {
        "schema": schema,
        "assets": [*base_assets, *native_assets],
    }, {
        "native_backfill_asset_count": len(native_assets),
        "native_backfill_request_count": len(request_paths),
        "manifest_extended": True,
    }


def native_backfill_validation_assets_for_export(run_root: str | Path) -> list[dict[str, Any]]:
    root = Path(run_root).expanduser().resolve(strict=False)
    svg_dir = root / "svg"
    attempts_dir = svg_dir / "attempts"
    assets: list[dict[str, Any]] = []
    seen_hrefs: set[str] = set()
    for request_path in sorted(attempts_dir.glob("**/native_backfill_request.json")):
        request = json.loads(request_path.read_text(encoding="utf-8"))
        candidates = request.get("candidates") if isinstance(request, Mapping) else None
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            bbox = candidate.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            asset_id = str(candidate.get("asset_id") or "").strip()
            if not asset_id:
                continue
            for suffix, href_key, background_policy in (
                ("", "preserve_href", "preserve_crop"),
                ("_nobg", "nobg_href", "transparent_subject"),
            ):
                href = str(candidate.get(href_key) or "").strip()
                if not href or href in seen_hrefs:
                    continue
                if not (svg_dir / href).is_file():
                    continue
                assets.append(
                    {
                        "asset_id": f"{asset_id}{suffix}",
                        "box_id": candidate.get("box_id"),
                        "bbox": bbox,
                        "svg_href": href,
                        "render_policy": "raster_png",
                        "background_policy": background_policy,
                        "native_backfill_candidate": True,
                        "native_backfill_request": str(request_path),
                        "insertable": True,
                    }
                )
                seen_hrefs.add(href)
    return assets


def _add_manifest_path(paths: set[Path], raw_item: Any, svg_dir: Path) -> None:
    if isinstance(raw_item, Mapping):
        raw_path = (
            raw_item.get("svg_href")
            or raw_item.get("href")
            or raw_item.get("path")
            or raw_item.get("local_path")
            or raw_item.get("source_path")
        )
    else:
        raw_path = raw_item
    if not isinstance(raw_path, str) or not raw_path:
        return
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = svg_dir / path
    paths.add(path.resolve(strict=False))


def _iter_insertable_components(asset: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    components = asset.get("insertable_components")
    if not isinstance(components, list):
        return
    for component in components:
        if not isinstance(component, Mapping):
            continue
        item = _manifest_item_from_mapping(component)
        if item is None:
            continue
        item.setdefault("asset_id", component.get("asset_id") or asset.get("asset_id"))
        item.setdefault("box_id", asset.get("box_id"))
        item.setdefault("parent_asset_id", asset.get("asset_id"))
        item.setdefault("render_policy", component.get("render_policy") or asset.get("render_policy"))
        item.setdefault("background_policy", component.get("background_policy") or asset.get("background_policy"))
        item.setdefault("split_policy", component.get("split_policy") or asset.get("split_policy"))
        yield item


def _manifest_item_from_mapping(asset: Mapping[str, Any]) -> dict[str, Any] | None:
    href = str(asset.get("svg_href") or "").strip()
    bbox = _manifest_bbox(asset.get("bbox"))
    if not href or bbox is None:
        return None
    item = dict(asset)
    item["svg_href"] = href
    item["bbox"] = list(bbox)
    return item


def _manifest_bbox(raw_bbox: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(value) for value in raw_bbox)
    except (TypeError, ValueError):
        return None
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _is_component_duplicate(item: Mapping[str, Any], component_items: list[dict[str, Any]]) -> bool:
    item_bbox = _manifest_bbox(item.get("bbox"))
    if item_bbox is None:
        return False
    item_area = _bbox_area(item_bbox)
    if item_area <= 0:
        return False
    for component in component_items:
        component_bbox = _manifest_bbox(component.get("bbox"))
        if component_bbox is None:
            continue
        component_area = _bbox_area(component_bbox)
        if component_area <= 0:
            continue
        intersection = _bbox_intersection(item_bbox, component_bbox)
        if intersection is None:
            continue
        intersection_area = _bbox_area(intersection)
        if intersection_area <= 0:
            continue
        iou = intersection_area / (item_area + component_area - intersection_area)
        component_coverage = intersection_area / component_area
        item_coverage = intersection_area / item_area
        if iou >= 0.60:
            return True
        if component_coverage >= 0.85 and item_coverage >= 0.45:
            return True
    return False


def _bbox_intersection(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


__all__ = ["iter_manifest_image_items", "manifest_image_paths"]
