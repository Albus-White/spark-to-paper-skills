from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from drawai.core import ArtifactStore

from .schema import (
    ASSET_PACKAGE_SCHEMA,
    ELEMENT_PLAN_SCHEMA,
    RUN_PACKAGE_SCHEMA,
    AssetPackage,
    ElementPlan,
    RunPackage,
    validate_asset_package,
    validate_asset_package_payload,
    validate_element_plan,
    validate_run_package,
    validate_run_package_payload,
)
from .registry import default_registry


@dataclass(frozen=True)
class RunClassification:
    mode: str
    root: Path
    can_fork_from_source: bool


def element_dir(root: str | Path, element_id: str) -> Path:
    safe_element_id = _safe_element_id(element_id)
    elements_dir = _resolve_run_relative(root, "elements")
    return _resolve_element_relative(elements_dir, safe_element_id)


def write_run_package(root: str | Path, package: RunPackage) -> RunPackage:
    root_path = Path(root).expanduser().resolve()
    store = ArtifactStore(root_path)
    normalized = replace(package, root=root_path)
    validate_run_package(normalized)
    store.write_json(
        "run_package",
        "drawai_package.json",
        normalized.to_dict(),
        schema=RUN_PACKAGE_SCHEMA,
    )
    return normalized


def read_run_package(root: str | Path) -> dict[str, Any]:
    package_path = _resolve_run_relative(root, "drawai_package.json")
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("run package must be a JSON object")
    validate_run_package_payload(payload)
    return payload


def write_element_plan(root: str | Path, plan: ElementPlan) -> ElementPlan:
    safe_element_id = _safe_element_id(plan.element_id)
    validate_element_plan(plan, registry=default_registry())
    store = ArtifactStore(root)
    store.write_json(
        f"element_plan:{safe_element_id}",
        Path("elements") / safe_element_id / "element.json",
        plan.to_dict(),
        schema=ELEMENT_PLAN_SCHEMA,
    )
    return plan


def write_asset_package(root: str | Path, package: AssetPackage) -> AssetPackage:
    safe_element_id = _safe_element_id(package.element_id)
    validate_asset_package(package)
    store = ArtifactStore(root)
    store.write_json(
        f"asset_package:{package.asset_id}",
        Path("elements") / safe_element_id / "asset_package.json",
        package.to_dict(),
        schema=ASSET_PACKAGE_SCHEMA,
    )
    return package


def read_asset_package(root: str | Path, element_id: str) -> dict[str, Any]:
    safe_element_id = _safe_element_id(element_id)
    package_path = _resolve_run_relative(
        root,
        Path("elements") / safe_element_id / "asset_package.json",
    )
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("asset package must be a JSON object")
    validate_asset_package_payload(payload)
    return payload


def classify_run_root(root: str | Path) -> RunClassification:
    root_path = Path(root).expanduser().resolve()
    package_path = root_path / "drawai_package.json"
    can_fork_from_source = _has_source_image(root_path)

    if package_path.exists():
        payload = json.loads(package_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("schema") == RUN_PACKAGE_SCHEMA:
            try:
                validate_run_package_payload(payload)
            except ValueError:
                return RunClassification(
                    mode="unknown",
                    root=root_path,
                    can_fork_from_source=can_fork_from_source,
                )
            return RunClassification(
                mode="v2",
                root=root_path,
                can_fork_from_source=can_fork_from_source,
            )
        return RunClassification(
            mode="unknown",
            root=root_path,
            can_fork_from_source=can_fork_from_source,
        )

    if _has_legacy_outputs(root_path):
        return RunClassification(
            mode="legacy_readonly",
            root=root_path,
            can_fork_from_source=can_fork_from_source,
        )

    return RunClassification(
        mode="unknown",
        root=root_path,
        can_fork_from_source=can_fork_from_source,
    )


def _resolve_run_relative(root: str | Path, relative_path: str | Path) -> Path:
    root_path = Path(root).expanduser().resolve()
    candidate = root_path / relative_path
    resolved = candidate.expanduser().resolve()
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"v2 package path is outside run root: {relative_path}") from exc
    return resolved


def _resolve_element_relative(elements_dir: Path, element_id: str) -> Path:
    resolved = (elements_dir / element_id).resolve()
    try:
        resolved.relative_to(elements_dir)
    except ValueError as exc:
        raise ValueError(f"element_id resolves outside elements directory: {element_id}") from exc
    return resolved


def _safe_element_id(element_id: str) -> str:
    if not isinstance(element_id, str) or not element_id:
        raise ValueError("element_id is required")
    path = Path(element_id)
    if (
        path.is_absolute()
        or element_id in {".", ".."}
        or "/" in element_id
        or "\\" in element_id
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"element_id must be a safe single path segment: {element_id}")
    return element_id


def _has_source_image(root: Path) -> bool:
    return (root / "inputs" / "figure.png").exists() or (
        root / "inputs" / "original.png"
    ).exists()


def _has_legacy_outputs(root: Path) -> bool:
    return any(
        path.exists()
        for path in (
            root / "svg" / "semantic.svg",
            root / "box_ir" / "box_ir.json",
            root / "reports" / "pipeline_summary.json",
        )
    )
