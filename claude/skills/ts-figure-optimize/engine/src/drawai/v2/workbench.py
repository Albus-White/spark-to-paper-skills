from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from drawai.artifacts import write_json
from drawai.workbench.models import CaseRecord
from drawai.workbench.store import WorkbenchStore

from .packages import classify_run_root, element_dir, read_asset_package, read_run_package
from .processors import processor_for_type
from .schema import ProcessingIntent
from .stages import _plan_from_payload


class LegacyReadOnlyCaseError(RuntimeError):
    pass


class V2PackageUnavailableError(FileNotFoundError):
    pass


def case_package_payload(case: CaseRecord) -> dict[str, Any]:
    classification = classify_run_root(case.run_root)
    if classification.mode != "v2":
        raise V2PackageUnavailableError("v2 package is not available for this case")
    return {
        "compatibility": {
            "mode": classification.mode,
            "can_fork_from_source": classification.can_fork_from_source,
        },
        "package": read_run_package(case.run_root),
    }


def case_elements_payload(case: CaseRecord) -> dict[str, Any]:
    package_payload = case_package_payload(case)
    elements = package_payload["package"].get("elements", [])
    if not isinstance(elements, list):
        raise ValueError("v2 run package elements must be a list")
    return {
        "compatibility": package_payload["compatibility"],
        "elements": elements,
    }


def case_asset_package_payload(case: CaseRecord, element_id: str) -> dict[str, Any]:
    classification = classify_run_root(case.run_root)
    if classification.mode != "v2":
        raise V2PackageUnavailableError("v2 package is not available for this case")
    return {
        "compatibility": {
            "mode": classification.mode,
            "can_fork_from_source": classification.can_fork_from_source,
        },
        "asset_package": read_asset_package(case.run_root, element_id),
    }


def ensure_v2_mutation_allowed(case: CaseRecord) -> None:
    classification = classify_run_root(case.run_root)
    if classification.mode == "v2":
        return
    if classification.mode == "legacy_readonly":
        raise LegacyReadOnlyCaseError("legacy_readonly_case")
    raise V2PackageUnavailableError("v2 package is not available for this case")


def process_case_asset(
    case: CaseRecord,
    element_id: str,
    processor_type: str,
    *,
    providers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_v2_mutation_allowed(case)
    root = Path(case.run_root).expanduser().resolve()
    element_path = element_dir(root, element_id)
    plan = _plan_from_payload(_read_json(element_path / "element.json"))
    if plan.element_id != element_id:
        raise ValueError(
            f"element plan id {plan.element_id!r} does not match requested element_id {element_id!r}"
        )
    plan = replace(
        plan,
        processing_intent=ProcessingIntent(
            object_type=plan.processing_intent.object_type,
            processing_type=processor_type,
            parameters=dict(plan.processing_intent.parameters),
        ),
    )
    processor = processor_for_type(processor_type, providers or {})
    try:
        package = processor.process(root, plan, source_image_path=_source_image_for_case(case))
    except Exception:
        failed_package_path = element_path / "asset_package.json"
        if failed_package_path.is_file():
            _sync_asset_package_into_run_package(root, _read_json(failed_package_path))
        raise
    payload = package.to_dict()
    _sync_asset_package_into_run_package(root, payload)
    return payload


def activate_case_asset_result(case: CaseRecord, element_id: str, result_id: str) -> dict[str, Any]:
    ensure_v2_mutation_allowed(case)
    root = Path(case.run_root).expanduser().resolve()
    payload = read_asset_package(root, element_id)
    results = payload.get("all_results")
    if not isinstance(results, list):
        raise ValueError("asset package all_results must be a list")
    active_result = next(
        (result for result in results if isinstance(result, Mapping) and result.get("result_id") == result_id),
        None,
    )
    if active_result is None:
        raise ValueError(f"asset result not found: {result_id}")
    payload["active_result"] = dict(active_result)
    payload["status"] = str(active_result.get("status") or payload.get("status") or "ok")
    if payload["status"] == "ok":
        payload["failure"] = None
    write_json(root / "elements" / element_id / "asset_package.json", payload)
    _sync_asset_package_into_run_package(root, payload)
    return payload


def fork_v2_case_from_source(store: WorkbenchStore, runner: Any, case: CaseRecord) -> CaseRecord:
    classification = classify_run_root(case.run_root)
    source_image = _fork_source_image(case)
    if not classification.can_fork_from_source and source_image is None:
        raise V2PackageUnavailableError("case source image is not available for v2 fork")
    new_case = store.create_case(
        batch_id=case.batch_id,
        name=f"{case.name} (v2)",
        source_image_path=source_image or case.source_image_path,
        config_path=case.config_path,
    )
    store.update_case_config_path(new_case.case_id, Path(new_case.run_root) / "drawai.config.yaml")
    new_case = store.get_case(new_case.case_id)
    runner.submit_rerun(new_case.case_id, "analysis")
    return store.get_case(new_case.case_id)


def _sync_asset_package_into_run_package(root: Path, package_payload: Mapping[str, Any]) -> None:
    run_package_path = root / "drawai_package.json"
    run_package = _read_json(run_package_path)
    asset_packages = run_package.get("asset_packages")
    if not isinstance(asset_packages, list):
        asset_packages = []
    package_element_id = package_payload.get("element_id")
    package_asset_id = package_payload.get("asset_id")
    updated: list[Any] = []
    replaced_existing = False
    for item in asset_packages:
        if (
            isinstance(item, Mapping)
            and (item.get("element_id") == package_element_id or item.get("asset_id") == package_asset_id)
        ):
            updated.append(dict(package_payload))
            replaced_existing = True
        else:
            updated.append(item)
    if not replaced_existing:
        updated.append(dict(package_payload))
    run_package["asset_packages"] = updated
    run_package.pop("compose_outputs", None)
    run_package.pop("export_outputs", None)
    write_json(run_package_path, run_package)


def _source_image_for_case(case: CaseRecord) -> Path:
    root = Path(case.run_root).expanduser().resolve()
    run_package = _read_json(root / "drawai_package.json")
    raw_source = run_package.get("source_image")
    if isinstance(raw_source, str) and raw_source:
        source = Path(raw_source)
        return source if source.is_absolute() else root / source
    return _fork_source_image(case) or Path(case.source_image_path).expanduser().resolve(strict=False)


def _fork_source_image(case: CaseRecord) -> Path | None:
    candidates = (
        Path(case.source_image_path).expanduser().resolve(strict=False),
        Path(case.run_root) / "inputs" / "figure.png",
        Path(case.run_root) / "inputs" / "original.png",
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload
