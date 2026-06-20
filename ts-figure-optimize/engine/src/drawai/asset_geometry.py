from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageChops, ImageDraw

GeometryBBox = tuple[int, int, int, int]


def normalize_asset_geometry(
    raw_geometry: Any,
    *,
    fallback_bbox: Sequence[float] | None = None,
    image_size: tuple[int | float, int | float] | None = None,
) -> dict[str, Any] | None:
    if raw_geometry is None:
        return None
    if not isinstance(raw_geometry, Mapping):
        return None

    kind = str(raw_geometry.get("kind") or raw_geometry.get("type") or "").strip().lower()
    if not kind:
        if _raw_mask_path(raw_geometry):
            kind = "mask"
        elif _raw_polygon_points(raw_geometry) is not None:
            kind = "polygon"
        elif raw_geometry.get("bbox") is not None or fallback_bbox is not None:
            kind = "bbox"

    if kind in {"poly", "polygon_box"}:
        kind = "polygon"
    if kind in {"segmentation", "alpha_mask", "bitmap_mask"}:
        kind = "mask"

    if kind == "polygon":
        points = _normalize_polygon_points(_raw_polygon_points(raw_geometry), image_size=image_size)
        if points is None:
            return None
        bbox = _float_bbox_from_points(points)
        return {
            "kind": "polygon",
            "points": points,
            "bbox": bbox,
            "coordinate_system": "figure_image_pixels",
        }

    if kind == "mask":
        mask_path = _raw_mask_path(raw_geometry)
        if not mask_path:
            return None
        bbox = _normalize_float_bbox(raw_geometry.get("bbox") or raw_geometry.get("mask_bbox") or fallback_bbox, image_size)
        if bbox is None:
            return None
        return {
            "kind": "mask",
            "mask_path": mask_path,
            "bbox": bbox,
            "coordinate_system": "figure_image_pixels",
        }

    if kind == "bbox":
        bbox = _normalize_float_bbox(raw_geometry.get("bbox") or fallback_bbox, image_size)
        if bbox is None:
            return None
        return {
            "kind": "bbox",
            "bbox": bbox,
            "coordinate_system": "figure_image_pixels",
        }

    return None


def normalize_geometry_from_region(
    raw_region: Mapping[str, Any],
    *,
    fallback_bbox: Sequence[float] | None = None,
    image_size: tuple[int | float, int | float] | None = None,
) -> dict[str, Any] | None:
    geometry = normalize_asset_geometry(raw_region.get("geometry"), fallback_bbox=fallback_bbox, image_size=image_size)
    if geometry is not None:
        return geometry
    if _raw_mask_path(raw_region):
        return normalize_asset_geometry(
            {"kind": "mask", "mask_path": _raw_mask_path(raw_region), "bbox": raw_region.get("bbox") or fallback_bbox},
            fallback_bbox=fallback_bbox,
            image_size=image_size,
        )
    points = _raw_polygon_points(raw_region)
    if points is not None:
        return normalize_asset_geometry({"kind": "polygon", "points": points}, image_size=image_size)
    return None


def geometry_bbox(geometry: Mapping[str, Any] | None) -> list[float] | None:
    if not isinstance(geometry, Mapping):
        return None
    bbox = _normalize_float_bbox(geometry.get("bbox"), None)
    if bbox is not None:
        return bbox
    if str(geometry.get("kind") or "") == "polygon":
        points = _normalize_polygon_points(geometry.get("points"), image_size=None)
        if points is not None:
            return _float_bbox_from_points(points)
    return None


def geometry_crop(
    source: Image.Image,
    bbox: GeometryBBox,
    geometry: Mapping[str, Any] | None,
    *,
    base_dir: str | Path | None = None,
) -> Image.Image:
    crop = source.convert("RGBA").crop(bbox)
    if not isinstance(geometry, Mapping):
        return crop

    kind = str(geometry.get("kind") or "").strip().lower()
    if kind == "polygon":
        points = _normalize_polygon_points(geometry.get("points"), image_size=source.size)
        if points is None:
            return crop
        local_points = [(point[0] - bbox[0], point[1] - bbox[1]) for point in points]
        mask = Image.new("L", crop.size, 0)
        ImageDraw.Draw(mask).polygon(local_points, fill=255)
        return _apply_alpha_mask(crop, mask)

    if kind == "mask":
        mask_path = _raw_mask_path(geometry)
        if not mask_path:
            return crop
        mask = _load_geometry_mask(mask_path, source.size, crop.size, bbox, base_dir=base_dir)
        return _apply_alpha_mask(crop, mask)

    return crop


