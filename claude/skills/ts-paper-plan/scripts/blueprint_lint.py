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
    venue_study_rel = blueprint.get("venue_study")
    if not venue_study_rel:
        issues.append("blueprint.venue_study is required")
    else:
        try:
            venue_study_path = (workdir / str(venue_study_rel)).resolve()
            venue_study_path.relative_to(workdir)
            venue_study = json.loads(venue_study_path.read_text(encoding="utf-8"))
            for key in ("official_guidance", "representative_papers", "field_conventions", "user_requirements", "design_decisions", "limitations", "reviewer"):
                if key not in venue_study or venue_study[key] in (None, ""):
                    issues.append(f"venue study missing {key}")
            representative_papers = venue_study.get("representative_papers")
            if not isinstance(representative_papers, list) or not representative_papers:
                issues.append("venue study requires representative_papers selected by the main model")
            else:
                for index, paper in enumerate(representative_papers):
                    if not isinstance(paper, dict) or not str(paper.get("title") or "").strip():
                        issues.append(f"venue study representative_papers[{index}] needs a title")
                        continue
                    if not any(str(paper.get(key) or "").strip() for key in ("url", "doi", "path")):
                        issues.append(f"venue study representative_papers[{index}] needs url, doi, or path")
            for key in ("official_guidance", "field_conventions", "limitations"):
                if key in venue_study and not isinstance(venue_study[key], list):
                    issues.append(f"venue study {key} must be a list")
            for key in ("user_requirements", "design_decisions", "reviewer"):
                if key in venue_study and not isinstance(venue_study[key], dict):
                    issues.append(f"venue study {key} must be an object")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues.append(f"blueprint venue_study is invalid: {exc}")
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
    result_figures = [(section_id, item) for section_id, item in figures if item.get("source_of_truth") == "measured_data"]
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
        for section_id, table in ((section_id, item) for section_id, item in tables if item.get("source_of_truth") == "measured_data"):
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
