#!/usr/bin/env python3
"""Validate adaptive figure provenance and actual-image review artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from paperbanana_quality import validate as validate_paperbanana_quality


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
        "figure_id", "figure_class", "route", "drawai_status", "semantic_type", "source_of_truth", "renderer", "renderer_rationale",
        "caption", "required_content", "forbidden_content",
    ]
    missing = [key for key in required_contract if key not in contract or contract[key] in (None, "", [])]
    if missing:
        errors.append(f"figure_contract missing fields: {missing}")
    for artifact in contract.get("data_sources", []):
        if not resolve(root, artifact).is_file():
            errors.append(f"figure data source missing: {artifact}")
    figure_class = contract.get("figure_class")
    route = contract.get("route")
    if figure_class == "explanatory_synthesis":
        if route != "PAPERBANANA_REQUIRED":
            errors.append("explanatory synthesis figures require PAPERBANANA_REQUIRED")
        if contract.get("drawai_status") not in {"AVAILABLE_REQUIRED", "UNAVAILABLE_EVIDENCED_SKIP"}:
            errors.append("PaperBanana figures require an explicit DrawAI preflight status")
        if contract.get("renderer") != "paperbanana":
            errors.append("PaperBanana figures must declare renderer=paperbanana")
    else:
        errors.append("PaperBanana pipeline accepts only explanatory_synthesis figures")

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
    elif safety_cap > 32:
        errors.append("search_plan.safety_cap exceeds the executor runaway-protection ceiling")
    for key in ("rationale", "resource_basis", "stop_conditions"):
        if not plan.get(key):
            errors.append(f"search_plan.{key} is required")
    reference_strategy = plan.get("reference_strategy") or {}
    if reference_strategy.get("search_required") is not True:
        errors.append("PaperBanana requires reference_strategy.search_required=true")
    if not reference_strategy.get("rationale"):
        errors.append("PaperBanana reference search requires a figure-specific rationale")
    retrieval = read_json(root / "references" / "retrieval.json", errors)
    references = retrieval.get("candidates", []) if isinstance(retrieval.get("candidates"), list) else []

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

    repairs = sorted((root / "repairs").glob("round_*.json")) if (root / "repairs").is_dir() else []
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

    drawai_outputs: dict[str, str] = {}
    paperbanana_quality: dict[str, Any] = {}
    if figure_class == "explanatory_synthesis":
        paperbanana_quality = validate_paperbanana_quality(root, contract, planned, final_image)
        errors.extend(paperbanana_quality["errors"])
        if contract.get("drawai_status") == "AVAILABLE_REQUIRED":
            preflight = read_json(root / "drawai" / "preflight.json", errors)
            if preflight.get("status") != "AVAILABLE" or preflight.get("returncode") != 0:
                errors.append("DrawAI available route requires a passing preflight.json")
            reconstruction = read_json(root / "drawai" / "reconstruction_manifest.json", errors)
            if reconstruction.get("workflow") != "DrawAI":
                errors.append("DrawAI reconstruction manifest must declare workflow=DrawAI")
            if final_image.is_file() and reconstruction.get("source_raster_sha256") != sha256(final_image):
                errors.append("DrawAI reconstruction is not bound to the approved PaperBanana raster")
            outputs = reconstruction.get("outputs")
            if not isinstance(outputs, dict):
                errors.append("DrawAI reconstruction requires outputs for svg, pdf, and pptx")
                outputs = {}
            for kind in ("svg", "pdf", "pptx"):
                artifact = outputs.get(kind)
                if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("sha256"):
                    errors.append(f"DrawAI output {kind} requires path and sha256")
                    continue
                path = resolve(root, artifact["path"])
                if not path.is_file():
                    errors.append(f"DrawAI output {kind} is missing")
                elif sha256(path) != artifact["sha256"]:
                    errors.append(f"DrawAI output {kind} hash mismatch")
                else:
                    drawai_outputs[kind] = str(path)
            vector_review = read_json(root / "drawai" / "vector_review.json", errors)
            if vector_review.get("verdict") not in {"PASS", "PASS_WITH_EXPLAINED_DEVIATION"}:
                errors.append("DrawAI vector review must pass")
            if vector_review.get("blocking_issues"):
                errors.append("DrawAI vector review retains blocking issues")
        elif contract.get("drawai_status") == "UNAVAILABLE_EVIDENCED_SKIP":
            unavailable = read_json(root / "drawai" / "unavailable.json", errors)
            required = ("status", "preflight_command", "observed_error", "attempted_configuration", "rationale", "reviewer")
            if unavailable.get("status") != "UNAVAILABLE" or any(not unavailable.get(key) for key in required[1:]):
                errors.append("DrawAI skip requires a complete unavailable.json preflight record")
    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "candidate_count": len(successful),
        "reference_count": len(references),
        "critic_rounds": len(repairs) + 1,
        "accepted_repairs": sum(1 for path in repairs if read_json(path, []).get("accepted") is True),
        "final_image": str(final_image) if final_image.is_file() else "",
        "figure_class": figure_class,
        "route": route,
        "drawai_status": contract.get("drawai_status"),
        "drawai_outputs": drawai_outputs,
        "paperbanana_quality": paperbanana_quality,
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
