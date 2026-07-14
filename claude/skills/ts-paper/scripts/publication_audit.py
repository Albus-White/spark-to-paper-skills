#!/usr/bin/env python3
"""Cross-artifact publication-contract audit."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def read_object(path: Path, issues: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        issues.append(f"unreadable {path}: {exc}")
        return {}
    if not isinstance(value, dict):
        issues.append(f"{path} must contain an object")
        return {}
    return value


def blueprint_figure_ids(blueprint: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for section in blueprint.get("sections", {}).values():
        if not isinstance(section, dict):
            continue
        for figure in section.get("figures", []):
            if isinstance(figure, dict) and (figure.get("figure_id") or figure.get("id")):
                ids.add(str(figure.get("figure_id") or figure.get("id")))
    return ids


def blueprint_table_ids(blueprint: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for section in blueprint.get("sections", {}).values():
        if not isinstance(section, dict):
            continue
        for table in section.get("tables", []):
            if isinstance(table, dict) and (table.get("table_id") or table.get("id")):
                ids.add(str(table.get("table_id") or table.get("id")))
    return ids


def tex_figure_ids(workdir: Path) -> set[str]:
    ids: set[str] = set()
    paths = [workdir / "main.tex"] + sorted((workdir / "sections").rglob("*.tex"))
    for path in paths:
        if not path.is_file() or path.name.endswith(".proc.tex"):
            continue
        text = path.read_text(encoding="utf-8")
        ids.update(re.findall(r"\\label\{fig:([^}]+)\}", text))
    return ids


def tex_table_ids(workdir: Path) -> set[str]:
    ids: set[str] = set()
    paths = [workdir / "main.tex"] + sorted((workdir / "sections").rglob("*.tex"))
    for path in paths:
        if path.is_file() and not path.name.endswith(".proc.tex"):
            ids.update(re.findall(r"\\label\{tab:([^}]+)\}", path.read_text(encoding="utf-8")))
    return ids


def audit(workdir: Path) -> dict[str, Any]:
    issues: list[str] = []
    research = workdir / "research"
    state = read_object(research / "research_state.json", issues)
    contract_id = state.get("active", {}).get("publication_contract_id")
    if not contract_id:
        issues.append("active publication contract is missing")
        contract = {}
    else:
        contract = read_object(research / "contracts" / f"{contract_id}.json", issues)
    expected_sections = {
        str(item.get("section_id")) for item in contract.get("section_plan", [])
        if isinstance(item, dict) and item.get("section_id")
    }
    if len(expected_sections) != len(contract.get("section_plan", [])):
        issues.append("publication contract section IDs are missing or duplicated")
    expected_items = contract.get("figure_plan", []) if isinstance(contract.get("figure_plan"), list) else []
    expected = {str(item.get("figure_id")) for item in expected_items if isinstance(item, dict) and item.get("figure_id")}
    if len(expected) != len(expected_items):
        issues.append("publication contract figure IDs are missing or duplicated")

    blueprint = read_object(workdir / "blueprint.json", issues)
    blueprint_sections = set(blueprint.get("sections", {})) if isinstance(blueprint.get("sections"), dict) else set()
    section_files = {
        path.relative_to(workdir / "sections").with_suffix("").as_posix()
        for path in (workdir / "sections").rglob("*.tex") if not path.name.endswith(".proc.tex")
    } if (workdir / "sections").is_dir() else set()
    main_text = (workdir / "main.tex").read_text(encoding="utf-8") if (workdir / "main.tex").is_file() else ""
    main_includes = set(re.findall(r"\\(?:input|include)\{sections/([^}]+)\}", main_text))
    for name, actual in (("blueprint", blueprint_sections), ("section files", section_files), ("main.tex includes", main_includes)):
        if actual != expected_sections:
            issues.append(f"section ID set mismatch for {name}: missing={sorted(expected_sections - actual)} extra={sorted(actual - expected_sections)}")
    blueprint_ids = blueprint_figure_ids(blueprint)
    routing = read_object(research / "manuscript" / "figure-routing.json", issues)
    routes = routing.get("figures", []) if isinstance(routing.get("figures"), list) else []
    routing_ids = {str(item.get("figure_id")) for item in routes if isinstance(item, dict) and item.get("figure_id")}
    manifest = read_object(workdir / "figures" / "figures.manifest.json", issues)
    manifest_items = manifest.get("figures", []) if isinstance(manifest.get("figures"), list) else []
    manifest_ids = {str(item.get("figure_id") or item.get("label")) for item in manifest_items if isinstance(item, dict) and (item.get("figure_id") or item.get("label"))}
    tex_ids = tex_figure_ids(workdir)
    sets = {"blueprint": blueprint_ids, "routing": routing_ids, "manifest": manifest_ids, "latex": tex_ids}
    for name, actual in sets.items():
        if actual != expected:
            issues.append(f"figure ID set mismatch for {name}: missing={sorted(expected - actual)} extra={sorted(actual - expected)}")

    expected_tables = {
        str(item.get("table_id")) for item in contract.get("table_plan", [])
        if isinstance(item, dict) and item.get("table_id")
    }
    if len(expected_tables) != len(contract.get("table_plan", [])):
        issues.append("publication contract table IDs are missing or duplicated")
    expected_table_count = int(contract.get("targets", {}).get("table_count", -1))
    if len(expected_tables) != expected_table_count:
        issues.append(
            f"table count differs from frozen target: actual={len(expected_tables)} expected={expected_table_count}"
        )
    for name, actual in (("blueprint", blueprint_table_ids(blueprint)), ("latex", tex_table_ids(workdir))):
        if actual != expected_tables:
            issues.append(f"table ID set mismatch for {name}: missing={sorted(expected_tables - actual)} extra={sorted(actual - expected_tables)}")

    expected_total = int(contract.get("targets", {}).get("figure_count", -1))
    actual_counts = {
        "measured_evidence": 0, "original_observation": 0,
        "exact_structure": 0, "explanatory_synthesis": 0, "total": len(expected_items),
    }
    for item in expected_items:
        kind = item.get("class") if isinstance(item, dict) else None
        if kind in actual_counts:
            actual_counts[kind] += 1
    if actual_counts["total"] != expected_total:
        issues.append(f"figure count differs from frozen target: actual={actual_counts['total']} expected={expected_total}")

    route_by_id = {item.get("figure_id"): item for item in routes if isinstance(item, dict)}
    manifest_by_id = {item.get("figure_id") or item.get("label"): item for item in manifest_items if isinstance(item, dict)}
    for planned in expected_items:
        figure_id = planned["figure_id"]
        route = route_by_id.get(figure_id, {})
        published = manifest_by_id.get(figure_id, {})
        for source, item in (("routing", route), ("manifest", published)):
            if item.get("class") != planned.get("class") or item.get("route") != planned.get("route"):
                issues.append(f"{figure_id}: {source} class/route differs from publication contract")
            if item.get("source_of_truth") != planned.get("source_of_truth"):
                issues.append(f"{figure_id}: {source} source_of_truth differs from publication contract")
            if set(item.get("claim_ids") or []) != set(planned.get("claim_ids") or []):
                issues.append(f"{figure_id}: {source} claim bindings differ from publication contract")
        expected_route = {
            "measured_evidence": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE",
            "original_observation": "ORIGINAL_EVIDENCE",
            "exact_structure": "DOMAIN_NATIVE",
            "explanatory_synthesis": "PAPERBANANA_REQUIRED",
        }.get(planned.get("class"))
        if not expected_route or planned.get("route") != expected_route:
            issues.append(f"{figure_id}: class/route violates source-of-truth routing")
        if planned.get("class") == "explanatory_synthesis":
            status = route.get("drawai_status")
            if status not in {"AVAILABLE_REQUIRED", "UNAVAILABLE_EVIDENCED_SKIP"}:
                issues.append(f"{figure_id}: DrawAI availability status is missing")
            if published.get("drawai_status") != status:
                issues.append(f"{figure_id}: manifest DrawAI status differs from routing preflight")

    return {
        "ok": not issues,
        "publication_contract_id": contract_id,
        "expected_figure_ids": sorted(expected),
        "sets": {name: sorted(value) for name, value in sets.items()},
        "expected_count": expected_total,
        "actual_counts": actual_counts,
        "issues": issues,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: publication_audit.py <workdir>"}))
        return 2
    report = audit(Path(sys.argv[1]).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