def relative_geometry_path(path: Path, base_dir: Path) -> str:
    return path.resolve(strict=False).relative_to(base_dir.resolve(strict=False)).as_posix()


def _raw_mask_path(raw: Mapping[str, Any]) -> str:
    for key in ("mask_path", "path", "alpha_mask_path"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _raw_polygon_points(raw: Mapping[str, Any]) -> Any:
    for key in ("points", "polygon", "vertices"):
        if key in raw:
            return raw[key]
    segmentation = raw.get("segmentation")
    if isinstance(segmentation, list):
        if segmentation and all(_is_number(item) for item in segmentation):
            return segmentation
        if segmentation and all(isinstance(item, (list, tuple)) for item in segmentation):
            return segmentation[0]
    return None


def _normalize_polygon_points(
    raw_points: Any,
    *,
    image_size: tuple[int | float, int | float] | None,
) -> list[list[float]] | None:
    if not isinstance(raw_points, (list, tuple)):
        return None
    pairs: list[tuple[Any, Any]] = []
    if raw_points and all(_is_number(item) for item in raw_points):
        if len(raw_points) % 2 != 0:
            return None
        pairs = [(raw_points[index], raw_points[index + 1]) for index in range(0, len(raw_points), 2)]
    else:
        for item in raw_points:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                return None
            pairs.append((item[0], item[1]))
    if len(pairs) < 3:
        return None
    width = float(image_size[0]) if image_size is not None else None
    height = float(image_size[1]) if image_size is not None else None
    points: list[list[float]] = []
    for raw_x, raw_y in pairs:
        if not _is_number(raw_x) or not _is_number(raw_y):
            return None
        x = float(raw_x)
        y = float(raw_y)
        if width is not None:
            x = min(width, max(0.0, x))
        if height is not None:
            y = min(height, max(0.0, y))
        points.append([x, y])
    bbox = _float_bbox_from_points(points)
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return points


def _float_bbox_from_points(points: Sequence[Sequence[float]]) -> list[float]:
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _normalize_float_bbox(
    raw_bbox: Any,
    image_size: tuple[int | float, int | float] | None,
) -> list[float] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    if not all(_is_number(value) for value in raw_bbox):
        return None
    x1, y1, x2, y2 = [float(value) for value in raw_bbox]
    left = min(x1, x2)
    right = max(x1, x2)
    top = min(y1, y2)
    bottom = max(y1, y2)
    if image_size is not None:
        width, height = float(image_size[0]), float(image_size[1])
        left = max(0.0, min(width, left))
        right = max(0.0, min(width, right))
        top = max(0.0, min(height, top))
        bottom = max(0.0, min(height, bottom))
    if right <= left or bottom <= top:
        return None
    return [left, top, right, bottom]


def _load_geometry_mask(
    raw_path: str,
    source_size: tuple[int, int],
    crop_size: tuple[int, int],
    bbox: GeometryBBox,
    *,
    base_dir: str | Path | None,
) -> Image.Image:
    path = Path(raw_path)
    if not path.is_absolute():
        if base_dir is None:
            raise ValueError(f"relative mask path requires a base_dir: {raw_path}")
        path = Path(base_dir) / path
    if not path.is_file():
        raise FileNotFoundError(f"geometry mask is missing: {path}")
    with Image.open(path) as mask_image:
        mask = mask_image.convert("L")
    if mask.size == source_size:
        return mask.crop(bbox)
    if mask.size == crop_size:
        return mask
    return mask.resize(crop_size, Image.Resampling.NEAREST)


def _apply_alpha_mask(crop: Image.Image, mask: Image.Image) -> Image.Image:
    rgba = crop.convert("RGBA")
    mask_l = mask.convert("L")
    if mask_l.size != rgba.size:
        mask_l = mask_l.resize(rgba.size, Image.Resampling.NEAREST)
    existing_alpha = rgba.getchannel("A")
    rgba.putalpha(ImageChops.multiply(existing_alpha, mask_l))
    return rgba


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) and math.isfinite(float(value))
