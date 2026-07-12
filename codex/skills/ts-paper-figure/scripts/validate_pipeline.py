#!/usr/bin/env python3
"""Validate adaptive figure provenance and actual-image review artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_json(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"missing {path.relative_to(path.parent.parent) if len(path.parents) > 1 else path.name}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"unreadable {path.name}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.name} root must be an object")
        return {}
    return value


def resolve(root: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else root / path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def readable_image(path: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def validate_pipeline(root: Path, **_: Any) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    contract = read_json(root / "figure_contract.json", errors)
    required_contract = [
        "figure_id", "semantic_type", "source_of_truth", "renderer", "renderer_rationale",
        "caption", "required_content", "forbidden_content",
    ]
    missing = [key for key in required_contract if key not in contract or contract[key] in (None, "", [])]
    if missing:
        errors.append(f"figure_contract missing fields: {missing}")
    for artifact in contract.get("data_sources", []):
        if not resolve(root, artifact).is_file():
            errors.append(f"figure data source missing: {artifact}")
    if contract.get("source_of_truth") == "measured_data" and not contract.get("fact_ids"):
        errors.append("measured-data figure requires fact_ids")

    plan = read_json(root / "search_plan.json", errors)
    if plan.get("strategy") not in {"direct", "candidate_search"}:
        errors.append("search_plan.strategy must be direct or candidate_search")
    planned = plan.get("planned_candidates")
    safety_cap = plan.get("safety_cap")
    if not isinstance(planned, int) or planned < 1:
        errors.append("search_plan.planned_candidates must be a positive integer")
        planned = 1
    if not isinstance(safety_cap, int) or safety_cap < planned:
        errors.append("search_plan.safety_cap must be an integer no smaller than planned_candidates")
    elif safety_cap > 10_000:
        errors.append("search_plan.safety_cap exceeds the executor runaway-protection ceiling")
    for key in ("rationale", "resource_basis", "stop_conditions"):
        if not plan.get(key):
            errors.append(f"search_plan.{key} is required")
    reference_strategy = plan.get("reference_strategy") or {}
    references: list[dict] = []
    if reference_strategy.get("required") is True:
        retrieval = read_json(root / "references" / "retrieval.json", errors)
        references = retrieval.get("references", []) if isinstance(retrieval.get("references"), list) else []
        if not references:
            errors.append("reference_strategy requires at least one real reference")
        for index, reference in enumerate(references):
            image = resolve(root, reference.get("image")) if isinstance(reference, dict) else root / ""
            if not image.is_file() or not readable_image(image):
                errors.append(f"reference {index} image is missing or unreadable")
            if not isinstance(reference, dict) or not reference.get("source") or not reference.get("reason_selected"):
                errors.append(f"reference {index} lacks source/reason_selected")
    elif not reference_strategy.get("rationale"):
        errors.append("search_plan.reference_strategy requires a rationale whether references are used or not")

    renders = read_json(root / "renders" / "render_manifest.json", errors)
    results = renders.get("results", []) if isinstance(renders.get("results"), list) else []
    successful: dict[str, dict] = {}
    for index, item in enumerate(results):
        if not isinstance(item, dict) or item.get("ok") is not True:
            continue
        candidate_id = str(item.get("id") or "")
        if not candidate_id or candidate_id in successful:
            errors.append(f"render {index} has missing/duplicate id")
            continue
        output = resolve(root, item.get("output"))
        if not output.is_file() or not readable_image(output):
            errors.append(f"render {candidate_id} output is missing or unreadable")
            continue
        if item.get("sha256") != sha256(output):
            errors.append(f"render {candidate_id} hash mismatch")
        successful[candidate_id] = item
    if len(successful) < planned:
        errors.append(f"search plan requested {planned} candidates but only {len(successful)} succeeded")

    selection = read_json(root / "selection.json", errors)
    selected_id = str(selection.get("selected_candidate_id") or "")
    if selected_id not in successful:
        errors.append("selection does not identify a successful render")
    if not selection.get("rationale"):
        errors.append("selection.rationale is required")
    if len(successful) > 1 and not selection.get("compared_candidates"):
        errors.append("multi-candidate selection requires compared_candidates")
    final_image = resolve(root, selection.get("final_image"))
    if not final_image.is_file() or not readable_image(final_image):
        errors.append("selection.final_image is missing or unreadable")
    elif selection.get("final_sha256") != sha256(final_image):
        errors.append("selection.final_sha256 does not match final_image")

    repairs = sorted((root / "repair").glob("round_*.json")) if (root / "repair").is_dir() else []
    for path in repairs:
        repair = read_json(path, errors)
        input_image = resolve(root, repair.get("input_image")); output_image = resolve(root, repair.get("output_image"))
        if not input_image.is_file() or repair.get("input_sha256") != sha256(input_image):
            errors.append(f"{path.name} input is missing or hash-mismatched")
        if repair.get("accepted") is True:
            if not output_image.is_file() or repair.get("output_sha256") != sha256(output_image):
                errors.append(f"{path.name} accepted output is missing or hash-mismatched")
            elif input_image.is_file() and sha256(input_image) == sha256(output_image):
                errors.append(f"{path.name} accepts a byte-identical no-op")
            if not repair.get("observed_changes") or not repair.get("regression_checks"):
                errors.append(f"{path.name} accepted repair lacks observed changes/regression checks")

    review = read_json(root / "critique" / "final_vision_review.json", errors)
    if final_image.is_file() and review.get("artifact_sha256") != sha256(final_image):
        errors.append("final vision review is not hash-bound to final_image")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict) or not reviewer.get("id") or reviewer.get("actual_image_review") is not True:
        errors.append("final vision review requires a reviewer that inspected the actual image")
    checks = review.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("final vision review checks must be a non-empty list")
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, dict) or not all(check.get(key) for key in ("question", "verdict", "rationale")):
                errors.append(f"final vision check {index} is incomplete")
            elif check["verdict"] not in {"PASS", "PASS_WITH_EXPLAINED_DEVIATION", "FAIL"}:
                errors.append(f"final vision check {index} verdict is invalid")
    if review.get("blocking_issues"):
        errors.append("final vision review retains blocking issues")
    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "candidate_count": len(successful),
        "reference_count": len(references),
        "critic_rounds": len(repairs) + 1,
        "accepted_repairs": sum(1 for path in repairs if read_json(path, []).get("accepted") is True),
        "final_image": str(final_image) if final_image.is_file() else "",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pipeline")
    args = parser.parse_args()
    report = validate_pipeline(Path(args.pipeline))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
