from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from PIL import Image

from .domain.box_ir import normalize_box_type

RenderPolicy = Literal["native_svg", "raster_png", "hybrid"]
BackgroundPolicy = Literal["preserve_crop", "transparent_subject", "split_backplate"]
Confidence = Literal["high", "medium", "low"]
ComponentKind = Literal["svg_geometry", "svg_text", "raster_symbol_transparent", "svg_symbol", "preserve_raster"]
SplitPolicy = Literal["no_split", "safe_compound_split", "text_svg_only", "fallback_raster"]


@dataclass(frozen=True)
class AssetPolicySettings:
    texture_threshold: float = 0.55
    native_svg_geometry_threshold: float = 0.58
    native_svg_max_component_count: int = 12
    native_svg_max_foreground_ratio: float = 0.28
    preserve_border_touch_threshold: float = 0.34
    transparent_uniform_border_threshold: float = 0.62
    transparent_near_white_border_threshold: float = 0.55
    hybrid_backplate_threshold: float = 0.62


@dataclass(frozen=True)
class AssetCropMetrics:
    crop_width: int
    crop_height: int
    box_area_ratio: float
    foreground_ratio: float
    border_foreground_ratio: float
    border_uniformity: float
    near_white_border_ratio: float
    light_neutral_border_ratio: float
    edge_density: float
    thin_line_score: float
    color_complexity: float
    local_entropy: float
    texture_score: float
    simple_geometry_score: float
    backplate_score: float
    warm_saturated_ratio: float
    connected_component_count: int
    largest_component_ratio: float
    foreground_touches_sides: int


@dataclass(frozen=True)
class AssetComponent:
    kind: ComponentKind
    bbox: tuple[int, int, int, int]
    confidence: Confidence
    source: str
    reason_codes: tuple[str, ...]
    text: str = ""


