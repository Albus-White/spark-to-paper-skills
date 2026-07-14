#!/usr/bin/env python3
"""Deterministic publication-policy and venue-calibration contracts."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

METRIC_KEYS = (
    "page_count",
    "unique_cited_references",
    "total_figures",
    "table_count",
    "evaluation_count",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def round_half_up(value: float) -> int:
    return int(math.floor(float(value) + 0.5))


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot compute an arithmetic mean from an empty sample")
    return sum(values) / len(values)


FIGURE_CLASS_ROUTES = {
    "measured_evidence": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE",
    "original_observation": "ORIGINAL_EVIDENCE",
    "exact_structure": "DOMAIN_NATIVE",
    "explanatory_synthesis": "PAPERBANANA_REQUIRED",
}


def derive_publication_envelope(
    policy: dict[str, Any],
    venue_profile: dict[str, Any],
) -> dict[str, Any]:
    """Return observations and exact constraints, never a manuscript quota."""
    aggregates = venue_profile["aggregates"]
    metrics = {}
    for key in METRIC_KEYS:
        metrics[key] = {
            "mean": aggregates["means"][key],
            "median": aggregates["medians"][key],
            "interquartile_range": [aggregates["lower_quartiles"][key], aggregates["upper_quartiles"][key]],
            "observed_range": [aggregates["minima"][key], aggregates["maxima"][key]],
            "outliers": aggregates["outliers"][key],
        }
    user_minimum = policy["citation_policy"].get("minimum_unique_cited_references")
    return {
        "sample_size": len(venue_profile.get("papers", [])),
        "metrics": metrics,
        "evidence_dimension_means": aggregates["evidence_dimension_means"],
        "figure_role_means": aggregates["figure_role_means"],
        "evaluation_kind_means": aggregates["evaluation_kind_means"],
        "evaluation_difficulty_synthesis": venue_profile["evaluation_difficulty_synthesis"],
        "official_constraints": venue_profile.get("official_constraints", {}),
        "user_constraints": {
            "minimum_unique_cited_references": user_minimum,
            "figure_policy": policy["figure_policy"],
            "requirements": policy.get("requirements", []),
        },
        "interpretation": "observed_calibration_not_a_quota",
    }


def validate_user_policy(payload: dict[str, Any]) -> None:
    required = {
        "source",
        "target_venue",
        "venue_selection_policy",
        "citation_policy",
        "figure_policy",
        "requirements",
        "research_preferences",
        "deadline",
        "resource_limits",
        "human_review",
        "priorities",
        "degradation_policy",
        "assumptions",
    }
    missing = sorted(key for key in required if key not in payload)
    if missing:
        raise ValueError(f"user policy missing fields: {missing}")
    if payload["source"] not in {"USER_PROVIDED", "USER_CONFIRMED_ASSUMPTIONS", "COMPILED_FROM_USER_REQUEST"}:
        raise ValueError("user policy source is invalid")
    if not payload.get("target_venue") and payload["venue_selection_policy"] != "RELEVANT_TOP_VENUES_IF_UNSPECIFIED":
        raise ValueError("an unspecified target venue requires RELEVANT_TOP_VENUES_IF_UNSPECIFIED")
    citation = payload["citation_policy"]
    if not isinstance(citation, dict):
        raise ValueError("citation_policy must be an object")
    minimum = citation.get("minimum_unique_cited_references")
    if minimum is not None and (not isinstance(minimum, int) or minimum < 0):
        raise ValueError("an explicit citation minimum must be a non-negative integer")
    figures = payload["figure_policy"]
    if not isinstance(figures, dict):
        raise ValueError("figure_policy must be an object")
    expected_routes = {
        "measured_evidence_route": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE",
        "original_observation_route": "ORIGINAL_EVIDENCE",
        "exact_structure_route": "DOMAIN_NATIVE",
        "explanatory_synthesis_route": "PAPERBANANA_REQUIRED",
        "drawai_policy": "USE_IF_AVAILABLE_AFTER_RASTER_APPROVAL",
    }
    if any(figures.get(key) != value for key, value in expected_routes.items()):
        raise ValueError("figure_policy must preserve source-of-truth routing and conditional DrawAI")
    preferences = payload["research_preferences"]
    if not isinstance(preferences, dict) or not preferences.get("field") or not preferences.get("paper_archetype"):
        raise ValueError("research_preferences requires field and paper_archetype")
    if not isinstance(payload["deadline"], dict) or not payload["deadline"]:
        raise ValueError("user policy requires an explicit deadline or UNKNOWN status")
    limits = payload["resource_limits"]
    if not isinstance(limits, dict) or any(key not in limits for key in ("compute", "financial", "api", "storage")):
        raise ValueError("resource_limits requires compute, financial, api, and storage entries")
    if not isinstance(payload["priorities"], list) or not payload["priorities"]:
        raise ValueError("user policy priorities must be a non-empty list")
    degradation = payload["degradation_policy"]
    if not isinstance(degradation, dict) or any(key not in degradation for key in ("acceptable", "unacceptable")):
        raise ValueError("degradation_policy requires acceptable and unacceptable lists")
    assumptions = payload["assumptions"]
    if not isinstance(assumptions, dict) or any(key not in assumptions for key in ("unknowns", "confirmed")):
        raise ValueError("assumptions requires unknowns and confirmed entries")


def _validate_local_pdf(root: Path, paper: dict[str, Any], index: int) -> None:
    pdf = paper.get("pdf")
    if not isinstance(pdf, dict) or not pdf.get("path") or not pdf.get("sha256"):
        raise ValueError(f"venue paper {index} requires a local source PDF path and sha256")
    path = Path(str(pdf["path"]))
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        raise ValueError(f"venue paper {index} source PDF is missing: {pdf['path']}")
    if sha256_file(path) != pdf["sha256"]:
        raise ValueError(f"venue paper {index} source PDF hash mismatch")


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _metric_summary(values: list[float]) -> dict[str, Any]:
    lower = _percentile(values, 0.25)
    upper = _percentile(values, 0.75)
    spread = upper - lower
    low_fence = lower - 1.5 * spread
    high_fence = upper + 1.5 * spread
    return {
        "mean": mean(values),
        "median": statistics.median(values),
        "lower_quartile": lower,
        "upper_quartile": upper,
        "minimum": min(values),
        "maximum": max(values),
        "outliers": [value for value in values if value < low_fence or value > high_fence],
    }


def compute_venue_aggregates(papers: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = {
        key: _metric_summary([float(paper["metrics"][key]) for paper in papers])
        for key in METRIC_KEYS
    }
    means = {key: value["mean"] for key, value in summaries.items()}
    def count_map_means(field: str) -> dict[str, float]:
        names = set().union(*(set(paper["metrics"][field]) for paper in papers))
        return {
            key: mean([float(paper["metrics"][field].get(key, 0)) for paper in papers])
            for key in sorted(names)
        }
    return {
        "means": means,
        "medians": {key: value["median"] for key, value in summaries.items()},
        "lower_quartiles": {key: value["lower_quartile"] for key, value in summaries.items()},
        "upper_quartiles": {key: value["upper_quartile"] for key, value in summaries.items()},
        "minima": {key: value["minimum"] for key, value in summaries.items()},
        "maxima": {key: value["maximum"] for key, value in summaries.items()},
        "missingness": {key: 0 for key in METRIC_KEYS},
        "outliers": {key: value["outliers"] for key, value in summaries.items()},
        "evidence_dimension_means": count_map_means("evidence_dimensions"),
        "figure_role_means": count_map_means("figure_roles"),
        "evaluation_kind_means": count_map_means("evaluation_kinds"),
    }


def validate_venue_profile(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    required = {
        "venue_basis",
        "research_scope",
        "corpus_criteria",
        "papers",
        "aggregates",
        "sample_sufficiency",
        "evaluation_difficulty_synthesis",
        "limitations",
        "reviewer",
    }
    missing = sorted(key for key in required if not payload.get(key))
    if missing:
        raise ValueError(f"venue profile missing non-empty fields: {missing}")
    papers = payload["papers"]
    if not isinstance(papers, list) or not papers:
        raise ValueError("venue profile papers must be a non-empty list")
    seen_sources: set[str] = set()
    for index, paper in enumerate(papers):
        required_paper = {"title", "venue", "year", "article_type", "source", "pdf", "relevance", "metrics"}
        absent = sorted(key for key in required_paper if not paper.get(key))
        if absent:
            raise ValueError(f"venue paper {index} missing non-empty fields: {absent}")
        source = paper["source"]
        if not isinstance(source, dict) or not any(source.get(key) for key in ("doi", "url", "official_path")):
            raise ValueError(f"venue paper {index} needs a DOI, URL, or official source path")
        identity = str(source.get("doi") or source.get("url") or source.get("official_path"))
        if identity in seen_sources:
            raise ValueError(f"duplicate venue paper source: {identity}")
        seen_sources.add(identity)
        _validate_local_pdf(root, paper, index)
        metrics = paper["metrics"]
        missing_metrics = [key for key in METRIC_KEYS if key not in metrics]
        if missing_metrics:
            raise ValueError(f"venue paper {index} missing metrics: {missing_metrics}")
        for key in METRIC_KEYS:
            if not isinstance(metrics[key], (int, float)) or metrics[key] < 0:
                raise ValueError(f"venue paper {index} metric {key} must be non-negative")
        for field in ("figure_roles", "evaluation_kinds", "evidence_dimensions"):
            counts = metrics.get(field)
            if not isinstance(counts, dict) or not counts:
                raise ValueError(f"venue paper {index} requires non-empty {field}")
            if any(not key or not isinstance(value, (int, float)) or value < 0 for key, value in counts.items()):
                raise ValueError(f"venue paper {index} {field} must contain named non-negative counts")
        if not math.isclose(sum(metrics["figure_roles"].values()), metrics["total_figures"]):
            raise ValueError(f"venue paper {index} figure_roles do not sum to total_figures")
        if not math.isclose(sum(metrics["evaluation_kinds"].values()), metrics["evaluation_count"]):
            raise ValueError(f"venue paper {index} evaluation_kinds do not sum to evaluation_count")
        difficulty = metrics.get("evaluation_difficulty")
        if not isinstance(difficulty, dict) or any(difficulty.get(key) in (None, "", []) for key in ("rating", "drivers", "rationale")):
            raise ValueError(f"venue paper {index} evaluation_difficulty requires rating, drivers, and rationale")
    computed = compute_venue_aggregates(papers)
    declared = payload["aggregates"]
    for group in (
        "means", "medians", "lower_quartiles", "upper_quartiles", "minima",
        "maxima", "missingness", "outliers", "evidence_dimension_means",
        "figure_role_means", "evaluation_kind_means",
    ):
        if not isinstance(declared.get(group), dict):
            raise ValueError(f"venue aggregates require {group}")
        for key, value in computed[group].items():
            observed = declared[group].get(key)
            if isinstance(value, list):
                matches = observed == value
            else:
                matches = isinstance(observed, (int, float)) and math.isclose(
                    float(observed), float(value), rel_tol=1e-9, abs_tol=1e-9
                )
            if not matches:
                raise ValueError(f"venue aggregate {group}.{key} is not reproducible from the paper sample")
    judgment = payload["sample_sufficiency"]
    if not isinstance(judgment, dict) or not all(judgment.get(key) for key in ("verdict", "rationale", "coverage", "stopping_reason")):
        raise ValueError("sample_sufficiency requires verdict, rationale, coverage, and stopping_reason")
    if judgment["verdict"] not in {"SUFFICIENT", "SUFFICIENT_WITH_LIMITATIONS"}:
        raise ValueError("venue profile cannot freeze with an insufficient sample")
    return computed


def validate_publication_contract(
    payload: dict[str, Any],
    policy: dict[str, Any],
    venue_profile: dict[str, Any],
) -> dict[str, Any]:
    required = {
        "idea_id",
        "research_program_id",
        "research_program_hash",
        "claim_registry_hash",
        "claim_ids",
        "paper_archetype",
        "calibration_envelope",
        "targets",
        "target_rationales",
        "section_plan",
        "figure_plan",
        "table_plan",
        "citation_coverage_requirements",
        "deadline_allocation",
        "deviations",
        "manuscript_content_policy",
    }
    missing = sorted(key for key in required if key not in payload or payload[key] in (None, ""))
    if missing:
        raise ValueError(f"publication contract missing non-empty fields: {missing}")
    if not isinstance(payload["claim_ids"], list) or not payload["claim_ids"] or len(payload["claim_ids"]) != len(set(payload["claim_ids"])):
        raise ValueError("publication contract claim_ids must be a non-empty unique list")
    envelope = derive_publication_envelope(policy, venue_profile)
    if payload["calibration_envelope"] != envelope:
        raise ValueError("publication calibration envelope is stale or not reproducible")
    targets = payload["targets"]
    required_targets = {
        "page_range", "minimum_unique_cited_references", "figure_count", "table_count",
    }
    if not isinstance(targets, dict) or set(targets) != required_targets:
        raise ValueError(f"publication targets must exactly contain {sorted(required_targets)}")
    page_range = targets["page_range"]
    if not isinstance(page_range, list) or len(page_range) != 2 or any(not isinstance(value, int) or value < 1 for value in page_range) or page_range[0] > page_range[1]:
        raise ValueError("targets.page_range must be an increasing pair of positive integers")
    for key in ("minimum_unique_cited_references", "figure_count", "table_count"):
        if not isinstance(targets[key], int) or targets[key] < 0:
            raise ValueError(f"targets.{key} must be a non-negative integer")
    user_minimum = policy["citation_policy"].get("minimum_unique_cited_references")
    if user_minimum is not None and targets["minimum_unique_cited_references"] < user_minimum:
        raise ValueError("publication citation target is below the user's explicit minimum")
    rationales = payload["target_rationales"]
    if not isinstance(rationales, dict) or any(not rationales.get(key) for key in required_targets):
        raise ValueError("target_rationales must explain every selected publication target")
    deviations = payload["deviations"]
    if not isinstance(deviations, list):
        raise ValueError("deviations must be a list")
    deviation_metrics = set()
    for index, deviation in enumerate(deviations):
        if not isinstance(deviation, dict) or any(deviation.get(key) in (None, "", []) for key in ("metric", "rationale", "evidence")):
            raise ValueError(f"publication deviation {index} requires metric, rationale, and evidence")
        deviation_metrics.add(deviation["metric"])
    selected_metrics = {
        "page_count": page_range,
        "unique_cited_references": targets["minimum_unique_cited_references"],
        "total_figures": targets["figure_count"],
        "table_count": targets["table_count"],
    }
    for metric, selected in selected_metrics.items():
        observed = envelope["metrics"][metric]["observed_range"]
        outside = (
            selected[1] < observed[0] or selected[0] > observed[1]
            if isinstance(selected, list)
            else selected < observed[0] or selected > observed[1]
        )
        if outside and metric not in deviation_metrics:
            raise ValueError(f"target {metric} is outside the observed comparable-paper range without a deviation record")
    sections = payload["section_plan"]
    if not isinstance(sections, list) or not sections:
        raise ValueError("section_plan must be a non-empty manuscript projection")
    section_ids = [item.get("section_id") for item in sections if isinstance(item, dict)]
    if len(section_ids) != len(sections) or any(not item for item in section_ids) or len(section_ids) != len(set(section_ids)):
        raise ValueError("section_plan requires unique non-empty section_id values")
    if any(not item.get("purpose") for item in sections):
        raise ValueError("every publication section requires a scientific purpose")
    figures = payload["figure_plan"]
    if not isinstance(figures, list) or len(figures) != targets["figure_count"]:
        raise ValueError("figure_plan count must equal the selected figure target")
    seen: set[str] = set()
    for item in figures:
        required_figure = ("figure_id", "class", "purpose", "route", "source_of_truth", "claim_ids", "section_role")
        if not isinstance(item, dict) or any(item.get(key) in (None, "", []) for key in required_figure):
            raise ValueError(f"every publication figure requires {', '.join(required_figure)}")
        if item["figure_id"] in seen:
            raise ValueError(f"duplicate publication figure_id: {item['figure_id']}")
        seen.add(item["figure_id"])
        expected_route = FIGURE_CLASS_ROUTES.get(item["class"])
        if expected_route is None or item["route"] != expected_route:
            raise ValueError(f"figure {item['figure_id']} class/source route is invalid")
        if item["class"] == "explanatory_synthesis" and item.get("drawai_policy") != "USE_IF_AVAILABLE_AFTER_RASTER_APPROVAL":
            raise ValueError(f"PaperBanana figure {item['figure_id']} must declare conditional DrawAI after raster approval")
        if not set(item["claim_ids"]).issubset(set(payload["claim_ids"])):
            raise ValueError(f"figure {item['figure_id']} references claims outside the publication contract")
    tables = payload["table_plan"]
    if not isinstance(tables, list) or len(tables) != targets["table_count"]:
        raise ValueError("table_plan count must equal the selected table target")
    required_table = ("table_id", "purpose", "source_of_truth", "claim_ids", "section_role")
    for index, item in enumerate(tables):
        if not isinstance(item, dict) or any(item.get(key) in (None, "", []) for key in required_table):
            raise ValueError(f"publication table {index} requires {', '.join(required_table)}")
        if not set(item["claim_ids"]).issubset(set(payload["claim_ids"])):
            raise ValueError(f"table {item['table_id']} references claims outside the publication contract")
    table_ids = [item.get("table_id") for item in tables if isinstance(item, dict)]
    if len(table_ids) != len(tables) or any(not item for item in table_ids) or len(table_ids) != len(set(table_ids)):
        raise ValueError("table_plan requires unique non-empty table_id values")
    content_policy = payload["manuscript_content_policy"]
    required_content_policy = (
        "internal_provenance_location", "reader_relevant_reproducibility_only",
        "forbid_page_filler", "allowed_internal_identifiers",
    )
    if not isinstance(content_policy, dict) or any(key not in content_policy for key in required_content_policy):
        raise ValueError(f"manuscript_content_policy requires {', '.join(required_content_policy)}")
    if content_policy["internal_provenance_location"] != "artifact_package":
        raise ValueError("internal hashes, gate ledgers, and run commands belong in the artifact package")
    if content_policy["reader_relevant_reproducibility_only"] is not True or content_policy["forbid_page_filler"] is not True:
        raise ValueError("manuscript content policy must prohibit audit leakage and page filler")
    return envelope


def dump_envelope(
    policy_path: Path,
    venue_path: Path,
) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    venue = json.loads(venue_path.read_text(encoding="utf-8"))
    return derive_publication_envelope(policy, venue)
