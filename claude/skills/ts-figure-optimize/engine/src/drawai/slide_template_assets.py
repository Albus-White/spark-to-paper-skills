from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping


SLIDE_TEMPLATE_ASSET_SCHEMA = "drawai.slide_template_asset.v1"
DEFAULT_TEMPLATE_ASSET_ROOT = Path(__file__).resolve().parents[2] / "templates" / "slide_image"


class SlideTemplateAssetError(ValueError):
    """Raised when a slide template asset manifest is missing or invalid."""


def list_slide_template_assets(root: str | Path | None = None) -> list[dict[str, Any]]:
    asset_root = _asset_root(root)
    if not asset_root.is_dir():
        return []
    assets = [
        load_slide_template_asset(path.parent.name, root=asset_root)
        for path in sorted(asset_root.glob("*/template.json"))
    ]
    return assets


def load_slide_template_asset(template_id: str, *, root: str | Path | None = None) -> dict[str, Any]:
    clean_id = str(template_id or "").strip()
    if not clean_id:
        raise SlideTemplateAssetError("template_id is required")
    manifest_path = _asset_root(root) / clean_id / "template.json"
    if not manifest_path.is_file():
        raise SlideTemplateAssetError(f"slide template asset does not exist: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SlideTemplateAssetError(f"slide template asset is not valid JSON: {manifest_path}") from exc
    if not isinstance(payload, Mapping):
        raise SlideTemplateAssetError(f"slide template asset must be a JSON object: {manifest_path}")
    asset = dict(payload)
    _validate_asset(asset, manifest_path=manifest_path)
    asset["manifest_path"] = str(manifest_path)
    asset["asset_dir"] = str(manifest_path.parent)
    return deepcopy(asset)


def template_asset_summary(root: str | Path | None = None) -> list[dict[str, Any]]:
    return [
        {
            "id": asset["id"],
            "name": asset["name"],
            "category": asset.get("category", ""),
            "page_types": [page.get("id", "") for page in asset.get("page_types", [])],
            "reference_image_count": len(asset.get("reference_images", [])),
            "sample_output_count": len(asset.get("sample_outputs", [])),
            "manifest_path": asset["manifest_path"],
        }
        for asset in list_slide_template_assets(root=root)
    ]


def _validate_asset(asset: dict[str, Any], *, manifest_path: Path) -> None:
    required_string_fields = ("schema", "id", "name", "category")
    for key in required_string_fields:
        if not isinstance(asset.get(key), str) or not asset[key].strip():
            raise SlideTemplateAssetError(f"{manifest_path}: {key} must be a non-empty string")
    if asset["schema"] != SLIDE_TEMPLATE_ASSET_SCHEMA:
        raise SlideTemplateAssetError(f"{manifest_path}: schema must be {SLIDE_TEMPLATE_ASSET_SCHEMA}")
    for key in ("design_tokens", "slot_schema", "prompt_recipe", "layout"):
        if not isinstance(asset.get(key), Mapping):
            raise SlideTemplateAssetError(f"{manifest_path}: {key} must be an object")
    for key in ("page_types", "reference_images", "sample_outputs"):
        if not isinstance(asset.get(key), list):
            raise SlideTemplateAssetError(f"{manifest_path}: {key} must be an array")


def _asset_root(root: str | Path | None) -> Path:
    return Path(root).expanduser().resolve(strict=False) if root is not None else DEFAULT_TEMPLATE_ASSET_ROOT


__all__ = [
    "DEFAULT_TEMPLATE_ASSET_ROOT",
    "SLIDE_TEMPLATE_ASSET_SCHEMA",
    "SlideTemplateAssetError",
    "list_slide_template_assets",
    "load_slide_template_asset",
    "template_asset_summary",
]