@dataclass(frozen=True)
class AssetPolicyDecision:
    asset_id: str
    role: str
    render_policy: RenderPolicy
    background_policy: BackgroundPolicy
    confidence: Confidence
    should_run_rmbg: bool
    reason_codes: tuple[str, ...]
    metrics: AssetCropMetrics
    split_policy: SplitPolicy = "no_split"
    components: tuple[AssetComponent, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        payload["components"] = [asdict(component) for component in self.components]
        return payload


def analyze_asset_crop(
    *,
    image: Image.Image,
    box: Mapping[str, Any] | None = None,
    slide_size: tuple[int | float, int | float] | None = None,
    max_metric_edge: int = 192,
) -> AssetCropMetrics:
    rgb = image.convert("RGB")
    original_width, original_height = rgb.size
    metric_image = _resize_for_metrics(rgb, max_metric_edge=max_metric_edge)
    arr = np.asarray(metric_image, dtype=np.float32)
    height, width = arr.shape[:2]
    margin = max(2, min(16, int(round(min(width, height) * 0.08))))
    border_mask = _border_mask(height, width, margin)
    border_pixels = arr[border_mask]
    bg_color = np.median(border_pixels, axis=0)
    bg_distance = np.linalg.norm(arr - bg_color, axis=2)
    border_distance = bg_distance[border_mask]
    threshold = float(max(24.0, min(78.0, np.percentile(border_distance, 75) + 22.0)))
    foreground = bg_distance > threshold
    foreground = _remove_tiny_boolean_noise(foreground)

    foreground_ratio = float(np.mean(foreground))
    border_foreground_ratio = float(np.mean(foreground[border_mask]))
    border_uniformity = _border_uniformity(border_pixels)
    near_white_border_ratio = _near_white_ratio(border_pixels)
    light_neutral_border_ratio = _light_neutral_ratio(border_pixels)
    edge_density = _edge_density(arr)
    thin_line_score = _thin_line_score(foreground)
    color_complexity = _color_complexity(arr, foreground)
    local_entropy = _local_entropy(arr)
    warm_saturated_ratio = _warm_saturated_ratio(arr)
    texture_score = _texture_score(
        color_complexity=color_complexity,
        local_entropy=local_entropy,
        foreground_ratio=foreground_ratio,
        edge_density=edge_density,
    )
    component_count, largest_component_ratio = _component_metrics(foreground)
    touches_sides = _foreground_touches_sides(foreground, margin=max(2, margin // 2))
    backplate_score = _backplate_score(
        foreground=foreground,
        border_foreground_ratio=border_foreground_ratio,
        touches_sides=touches_sides,
        foreground_ratio=foreground_ratio,
    )
    simple_geometry_score = _simple_geometry_score(
        thin_line_score=thin_line_score,
        color_complexity=color_complexity,
        texture_score=texture_score,
        foreground_ratio=foreground_ratio,
        component_count=component_count,
        edge_density=edge_density,
    )
    box_area_ratio = _box_area_ratio(box, slide_size)

    return AssetCropMetrics(
        crop_width=original_width,
        crop_height=original_height,
        box_area_ratio=box_area_ratio,
        foreground_ratio=foreground_ratio,
        border_foreground_ratio=border_foreground_ratio,
        border_uniformity=border_uniformity,
        near_white_border_ratio=near_white_border_ratio,
        light_neutral_border_ratio=light_neutral_border_ratio,
        edge_density=edge_density,
        thin_line_score=thin_line_score,
        color_complexity=color_complexity,
        local_entropy=local_entropy,
        texture_score=texture_score,
        simple_geometry_score=simple_geometry_score,
        backplate_score=backplate_score,
        warm_saturated_ratio=warm_saturated_ratio,
        connected_component_count=component_count,
        largest_component_ratio=largest_component_ratio,
        foreground_touches_sides=touches_sides,
    )


def decide_asset_policy(
    *,
    asset_id: str,
    role: str,
    metrics: AssetCropMetrics,
    settings: AssetPolicySettings | None = None,
) -> AssetPolicyDecision:
    settings = settings or AssetPolicySettings()
    normalized_role = normalize_box_type(role)
    reasons: list[str] = []

    min_dim = min(metrics.crop_width, metrics.crop_height)
    if min_dim < 16:
        return _decision(
            asset_id,
            normalized_role,
            "raster_png",
            "preserve_crop",
            "low",
            metrics,
            ["tiny_crop"],
        )

    uniform_light_background = (
        metrics.border_uniformity >= settings.transparent_uniform_border_threshold
        and metrics.near_white_border_ratio >= settings.transparent_near_white_border_threshold
    )
    removable_light_background = uniform_light_background or metrics.light_neutral_border_ratio >= 0.58
    if uniform_light_background:
        reasons.append("uniform_light_border")
    elif metrics.light_neutral_border_ratio >= 0.58:
        reasons.append("light_neutral_or_checkerboard_border")

    simple_low_entropy_shape = (
        (
            metrics.local_entropy <= 3.20
            and metrics.connected_component_count <= 8
            and metrics.foreground_ratio <= 0.78
        )
        or (
            metrics.local_entropy <= 3.50
            and metrics.connected_component_count <= 4
            and metrics.color_complexity <= 0.55
            and metrics.foreground_ratio <= 0.78
        )
    )

    texture_like = (
        metrics.texture_score >= settings.texture_threshold
        or metrics.color_complexity >= 0.42
        or (metrics.local_entropy >= 4.55 and metrics.color_complexity >= 0.26)
    )
    pixel_or_dense_fill = (
        min_dim <= 80
        and metrics.foreground_ratio >= 0.32
        and metrics.thin_line_score < 0.62
        and metrics.edge_density >= 0.18
    )
    border_dependent = (
        metrics.border_foreground_ratio >= settings.preserve_border_touch_threshold
        and metrics.foreground_touches_sides >= 3
        and not uniform_light_background
    )
    compact_cutout_symbol = (
        normalized_role == "icon"
        and min_dim <= 96
        and removable_light_background
        and 0.08 <= metrics.foreground_ratio <= 0.72
        and metrics.connected_component_count <= 8
        and not pixel_or_dense_fill
    )

    if pixel_or_dense_fill:
        reasons.extend(["dense_filled_asset", "foreground_background_coupled"])
        return _decision(asset_id, normalized_role, "raster_png", "preserve_crop", "medium", metrics, reasons)

    if compact_cutout_symbol:
        reasons.extend(["compact_symbol_cutout", "removable_light_background"])
        return _decision(asset_id, normalized_role, "raster_png", "transparent_subject", "medium", metrics, reasons)

    if (
        metrics.backplate_score >= settings.hybrid_backplate_threshold
        and metrics.border_foreground_ratio >= 0.30
        and 0.12 <= metrics.foreground_ratio <= 0.45
    ):
        reasons.extend(["probable_backplate", "separable_subject_container"])
        return _decision(asset_id, normalized_role, "hybrid", "split_backplate", "medium", metrics, reasons)

    if (
        normalized_role == "icon"
        and metrics.backplate_score >= 0.78
        and metrics.color_complexity >= 0.75
        and metrics.light_neutral_border_ratio >= 0.55
        and 0.12 <= metrics.foreground_ratio <= 0.32
    ):
        reasons.extend(["probable_backplate", "high_color_inner_symbol"])
        return _decision(asset_id, normalized_role, "hybrid", "split_backplate", "medium", metrics, reasons)

    native_svg_like = (
        (
            metrics.simple_geometry_score >= settings.native_svg_geometry_threshold
            and metrics.connected_component_count <= settings.native_svg_max_component_count
            and metrics.foreground_ratio <= settings.native_svg_max_foreground_ratio
            and metrics.texture_score < 0.42
        )
        or simple_low_entropy_shape
    )
    if native_svg_like:
        if simple_low_entropy_shape:
            reasons.append("simple_low_entropy_geometry")
        else:
            reasons.append("simple_line_geometry")
        reasons.extend(["low_texture", "limited_components"])
        return _decision(asset_id, normalized_role, "native_svg", "transparent_subject", "high", metrics, reasons)

    if texture_like:
        reasons.extend(["texture_like", "high_color_or_entropy"])
        return _decision(asset_id, normalized_role, "raster_png", "preserve_crop", "high", metrics, reasons)

    if border_dependent:
        reasons.extend(["foreground_touches_multiple_edges", "background_context_may_matter"])
        return _decision(asset_id, normalized_role, "raster_png", "preserve_crop", "medium", metrics, reasons)

    if removable_light_background and metrics.texture_score < 0.5:
        reasons.extend(["line_art_on_removable_background", "too_detailed_for_native_svg"])
        return _decision(asset_id, normalized_role, "raster_png", "transparent_subject", "medium", metrics, reasons)

    reasons.append("conservative_preserve_fallback")
    return _decision(asset_id, normalized_role, "raster_png", "preserve_crop", "low", metrics, reasons)


def detect_asset_components(
    *,
    image: Image.Image,
    decision: AssetPolicyDecision,
    asset_box: Mapping[str, Any] | None = None,
    ocr_boxes: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[AssetComponent, ...]:
    normalized_role = normalize_box_type(decision.role)
    if normalized_role != "icon":
        return ()

    crop_width, crop_height = image.size
    text_components = _text_components_from_ocr(
        asset_box=asset_box,
        ocr_boxes=ocr_boxes or (),
        crop_size=(crop_width, crop_height),
    )
    has_warm_policy_reason = "warm_saturated_symbol" in decision.reason_codes
    should_probe_warm_symbol = (
        decision.render_policy == "hybrid"
        or decision.background_policy == "split_backplate"
        or bool(text_components)
        or has_warm_policy_reason
    )
    raster_symbols = (
        _warm_symbol_components(image=image, text_components=text_components) if should_probe_warm_symbol else []
    )

    components: list[AssetComponent] = []
    should_attempt_compound = (
        decision.render_policy == "hybrid"
        or (text_components and raster_symbols)
        or (text_components and decision.render_policy == "native_svg")
    )
    if should_attempt_compound and _has_geometry_residual(decision, text_components, raster_symbols):
        components.append(
            AssetComponent(
                kind="svg_geometry",
                bbox=(0, 0, crop_width, crop_height),
                confidence="medium",
                source="residual_geometry_probe",
                reason_codes=("residual_low_entropy_or_backplate",),
            )
        )
    components.extend(text_components)
    components.extend(raster_symbols)

    if not components and decision.render_policy == "native_svg":
        components.append(
            AssetComponent(
                kind="svg_symbol",
                bbox=(0, 0, crop_width, crop_height),
                confidence=decision.confidence,
                source="asset_policy",
                reason_codes=("whole_asset_svg_symbol",),
            )
        )

    return tuple(components)


def refine_asset_policy_with_components(
    decision: AssetPolicyDecision,
    components: Sequence[AssetComponent],
) -> AssetPolicyDecision:
    component_tuple = tuple(components)
    kinds = {component.kind for component in component_tuple}
    reasons = list(decision.reason_codes)
    render_policy: RenderPolicy = decision.render_policy
    background_policy: BackgroundPolicy = decision.background_policy
    confidence: Confidence = decision.confidence
    split_policy: SplitPolicy = "no_split"
    normalized_role = normalize_box_type(decision.role)

    if _is_safe_compound_split(decision, component_tuple):
        render_policy = "hybrid"
        background_policy = "split_backplate"
        confidence = "medium"
        split_policy = "safe_compound_split"
        reasons.append("compound_safe_split")
    elif kinds == {"raster_symbol_transparent"}:
        if decision.render_policy != "native_svg" and (
            decision.background_policy == "transparent_subject" or "warm_saturated_symbol" in reasons
        ):
            render_policy = "raster_png"
            background_policy = "transparent_subject"
            confidence = "medium" if confidence == "high" else confidence
            reasons.append("single_symbol_cutout")
    elif "svg_text" in kinds and _has_structural_text(component_tuple) and render_policy == "raster_png":
        split_policy = "text_svg_only"
        background_policy = "transparent_subject" if normalized_role == "icon" else background_policy
        reasons.append("structural_text_svg_only")
    elif "svg_text" in kinds and decision.render_policy == "raster_png":
        render_policy = "raster_png"
        background_policy = "transparent_subject" if normalized_role == "icon" else "preserve_crop"
        split_policy = "fallback_raster"
        confidence = "medium" if confidence == "high" else confidence
        reasons.append("text_detected_but_split_not_safe")

    if normalized_role == "picture":
        background_policy = "transparent_subject" if _picture_should_cutout(decision.metrics) else "preserve_crop"
    elif normalized_role == "icon":
        if render_policy == "native_svg":
            background_policy = "transparent_subject"
        elif split_policy == "safe_compound_split":
            background_policy = "split_backplate"
        elif render_policy == "raster_png":
            if _should_preserve_raster_icon_background(decision.metrics, decision.reason_codes):
                background_policy = "preserve_crop"
                reasons.append("raster_icon_background_context_preserved")
            elif not _looks_like_noise_texture(decision.metrics):
                background_policy = "transparent_subject"

    should_run_rmbg = background_policy in {"transparent_subject", "split_backplate"} and render_policy != "native_svg"
    return AssetPolicyDecision(
        asset_id=decision.asset_id,
        role=decision.role,
        render_policy=render_policy,
        background_policy=background_policy,
        confidence=confidence,
        should_run_rmbg=should_run_rmbg,
        reason_codes=tuple(dict.fromkeys(reasons)),
        metrics=decision.metrics,
        split_policy=split_policy,
        components=component_tuple,
    )


def _is_safe_compound_split(
    decision: AssetPolicyDecision,
    components: Sequence[AssetComponent],
) -> bool:
    kinds = {component.kind for component in components}
    has_geometry = "svg_geometry" in kinds
    has_text = "svg_text" in kinds
    has_raster_symbol = "raster_symbol_transparent" in kinds
    if not has_geometry:
        return False
    if _has_internal_label_text(components):
        return False
    if decision.metrics.local_entropy >= 4.0 and decision.metrics.texture_score >= 0.72:
        return False
    if has_text and has_raster_symbol:
        return True
    if has_text and _has_structural_text(components) and decision.metrics.local_entropy < 3.35:
        return True
    if has_raster_symbol and decision.metrics.backplate_score >= 0.72 and decision.metrics.local_entropy < 3.35:
        return True
    return False


def _has_structural_text(components: Sequence[AssetComponent]) -> bool:
    text_values = [component.text.strip() for component in components if component.kind == "svg_text" and component.text]
    if not text_values:
        return False
    if len(text_values) == 1:
        text = text_values[0]
        if len(text) <= 5:
            return True
        if any(char in text for char in "_{}+-=()[]"):
            return True
    return all(text.isdigit() and len(text) <= 2 for text in text_values)


def _has_internal_label_text(components: Sequence[AssetComponent]) -> bool:
    text_values = [component.text.strip() for component in components if component.kind == "svg_text" and component.text]
    if len(text_values) < 2:
        return False
    long_alpha_words = [
        text
        for text in text_values
        if text.replace(" ", "").isalpha() and len(text.replace(" ", "")) >= 4
    ]
    return len(long_alpha_words) >= 2


def _looks_like_noise_texture(metrics: AssetCropMetrics) -> bool:
    return (
        metrics.connected_component_count >= 16
        and metrics.foreground_ratio <= 0.18
        and metrics.warm_saturated_ratio < 0.08
        and metrics.edge_density <= 0.12
    )


def _should_preserve_raster_icon_background(metrics: AssetCropMetrics, reason_codes: Sequence[str]) -> bool:
    if "foreground_background_coupled" in reason_codes or "background_context_may_matter" in reason_codes:
        return True
    min_dim = min(metrics.crop_width, metrics.crop_height)
    if min_dim < 96:
        return False
    return (
        metrics.texture_score >= 0.62
        or (metrics.local_entropy >= 3.65 and metrics.color_complexity >= 0.58)
        or (
            metrics.largest_component_ratio >= 0.80
            and metrics.foreground_ratio >= 0.36
            and metrics.color_complexity >= 0.45
        )
    )


def _picture_should_cutout(metrics: AssetCropMetrics) -> bool:
    return (
        metrics.near_white_border_ratio >= 0.60
        and metrics.light_neutral_border_ratio >= 0.70
        and metrics.edge_density >= 0.16
        and metrics.connected_component_count <= 3
    )


def _decision(
    asset_id: str,
    role: str,
    render_policy: RenderPolicy,
    background_policy: BackgroundPolicy,
    confidence: Confidence,
    metrics: AssetCropMetrics,
    reason_codes: list[str],
) -> AssetPolicyDecision:
    should_run_rmbg = background_policy in {"transparent_subject", "split_backplate"} and render_policy != "native_svg"
    return AssetPolicyDecision(
        asset_id=asset_id,
        role=role,
        render_policy=render_policy,
        background_policy=background_policy,
        confidence=confidence,
        should_run_rmbg=should_run_rmbg,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        metrics=metrics,
    )


def _text_components_from_ocr(
    *,
    asset_box: Mapping[str, Any] | None,
    ocr_boxes: Sequence[Mapping[str, Any]],
    crop_size: tuple[int, int],
) -> list[AssetComponent]:
    asset_bbox = _parse_bbox_tuple(asset_box.get("bbox") if isinstance(asset_box, Mapping) else None)
    if asset_bbox is None:
        return []
    crop_width, crop_height = crop_size
    asset_area = _bbox_area_tuple(asset_bbox)
    components: list[AssetComponent] = []
    for ocr in ocr_boxes:
        ocr_bbox = _parse_bbox_tuple(ocr.get("bbox") if isinstance(ocr, Mapping) else None)
        if ocr_bbox is None:
            continue
        intersection = _bbox_intersection(asset_bbox, ocr_bbox)
        if intersection is None:
            continue
        ocr_area = _bbox_area_tuple(ocr_bbox)
        inter_area = _bbox_area_tuple(intersection)
        if ocr_area <= 0 or asset_area <= 0:
            continue
        if inter_area / ocr_area < 0.38 or inter_area / asset_area > 0.80:
            continue
        try:
            ocr_confidence = float(ocr.get("confidence", 0.0))
        except (TypeError, ValueError):
            ocr_confidence = 0.0
        text = str(ocr.get("text") or "").strip()
        if not text or ocr_confidence < 0.50:
            continue
        relative = (
            max(0, min(crop_width, round(intersection[0] - asset_bbox[0]))),
            max(0, min(crop_height, round(intersection[1] - asset_bbox[1]))),
            max(0, min(crop_width, round(intersection[2] - asset_bbox[0]))),
            max(0, min(crop_height, round(intersection[3] - asset_bbox[1]))),
        )
        if relative[2] - relative[0] < 5 or relative[3] - relative[1] < 5:
            continue
        components.append(
            AssetComponent(
                kind="svg_text",
                bbox=relative,
                confidence="high" if ocr_confidence >= 0.85 else "medium",
                source="ocr_overlap",
                reason_codes=("ocr_text_inside_asset",),
                text=text,
            )
        )
    return _dedupe_text_components(components)


def _warm_symbol_components(
    *,
    image: Image.Image,
    text_components: Sequence[AssetComponent],
) -> list[AssetComponent]:
    rgb = image.convert("RGB")
    arr = np.asarray(rgb, dtype=np.float32)
    mask = _warm_saturated_mask(arr)
    mask = _dilate(_remove_tiny_boolean_noise(mask))
    boxes = _mask_component_bboxes(mask)
    image_area = max(1, image.width * image.height)
    components: list[AssetComponent] = []
    for bbox, area in boxes:
        area_ratio = area / image_area
        if area_ratio < 0.008 or area_ratio > 0.52:
            continue
        if any(_bbox_iou(bbox, component.bbox) > 0.25 for component in text_components):
            continue
        components.append(
            AssetComponent(
                kind="raster_symbol_transparent",
                bbox=bbox,
                confidence="medium",
                source="warm_saturated_component",
                reason_codes=("warm_saturated_local_component",),
            )
        )
    if not components:
        warm_ratio = float(np.mean(mask)) if mask.size else 0.0
        if warm_ratio >= 0.20:
            components.append(
                AssetComponent(
                    kind="raster_symbol_transparent",
                    bbox=(0, 0, image.width, image.height),
                    confidence="medium",
                    source="warm_saturated_whole_symbol",
                    reason_codes=("warm_saturated_whole_asset",),
                )
            )
    return components[:2]


def _has_geometry_residual(
    decision: AssetPolicyDecision,
    text_components: Sequence[AssetComponent],
    raster_symbols: Sequence[AssetComponent],
) -> bool:
    if decision.metrics.backplate_score >= 0.58:
        return True
    if text_components and decision.metrics.simple_geometry_score >= 0.20:
        return True
    component_area = sum(_bbox_area_tuple(component.bbox) for component in (*text_components, *raster_symbols))
    crop_area = max(1, decision.metrics.crop_width * decision.metrics.crop_height)
    return component_area / crop_area <= 0.62


def _resize_for_metrics(image: Image.Image, *, max_metric_edge: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_metric_edge:
        return image
    scale = max_metric_edge / float(longest)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.BICUBIC)


def _border_mask(height: int, width: int, margin: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    mask[:margin, :] = True
    mask[-margin:, :] = True
    mask[:, :margin] = True
    mask[:, -margin:] = True
    return mask


def _border_uniformity(border_pixels: np.ndarray) -> float:
    if border_pixels.size == 0:
        return 0.0
    channel_std = float(np.mean(np.std(border_pixels, axis=0)))
    return _clamp01(1.0 - channel_std / 82.0)


def _near_white_ratio(pixels: np.ndarray) -> float:
    if pixels.size == 0:
        return 0.0
    channel_min = np.min(pixels, axis=1)
    channel_span = np.max(pixels, axis=1) - channel_min
    return float(np.mean((channel_min >= 218.0) & (channel_span <= 34.0)))


def _light_neutral_ratio(pixels: np.ndarray) -> float:
    if pixels.size == 0:
        return 0.0
    channel_min = np.min(pixels, axis=1)
    channel_span = np.max(pixels, axis=1) - channel_min
    return float(np.mean((channel_min >= 185.0) & (channel_span <= 58.0)))


def _warm_saturated_ratio(arr: np.ndarray) -> float:
    if arr.size == 0:
        return 0.0
    return float(np.mean(_warm_saturated_mask(arr)))


def _warm_saturated_mask(arr: np.ndarray) -> np.ndarray:
    if arr.size == 0:
        return np.zeros(arr.shape[:2], dtype=bool)
    red = arr[:, :, 0]
    green = arr[:, :, 1]
    blue = arr[:, :, 2]
    return (
        (red >= 150.0)
        & (green >= 40.0)
        & (red >= green + 20.0)
        & (green >= blue + 18.0)
        & ((red - blue) >= 70.0)
    )


def _edge_density(arr: np.ndarray) -> float:
    gray = _gray(arr)
    dx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    dy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    grad = dx + dy
    return float(np.mean(grad > 32.0))


def _thin_line_score(mask: np.ndarray) -> float:
    fg_count = int(np.sum(mask))
    if fg_count == 0:
        return 0.0
    eroded = _erode(mask)
    interior_ratio = float(np.sum(eroded)) / float(fg_count)
    return _clamp01(1.0 - interior_ratio)


def _color_complexity(arr: np.ndarray, foreground: np.ndarray) -> float:
    pixels = arr[foreground]
    if len(pixels) < 8:
        pixels = arr.reshape(-1, 3)
    if len(pixels) == 0:
        return 0.0
    if len(pixels) > 8000:
        step = max(1, len(pixels) // 8000)
        pixels = pixels[::step]
    quantized = np.clip((pixels // 24).astype(np.int16), 0, 10)
    packed = quantized[:, 0] * 121 + quantized[:, 1] * 11 + quantized[:, 2]
    unique_count = len(np.unique(packed))
    return _clamp01(unique_count / 72.0)


def _local_entropy(arr: np.ndarray) -> float:
    gray = _gray(arr).astype(np.uint8)
    hist = np.bincount((gray // 8).reshape(-1), minlength=32).astype(np.float64)
    total = float(np.sum(hist))
    if total <= 0:
        return 0.0
    probabilities = hist[hist > 0] / total
    return float(-np.sum(probabilities * np.log2(probabilities)))


def _texture_score(
    *,
    color_complexity: float,
    local_entropy: float,
    foreground_ratio: float,
    edge_density: float,
) -> float:
    entropy_norm = _clamp01(local_entropy / 5.0)
    fill_norm = _clamp01((foreground_ratio - 0.28) / 0.42)
    edge_norm = _clamp01(edge_density / 0.28)
    return _clamp01(color_complexity * 0.58 + entropy_norm * 0.27 + fill_norm * 0.10 + edge_norm * 0.05)


def _simple_geometry_score(
    *,
    thin_line_score: float,
    color_complexity: float,
    texture_score: float,
    foreground_ratio: float,
    component_count: int,
    edge_density: float,
) -> float:
    component_penalty = _clamp01(max(0, component_count - 8) / 24.0)
    fill_penalty = _clamp01(max(0.0, foreground_ratio - 0.24) / 0.32)
    edge_penalty = _clamp01(max(0.0, edge_density - 0.18) / 0.24)
    score = (
        thin_line_score * 0.36
        + (1.0 - color_complexity) * 0.24
        + (1.0 - texture_score) * 0.22
        + (1.0 - component_penalty) * 0.10
        + (1.0 - fill_penalty) * 0.05
        + (1.0 - edge_penalty) * 0.03
    )
    return _clamp01(score)


def _backplate_score(
    *,
    foreground: np.ndarray,
    border_foreground_ratio: float,
    touches_sides: int,
    foreground_ratio: float,
) -> float:
    if foreground.size == 0:
        return 0.0
    touch_score = touches_sides / 4.0
    border_score = _clamp01(border_foreground_ratio / 0.30)
    fill_score = _clamp01((foreground_ratio - 0.08) / 0.26)
    return _clamp01(touch_score * 0.48 + border_score * 0.32 + fill_score * 0.20)


def _component_metrics(mask: np.ndarray) -> tuple[int, float]:
    if not np.any(mask):
        return 0, 0.0
    work = _dilate(mask)
    height, width = work.shape
    seen = np.zeros_like(work, dtype=bool)
    component_count = 0
    largest = 0
    for y in range(height):
        for x in range(width):
            if seen[y, x] or not work[y, x]:
                continue
            size = _flood_fill_size(work, seen, y, x)
            if size >= 4:
                component_count += 1
                largest = max(largest, size)
    total = int(np.sum(work))
    largest_ratio = float(largest) / float(total) if total else 0.0
    return component_count, largest_ratio


def _mask_component_bboxes(mask: np.ndarray) -> list[tuple[tuple[int, int, int, int], int]]:
    if not np.any(mask):
        return []
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    components: list[tuple[tuple[int, int, int, int], int]] = []
    for y in range(height):
        for x in range(width):
            if seen[y, x] or not mask[y, x]:
                continue
            bbox, size = _flood_fill_bbox(mask, seen, y, x)
            if size >= 6:
                components.append((bbox, size))
    components.sort(key=lambda item: item[1], reverse=True)
    return components


def _flood_fill_bbox(
    mask: np.ndarray,
    seen: np.ndarray,
    start_y: int,
    start_x: int,
) -> tuple[tuple[int, int, int, int], int]:
    height, width = mask.shape
    stack = [(start_y, start_x)]
    seen[start_y, start_x] = True
    size = 0
    min_x = max_x = start_x
    min_y = max_y = start_y
    while stack:
        y, x = stack.pop()
        size += 1
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
        for ny in range(max(0, y - 1), min(height, y + 2)):
            for nx in range(max(0, x - 1), min(width, x + 2)):
                if seen[ny, nx] or not mask[ny, nx]:
                    continue
                seen[ny, nx] = True
                stack.append((ny, nx))
    return (min_x, min_y, min(width, max_x + 1), min(height, max_y + 1)), size


def _flood_fill_size(mask: np.ndarray, seen: np.ndarray, start_y: int, start_x: int) -> int:
    height, width = mask.shape
    stack = [(start_y, start_x)]
    seen[start_y, start_x] = True
    size = 0
    while stack:
        y, x = stack.pop()
        size += 1
        for ny in range(max(0, y - 1), min(height, y + 2)):
            for nx in range(max(0, x - 1), min(width, x + 2)):
                if seen[ny, nx] or not mask[ny, nx]:
                    continue
                seen[ny, nx] = True
                stack.append((ny, nx))
    return size


def _foreground_touches_sides(mask: np.ndarray, *, margin: int) -> int:
    if mask.size == 0:
        return 0
    top = float(np.mean(mask[:margin, :]))
    bottom = float(np.mean(mask[-margin:, :]))
    left = float(np.mean(mask[:, :margin]))
    right = float(np.mean(mask[:, -margin:]))
    return sum(value >= 0.035 for value in (top, bottom, left, right))


def _remove_tiny_boolean_noise(mask: np.ndarray) -> np.ndarray:
    if mask.size == 0:
        return mask
    neighbors = _neighbor_count(mask)
    return mask & (neighbors >= 2)


def _neighbor_count(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask.astype(np.uint8), 1, mode="constant")
    total = np.zeros(mask.shape, dtype=np.uint8)
    for dy in range(3):
        for dx in range(3):
            if dy == 1 and dx == 1:
                continue
            total += padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
    return total


def _erode(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    result = np.ones(mask.shape, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            result &= padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
    return result


def _dilate(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    result = np.zeros(mask.shape, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            result |= padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
    return result


def _gray(arr: np.ndarray) -> np.ndarray:
    return arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114


def _box_area_ratio(
    box: Mapping[str, Any] | None,
    slide_size: tuple[int | float, int | float] | None,
) -> float:
    if not isinstance(box, Mapping) or slide_size is None:
        return 0.0
    bbox = box.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return 0.0
    try:
        x1, y1, x2, y2 = [float(value) for value in bbox]
        width, height = float(slide_size[0]), float(slide_size[1])
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0
    if width <= 0 or height <= 0:
        return 0.0
    area = abs(x2 - x1) * abs(y2 - y1)
    return _clamp01(area / (width * height))


def _parse_bbox_tuple(raw_bbox: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(value) for value in raw_bbox]
    except (TypeError, ValueError):
        return None
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


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


def _bbox_area_tuple(bbox: tuple[int | float, int | float, int | float, int | float]) -> float:
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))


def _bbox_iou(
    a: tuple[int | float, int | float, int | float, int | float],
    b: tuple[int | float, int | float, int | float, int | float],
) -> float:
    intersection = _bbox_intersection(
        (float(a[0]), float(a[1]), float(a[2]), float(a[3])),
        (float(b[0]), float(b[1]), float(b[2]), float(b[3])),
    )
    if intersection is None:
        return 0.0
    inter_area = _bbox_area_tuple(intersection)
    union = _bbox_area_tuple(a) + _bbox_area_tuple(b) - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def _dedupe_text_components(components: Sequence[AssetComponent]) -> list[AssetComponent]:
    kept: list[AssetComponent] = []
    for component in sorted(components, key=lambda item: _bbox_area_tuple(item.bbox), reverse=True):
        if any(_bbox_iou(component.bbox, existing.bbox) > 0.55 for existing in kept):
            continue
        kept.append(component)
    kept.sort(key=lambda item: (item.bbox[1], item.bbox[0]))
    return kept


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
