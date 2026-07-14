#!/usr/bin/env python3
"""Validate blueprint structure without deciding the paper's scientific organization."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CLAIM_TYPE_MAP = {
    "DATASET": "METRIC", "METHOD": "CORE", "BACKGROUND": "CONTEXT",
    "COMPARISON": "BASELINE", "PRIOR": "CONTEXT", "RELATED": "CONTEXT",
    "BENCHMARK": "METRIC", "EVALUATION": "METRIC", "TERM": "DEFINITION",
}


def load_spec(workdir: Path) -> dict:
    path = workdir / "template.json"
    if not path.is_file():
        raise ValueError("template.json is required; venue formatting must never silently fall back")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("template.json root must be an object")
    return value


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: blueprint_lint.py <workdir> [--fix]"}))
        return 2
    workdir = Path(sys.argv[1]).resolve()
    fix = "--fix" in sys.argv[2:]
    try:
        spec = load_spec(workdir)
        blueprint = json.loads((workdir / "blueprint.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "issues": [str(exc)]}, indent=2))
        return 1
    issues: list[str] = []
    repaired: list[str] = []
    publication_contract = {}
    for key, required_fields in (
        ("venue_profile", ("papers", "aggregates", "sample_sufficiency")),
        ("publication_contract", ("targets", "figure_plan", "section_plan", "claim_ids")),
    ):
        relative = blueprint.get(key)
        if not relative:
            issues.append(f"blueprint.{key} is required")
            continue
        try:
            path = (workdir / str(relative)).resolve()
            path.relative_to(workdir)
            value = json.loads(path.read_text(encoding="utf-8"))
            missing = [field for field in required_fields if field not in value or value[field] in (None, "")]
            if missing:
                issues.append(f"blueprint {key} artifact missing {missing}")
            if key == "venue_profile":
                papers = value.get("papers")
                if not isinstance(papers, list) or not papers:
                    issues.append("venue profile requires accepted papers")
                else:
                    for index, paper in enumerate(papers):
                        source = paper.get("source") if isinstance(paper, dict) else None
                        if not isinstance(source, dict) or not any(source.get(item) for item in ("url", "doi", "official_path")):
                            issues.append(f"venue profile papers[{index}] needs url, doi, or official_path")
                        pdf = paper.get("pdf") if isinstance(paper, dict) else None
                        if not isinstance(pdf, dict) or not pdf.get("path") or not pdf.get("sha256"):
                            issues.append(f"venue profile papers[{index}] needs local PDF path and sha256")
                        metrics = paper.get("metrics") if isinstance(paper, dict) else None
                        required_metrics = {
                            "page_count", "unique_cited_references", "total_figures", "table_count",
                            "evaluation_count", "figure_roles", "evaluation_kinds", "evidence_dimensions",
                            "evaluation_difficulty",
                        }
                        if not isinstance(metrics, dict) or not required_metrics.issubset(metrics):
                            issues.append(f"venue profile papers[{index}] lacks complete publication/evidence metrics")
            if key == "publication_contract":
                publication_contract = value
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues.append(f"blueprint {key} is invalid: {exc}")
    sections = blueprint.get("sections")
    if not isinstance(sections, dict) or not sections:
        issues.append("blueprint.sections must be a non-empty object chosen for this paper")
        sections = {}
    allowed_citations = set((spec.get("citations") or {}).get("types") or [])
    template_sections = {item["id"]: item for item in spec.get("sections", []) if isinstance(item, dict) and item.get("id")}
    for section_id, section in sections.items():
        if not isinstance(section, dict):
            issues.append(f"section {section_id} must be an object")
            continue
        if not section.get("title"):
            issues.append(f"section {section_id}.title is required")
        roles = section.get("roles") or template_sections.get(section_id, {}).get("roles") or []
        if not isinstance(roles, list):
            issues.append(f"section {section_id}.roles must be a list")
        target = section.get("target_words")
        if target is not None and not (isinstance(target, (list, tuple)) and len(target) == 2 and target[0] <= target[1]):
            issues.append(f"section {section_id}.target_words must be [min,max] when supplied")
        citation_types = section.get("citation_types", [])
        normalized = []
        for value in citation_types:
            upper = str(value).upper()
            mapped = upper if upper in allowed_citations else CLAIM_TYPE_MAP.get(upper)
            if mapped in allowed_citations:
                normalized.append(mapped)
                if mapped != upper:
                    repaired.append(f"{section_id}.citation_types: {upper}->{mapped}")
            else:
                issues.append(f"section {section_id} has unknown citation type {upper}")
        if fix and normalized != citation_types:
            section["citation_types"] = normalized
    order = blueprint.get("section_order")
    if not isinstance(order, list) or set(order) != set(sections) or len(order) != len(sections):
        issues.append("section_order must list every blueprint section exactly once")
    required_sections = [item["id"] for item in spec.get("sections", []) if item.get("required") is True]
    for section_id in required_sections:
        if section_id not in sections:
            issues.append(f"venue template requires section {section_id}")
    title = str(blueprint.get("paper_title", "")).strip()
    if not title:
        issues.append("paper_title is required")
    title_spec = spec.get("title") or {}
    if title_spec.get("max_words") and len(title.split()) > int(title_spec["max_words"]):
        issues.append(f"paper_title exceeds venue max_words={title_spec['max_words']}")
    if title_spec.get("max_chars") and len(title) > int(title_spec["max_chars"]):
        issues.append(f"paper_title exceeds venue max_chars={title_spec['max_chars']}")

    results_mode = spec.get("results_mode", "proposal")
    figures = []
    tables = []
    result_sections = set()
    for section_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        roles = set(section.get("roles") or template_sections.get(section_id, {}).get("roles") or [])
        if "results" in roles or "evaluation" in roles:
            result_sections.add(section_id)
        figures.extend((section_id, item) for item in section.get("figures", []) if isinstance(item, dict))
        tables.extend((section_id, item) for item in section.get("tables", []) if isinstance(item, dict))
    result_figures = [(section_id, item) for section_id, item in figures if item.get("class") == "measured_evidence"]
    planned_figures = publication_contract.get("figure_plan", []) if isinstance(publication_contract.get("figure_plan"), list) else []
    expected_ids = {str(item.get("figure_id")) for item in planned_figures if isinstance(item, dict) and item.get("figure_id")}
    actual_ids = {str(item.get("figure_id") or item.get("id")) for _, item in figures if item.get("figure_id") or item.get("id")}
    if actual_ids != expected_ids or len(actual_ids) != len(figures):
        issues.append(f"blueprint figure IDs must exactly match publication contract: missing={sorted(expected_ids - actual_ids)} extra={sorted(actual_ids - expected_ids)}")
    planned_by_id = {str(item["figure_id"]): item for item in planned_figures if isinstance(item, dict) and item.get("figure_id")}
    for _, figure in figures:
        figure_id = str(figure.get("figure_id") or figure.get("id") or "")
        planned = planned_by_id.get(figure_id, {})
        if figure.get("class") != planned.get("class") or figure.get("route") != planned.get("route"):
            issues.append(f"blueprint figure {figure_id or '?'} class/route differs from publication contract")
        if figure.get("source_of_truth") != planned.get("source_of_truth"):
            issues.append(f"blueprint figure {figure_id or '?'} source_of_truth differs from publication contract")
    planned_sections = {
        str(item.get("section_id")) for item in publication_contract.get("section_plan", [])
        if isinstance(item, dict) and item.get("section_id")
    }
    if set(sections) != planned_sections:
        issues.append(
            f"blueprint sections must exactly match publication contract: "
            f"missing={sorted(planned_sections - set(sections))} extra={sorted(set(sections) - planned_sections)}"
        )
    planned_tables = publication_contract.get("table_plan", []) if isinstance(publication_contract.get("table_plan"), list) else []
    expected_table_ids = {
        str(item.get("table_id")) for item in planned_tables
        if isinstance(item, dict) and item.get("table_id")
    }
    actual_table_ids = {
        str(item.get("table_id") or item.get("id")) for _, item in tables
        if item.get("table_id") or item.get("id")
    }
    if actual_table_ids != expected_table_ids or len(actual_table_ids) != len(tables):
        issues.append(
            f"blueprint table IDs must exactly match publication contract: "
            f"missing={sorted(expected_table_ids - actual_table_ids)} extra={sorted(actual_table_ids - expected_table_ids)}"
        )
    if results_mode == "proposal" and result_figures:
        issues.append("proposal blueprint cannot plan measured-data result figures")
    if results_mode == "data_aware":
        if not result_sections:
            issues.append("data-aware blueprint needs at least one section with role results or evaluation")
        for section_id, figure in result_figures:
            if section_id not in result_sections:
                issues.append(f"measured-data figure {figure.get('id', '?')} is outside a results/evaluation section")
            for key in ("data_source", "fact_ids", "claim_role", "renderer"):
                if not figure.get(key):
                    issues.append(f"measured-data figure {figure.get('id', '?')} missing {key}")
        for section_id, table in (
            (section_id, item) for section_id, item in tables
            if item.get("source_of_truth") == "canonical_result_facts" or item.get("fact_ids")
        ):
            if section_id not in result_sections:
                issues.append(f"measured-data table {table.get('id', '?')} is outside a results/evaluation section")
            for key in ("data_source", "fact_ids", "claim_role"):
                if not table.get(key):
                    issues.append(f"measured-data table {table.get('id', '?')} missing {key}")
    if fix and repaired:
        (workdir / "blueprint.json").write_text(json.dumps(blueprint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = {"ok": not issues, "template": spec.get("name"), "issues": issues, "repaired": repaired}
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
