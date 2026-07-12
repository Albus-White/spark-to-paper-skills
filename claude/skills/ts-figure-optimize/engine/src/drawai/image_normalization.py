from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageColor, ImageOps

from .artifacts import DrawAiArtifactPaths, write_json
from .config import DrawAiInputConfig, InputNormalizationConfig


@dataclass(frozen=True)
class InputNormalizationResult:
    original_size: tuple[int, int]
    normalized_size: tuple[int, int]
    scale: float
    upscaled: bool
    figure_image: Path
    original_image: Path
    source_metadata: Path


def normalize_input_image(
    input_config: DrawAiInputConfig,
    artifact_paths: DrawAiArtifactPaths,
) -> InputNormalizationResult:
    normalization = input_config.normalization
    source_path = input_config.image
    source_sha256 = _sha256_file(source_path)

    with Image.open(source_path) as image:
        transposed = ImageOps.exif_transpose(image)
        source_had_alpha = _has_alpha(transposed)
        original_rgb = _to_rgb(
            transposed,
            normalization.flatten_transparency_background,
            source_had_alpha,
        )

    original_size = original_rgb.size
    original_rgb.save(artifact_paths.original_image)

    figure_rgb, scale, upscaled = _resize_for_figure(original_rgb, normalization)
    normalized_size = figure_rgb.size
    figure_rgb.save(artifact_paths.figure_image)

    metadata = {
        "source_path": str(source_path),
        "sha256": source_sha256,
        "original_size": list(original_size),
        "normalized_size": list(normalized_size),
        "scale": scale,
        "upscaled": upscaled,
        "normalization_enabled": normalization.enabled,
        "upscale_only": normalization.upscale_only,
        "target_long_edge": normalization.target_long_edge,
        "coordinate_system": "figure_image_pixels",
        "input_had_alpha": source_had_alpha,
        "flattened_transparency": source_had_alpha,
        "flatten_transparency_background": normalization.flatten_transparency_background,
        "original_image": str(artifact_paths.original_image),
        "figure_image": str(artifact_paths.figure_image),
    }
    write_json(artifact_paths.source_metadata, metadata)

    return InputNormalizationResult(
        original_size=original_size,
        normalized_size=normalized_size,
        scale=scale,
        upscaled=upscaled,
        figure_image=artifact_paths.figure_image,
        original_image=artifact_paths.original_image,
        source_metadata=artifact_paths.source_metadata,
    )


def _resize_for_figure(
    image: Image.Image,
    normalization: InputNormalizationConfig,
) -> tuple[Image.Image, float, bool]:
    if not normalization.enabled:
        return image.copy(), 1.0, False

    width, height = image.size
    long_edge = max(width, height)
    target_long_edge = normalization.target_long_edge
    should_resize = long_edge < target_long_edge or (
        long_edge > target_long_edge and not normalization.upscale_only
    )
    if not should_resize:
        return image.copy(), 1.0, False

    scale = target_long_edge / long_edge
    if width >= height:
        resized_size = (target_long_edge, max(1, round(height * scale)))
    else:
        resized_size = (max(1, round(width * scale)), target_long_edge)
    resized = image.resize(resized_size, Image.Resampling.LANCZOS)
    return resized, scale, scale > 1.0


def _to_rgb(
    image: Image.Image,
    flatten_transparency_background: str,
    source_had_alpha: bool,
) -> Image.Image:
    if not source_had_alpha:
        return image.convert("RGB")

    background_rgb = _parse_rgb(flatten_transparency_background)
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (*background_rgb, 255))
    return Image.alpha_composite(background, rgba).convert("RGB")


def _has_alpha(image: Image.Image) -> bool:
    if "transparency" in image.info:
        return True
    if image.mode in {"RGBA", "LA"}:
        return True
    return False


def _parse_rgb(raw: str) -> tuple[int, int, int]:
    try:
        color = ImageColor.getrgb(raw)
    except ValueError as exc:
        raise ValueError(
            f"input.normalization.flatten_transparency_background is not a valid color: {raw!r}"
        ) from exc
    return color[:3]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
