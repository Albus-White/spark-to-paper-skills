#!/usr/bin/env python3
"""Validate research artifact structure; scientific meaning belongs to model judgments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BENCHMARK_DECISIONS = {
    "OFFICIAL_BENCHMARK_FOUND", "AUTHOR_BENCHMARK_FOUND", "ADJACENT_BENCHMARK_ONLY",
    "NO_VALID_PUBLIC_BENCHMARK", "BENCHMARK_INCOMPATIBLE", "ACCESS_BLOCKED", "LICENSE_BLOCKED",
    # Legacy values remain importable.
    "CANONICAL_AND_APPLICABLE", "RELATED_BUT_PARTIAL", "INAPPLICABLE", "NO_PUBLIC_BENCHMARK",
}
SUPPORT = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "INCONCLUSIVE", "NEEDS_AUTHOR_CONFIRMATION", "UNVERIFIED"}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"root must be object: {path}")
    return value


def require(obj, keys, prefix, issues):
    for key in keys:
        if key not in obj or obj[key] in (None, "", []):
            issues.append(f"{prefix}.{key} is required")


def validate_grounding(data, issues):
    choices = data.get("design_choices")
    if not isinstance(choices, list) or not choices:
        issues.append("design_choices must be a non-empty list"); return
    for index, choice in enumerate(choices):
        if not isinstance(choice, dict):
            issues.append(f"design_choices[{index}] must be an object"); continue
        require(choice, ["choice_id", "question", "decision", "rationale", "evidence", "uncertainty"], f"design_choices[{index}]", issues)
        if not isinstance(choice.get("evidence"), list):
            issues.append(f"design_choices[{index}].evidence must be a list")


def validate_benchmarks(data, issues):
    decision = data.get("decision")
    if not isinstance(decision, dict):
        issues.append("decision must be an object"); return
    require(decision, ["classification", "rationale", "search_scope"], "decision", issues)
    if decision.get("classification") not in BENCHMARK_DECISIONS:
        issues.append("decision.classification invalid")
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        issues.append("candidates must be a list"); return
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            issues.append(f"candidates[{index}] must be an object"); continue
        require(candidate, ["name", "source", "status", "compatibility_rationale", "license_status"], f"candidates[{index}]", issues)


def validate_contract(data, claims, issues):
    require(data, [
        "claim_ids", "evaluation_units", "study_inputs", "protocol", "outcomes", "comparators",
        "analysis_plan", "test_set_policy", "stop_conditions", "resource_plan", "feasibility",
        "benchmark_policy", "venue_alignment", "revalidation_policy", "idea_iteration_policy",
    ], "research_program", issues)
    known = {item.get("claim_id") for item in claims.get("claims", [])}
    for claim_id in data.get("claim_ids", []):
        if claim_id not in known:
            issues.append(f"unknown claim: {claim_id}")
    units = data.get("evaluation_units", [])
    if not isinstance(units, list) or not units:
        issues.append("research_program.evaluation_units must be a non-empty list")
        units = []
    valid_kinds = {
        "benchmark", "experiment", "simulation", "observational_analysis",
        "qualitative_study", "proof", "artifact_evaluation",
    }
    seen_units = set()
    covered_claims = set()
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            issues.append(f"evaluation_units[{index}] must be an object")
            continue
        require(unit, [
            "unit_id", "kind", "claim_ids", "question", "why_it_tests_claim", "protocol_summary",
            "positive_interpretation", "negative_interpretation", "confounders",
            "out_of_scope_conclusions", "difficulty", "stop_condition",
        ], f"evaluation_units[{index}]", issues)
        unit_id = unit.get("unit_id")
        if unit_id in seen_units:
            issues.append(f"duplicate evaluation unit: {unit_id}")
        seen_units.add(unit_id)
        if unit.get("kind") not in valid_kinds:
            issues.append(f"evaluation_units[{index}].kind invalid")
        unit_claims = set(unit.get("claim_ids") or [])
        covered_claims.update(unit_claims)
        for claim_id in unit_claims:
            if claim_id not in known:
                issues.append(f"evaluation_units[{index}] references unknown claim: {claim_id}")
    uncovered = set(data.get("claim_ids") or []) - covered_claims
    if uncovered:
        issues.append(f"research-program claims lack evaluation units: {sorted(uncovered)}")
    feasibility = data.get("feasibility")
    if feasibility is not None and not isinstance(feasibility, dict):
        issues.append("contract.feasibility must be an object when supplied")


def validate_claims(data, issues):
    for index, claim in enumerate(data.get("claims", [])):
        if not isinstance(claim, dict):
            issues.append(f"claims[{index}] must be an object"); continue
        require(claim, ["claim_id", "claim_text", "claim_type", "essential", "strength", "scope", "required_evidence", "support_status"], f"claims[{index}]", issues)
        if claim.get("support_status") not in SUPPORT:
            issues.append(f"claims[{index}].support_status invalid")


def validate_idea_evolution(data, issues):
    require(data, ["source_idea_id", "decision", "mechanism_verdict", "trigger_evidence", "old_evidence_impact", "independent_revalidation_plan", "approval"], "idea_evolution", issues)
    if data.get("test_data_used_for_discovery") and not (data.get("independent_revalidation_plan") or {}).get("new_confirmation_source"):
        issues.append("test-informed Idea evolution requires a new confirmation source")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["grounding", "benchmarks", "claims", "contract", "idea-evolution"])
    parser.add_argument("file"); parser.add_argument("--claims")
    args = parser.parse_args(); issues = []
    try:
        data = load(Path(args.file))
        if args.kind == "grounding": validate_grounding(data, issues)
        elif args.kind == "benchmarks": validate_benchmarks(data, issues)
        elif args.kind == "claims": validate_claims(data, issues)
        elif args.kind == "contract":
            if not args.claims: issues.append("--claims required")
            else: validate_contract(data, load(Path(args.claims)), issues)
        else: validate_idea_evolution(data, issues)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    print(json.dumps({"ok": not issues, "issues": issues}, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
