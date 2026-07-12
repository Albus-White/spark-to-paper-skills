from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

from .asset_manifest_utils import manifest_image_paths


def is_data_uri(ref: str) -> bool:
    return str(ref or "").lower().startswith("data:")


def is_external_or_absolute_ref(ref: str) -> bool:
    ref_text = str(ref or "")
    lower_ref = ref_text.lower()
    if lower_ref.startswith(("http://", "https://", "file://", "//")):
        return True
    if ref_text.startswith("/") or ref_text.startswith("\\\\"):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", ref_text):
        return True
    parsed = urlparse(ref_text)
    return bool(parsed.scheme and parsed.scheme.lower() != "data")


def resolve_local_ref(ref: str, svg_dir: Path) -> Path | None:
    parsed = urlparse(str(ref or ""))
    if parsed.scheme or parsed.netloc:
        return None
    raw_path = unquote(parsed.path)
    if not raw_path:
        return None
    return (Path(svg_dir) / raw_path).expanduser().resolve(strict=False)


def manifest_asset_paths(asset_manifest: Mapping[str, Any] | list[Any] | None, svg_dir: Path) -> set[Path]:
    return manifest_image_paths(asset_manifest, svg_dir)
