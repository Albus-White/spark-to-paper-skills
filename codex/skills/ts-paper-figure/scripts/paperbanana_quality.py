#!/usr/bin/env python3
"""Validate real PaperBanana execution and model-owned visual quality evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REVIEW_DIMENSIONS = (
    "semantic_fidelity",
    "visual_specificity",
    "information_hierarchy",
    "field_convention_alignment",
    "anti_genericness",
    "legibility",
    "integrity",
)
UPSTREAM_STAGES = {"retriever", "planner", "stylist", "visualizer", "critic"}


def read_json(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"missing PaperBanana artifact: {path.name}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"unreadable PaperBanana artifact {path.name}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"PaperBanana artifact {path.name} must contain an object")
        return {}
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(root: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else root / path


def readable_image(path: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def validate_references(root: Path, errors: list[str]) -> tuple[dict[str, Any], list[str]]:
    retrieval_path = root / "references/retrieval.json"
    retrieval = read_json(retrieval_path, errors)
    if not isinstance(retrieval.get("search_queries"), list) or not retrieval["search_queries"]:
        errors.append("PaperBanana reference search requires recorded search_queries")
    if not isinstance(retrieval.get("attempted_sources"), list) or not retrieval["attempted_sources"]:
        errors.append("PaperBanana reference search requires attempted_sources")
    candidates = retrieval.get("candidates")
    if not isinstance(candidates, list):
        errors.append("PaperBanana reference candidates must be a list")
        candidates = []
    by_id = {}
    for index, item in enumerate(candidates):
        required = ("reference_id", "title", "source", "image", "content", "visual_intent", "reason_selected", "visual_conventions")
        if not isinstance(item, dict) or any(item.get(key) in (None, "", []) for key in required):
            errors.append(f"PaperBanana reference candidate {index} is incomplete")
            continue
        if item["reference_id"] in by_id:
            errors.append(f"duplicate PaperBanana reference_id: {item['reference_id']}")
        by_id[item["reference_id"]] = item
    decision = retrieval.get("decision")
    if not isinstance(decision, dict) or decision.get("status") not in {"SELECTED", "NO_SUITABLE_REFERENCE"}:
        errors.append("PaperBanana reference decision must be SELECTED or NO_SUITABLE_REFERENCE")
        decision = {}
    for key in ("rationale", "reviewer"):
        if not decision.get(key):
            errors.append(f"PaperBanana reference decision requires {key}")
    selected_ids = decision.get("selected_reference_ids") or []
    if decision.get("status") == "SELECTED" and not selected_ids:
        errors.append("selected PaperBanana references require selected_reference_ids")
    if decision.get("status") == "NO_SUITABLE_REFERENCE" and not decision.get("rejection_summary"):
        errors.append("NO_SUITABLE_REFERENCE requires rejection_summary")
    for reference_id in selected_ids:
        item = by_id.get(reference_id)
        if not item:
            errors.append(f"selected PaperBanana reference is unknown: {reference_id}")
            continue
        image = resolve(root, item["image"])
        if not image.is_file() or not readable_image(image):
            errors.append(f"selected PaperBanana reference image is missing or unreadable: {reference_id}")
    return retrieval, list(selected_ids)


def validate_semantic_plan(root: Path, contract: dict[str, Any], retrieval: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    semantic = read_json(root / "paperbanana/semantic_plan.json", errors)
    required = (
        "figure_id", "communication_goal", "visual_story", "visual_blueprint", "concrete_visual_elements",
        "field_visual_conventions", "anti_generic_strategy", "text_strategy", "required_content",
        "forbidden_content", "reference_decision", "retrieval_sha256", "minimalism_decision",
    )
    for key in required:
        if semantic.get(key) in (None, "", []):
            errors.append(f"PaperBanana semantic plan missing {key}")
    if not isinstance(semantic.get("semantic_edges"), list):
        errors.append("PaperBanana semantic plan semantic_edges must be a list")
    if semantic.get("figure_id") and semantic.get("figure_id") != contract.get("figure_id"):
        errors.append("PaperBanana semantic plan figure_id mismatch")
    retrieval_path = root / "references/retrieval.json"
    if retrieval_path.is_file() and semantic.get("retrieval_sha256") != sha256(retrieval_path):
        errors.append("PaperBanana semantic plan is not bound to reference retrieval")
    if semantic.get("reference_decision") != (retrieval.get("decision") or {}).get("status"):
        errors.append("PaperBanana semantic plan reference decision differs from retrieval")
    if semantic.get("minimalism_decision") not in {"RICH_DOMAIN_SPECIFIC", "JUSTIFIED_MINIMAL"}:
        errors.append("PaperBanana minimalism_decision is invalid")
    if semantic.get("minimalism_decision") == "JUSTIFIED_MINIMAL" and not semantic.get("minimalism_rationale"):
        errors.append("JUSTIFIED_MINIMAL requires a field-precedent rationale")
    return semantic


def validate_upstream_run(root: Path, planned_candidates: int, errors: list[str]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    run = read_json(root / "paperbanana/run.json", errors)
    if run.get("workflow") != "PaperBanana" or run.get("executor") != "upstream_papervizprocessor_adapter":
        errors.append("PaperBanana run must come from the upstream PaperVizProcessor adapter")
    upstream = run.get("upstream")
    if not isinstance(upstream, dict) or not upstream.get("commit") or upstream.get("dirty") not in {False, True}:
        errors.append("PaperBanana run requires a pinned upstream Git identity")
    if upstream and upstream.get("dirty") is True and not upstream.get("dirty_status_sha256"):
        errors.append("dirty PaperBanana execution requires a recorded diff-status hash")
    if run.get("returncode") != 0:
        errors.append("PaperBanana upstream execution did not complete successfully")
    if set(run.get("stages") or []) != UPSTREAM_STAGES:
        errors.append("PaperBanana run must execute Retriever, Planner, Stylist, Visualizer, and Critic")
    candidates = run.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != planned_candidates:
        errors.append("PaperBanana run candidate count differs from the frozen search plan")
        candidates = []
    by_id = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or not candidate.get("candidate_id") or candidate["candidate_id"] in by_id:
            errors.append(f"PaperBanana upstream candidate {index} has a missing or duplicate ID")
            continue
        stages = candidate.get("stages")
        if not isinstance(stages, dict) or any(not (stages.get(stage) or {}).get("ran") for stage in UPSTREAM_STAGES):
            errors.append(f"PaperBanana candidate {candidate['candidate_id']} lacks a real stage trace")
        final = resolve(root, candidate.get("final_image"))
        if not final.is_file() or not readable_image(final) or candidate.get("final_sha256") != sha256(final):
            errors.append(f"PaperBanana candidate {candidate['candidate_id']} final image is missing or hash-mismatched")
        by_id[candidate["candidate_id"]] = candidate
    for binding in ("input", "semantic_plan", "reference_search", "style_guide", "worker_report"):
        artifact = run.get(binding)
        if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("sha256"):
            errors.append(f"PaperBanana run missing {binding} binding")
            continue
        path = resolve(root, artifact["path"])
        if not path.is_file() or sha256(path) != artifact["sha256"]:
            errors.append(f"PaperBanana run {binding} binding is stale")
    return run, by_id


def validate_final_review(root: Path, final_image: Path, selected_ids: list[str], errors: list[str]) -> None:
    review = read_json(root / "critique/final_vision_review.json", errors)
    if final_image.is_file() and review.get("artifact_sha256") != sha256(final_image):
        errors.append("PaperBanana final review is not bound to the selected actual image")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict) or reviewer.get("actual_image_review") is not True or reviewer.get("independent_from_generation") is not True:
        errors.append("PaperBanana final review must be fresh and independent from generation")
    elif not isinstance(reviewer.get("context_artifacts"), list) or not reviewer["context_artifacts"]:
        errors.append("PaperBanana final reviewer must record its minimal context artifacts")
    dimensions = review.get("dimensions")
    if not isinstance(dimensions, dict):
        errors.append("PaperBanana final review requires structured dimensions")
        dimensions = {}
    for name in REVIEW_DIMENSIONS:
        item = dimensions.get(name)
        if not isinstance(item, dict) or item.get("verdict") not in {"PASS", "PASS_WITH_EXPLAINED_DEVIATION"} or not item.get("rationale") or not item.get("visual_evidence"):
            errors.append(f"PaperBanana review dimension {name} is missing, failed, or lacks visible evidence")
    diagnosis = review.get("generic_box_flowchart_diagnosis")
    if not isinstance(diagnosis, dict) or diagnosis.get("detected") is not False or not diagnosis.get("rationale") or not diagnosis.get("visual_evidence"):
        errors.append("PaperBanana review must explicitly reject generic box-flowchart degeneration")
    if selected_ids and not review.get("reference_comparison"):
        errors.append("PaperBanana review must compare the final image with selected field references")
    if review.get("publication_readiness") not in {"PASS", "PASS_WITH_EXPLAINED_DEVIATION"}:
        errors.append("PaperBanana final review must pass publication readiness")
    if review.get("blocking_issues"):
        errors.append("PaperBanana final review retains blocking issues")


def validate(root: Path, contract: dict[str, Any], planned_candidates: int, final_image: Path) -> dict[str, Any]:
    errors: list[str] = []
    retrieval, selected_reference_ids = validate_references(root, errors)
    semantic = validate_semantic_plan(root, contract, retrieval, errors)
    run, candidates = validate_upstream_run(root, planned_candidates, errors)
    selection = read_json(root / "selection.json", errors)
    selected_candidate = candidates.get(str(selection.get("selected_candidate_id") or ""))
    if not selected_candidate:
        errors.append("PaperBanana selection is not an executed upstream candidate")
    elif final_image.is_file() and selected_candidate.get("final_sha256") != sha256(final_image):
        errors.append("PaperBanana selected image differs from the upstream candidate")
    if planned_candidates > 1:
        comparison = selection.get("quality_comparison")
        required = ("semantic_fidelity", "visual_specificity", "information_hierarchy", "reference_alignment", "why_selected")
        if not isinstance(comparison, dict) or any(not comparison.get(key) for key in required):
            errors.append("multi-candidate PaperBanana selection requires an actual-image quality comparison")
    validate_final_review(root, final_image, selected_reference_ids, errors)
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": [],
        "reference_decision": (retrieval.get("decision") or {}).get("status"),
        "selected_reference_ids": selected_reference_ids,
        "minimalism_decision": semantic.get("minimalism_decision"),
        "upstream_commit": (run.get("upstream") or {}).get("commit"),
        "executed_candidates": sorted(candidates),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pipeline")
    parser.add_argument("--final-image")
    args = parser.parse_args()
    root = Path(args.pipeline).resolve()
    errors: list[str] = []
    contract = read_json(root / "figure_contract.json", errors)
    plan = read_json(root / "search_plan.json", errors)
    selection = read_json(root / "selection.json", errors)
    final_image = resolve(root, args.final_image or selection.get("final_image"))
    report = validate(root, contract, int(plan.get("planned_candidates") or 0), final_image)
    report["errors"] = errors + report["errors"]
    report["ok"] = not report["errors"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
