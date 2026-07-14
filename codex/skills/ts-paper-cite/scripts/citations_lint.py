#!/usr/bin/env python3
"""Validate deterministic citation wiring after manuscript sections exist.

Scientific relevance and claim support are judged by the main model from paper text and source
material. This linter checks only facts a parser can establish without pretending to understand them.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bib_integrity_lint import parse_bib, validate as validate_bib


def publication_context(workdir: Path) -> tuple[int, set[str], list[dict]]:
    issues: list[dict] = []
    research = workdir / "research"
    state_path = research / "research_state.json"
    if not state_path.is_file():
        return 0, set(), [{"rule": "missing_research_lifecycle"}]
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        contract_id = state.get("active", {}).get("publication_contract_id")
        if not contract_id:
            return 0, set(), [{"rule": "missing_active_publication_contract"}]
        contract_path = research / "contracts" / f"{contract_id}.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        target = int(contract["targets"]["minimum_unique_cited_references"])
        coverage_path = research / "manuscript" / "bibliography-coverage.json"
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        planned = set(coverage["planned_citation_keys"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return 0, set(), [{"rule": "invalid_publication_citation_contract", "detail": str(exc)}]
    return target, planned, issues


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: citations_lint.py <workdir>"}))
        return 2
    workdir = Path(sys.argv[1]).resolve()
    refs = workdir / "refs.bib"
    sections = workdir / "sections"
    if not refs.is_file() or not sections.is_dir():
        missing = [name for name, path in (("refs.bib", refs), ("sections", sections)) if not path.exists()]
        print(json.dumps({"ok": False, "issues": [{"rule": "missing_required_artifact", "items": missing}]}, indent=2))
        return 1
    entries = parse_bib(refs.read_text(encoding="utf-8"))
    issues = validate_bib(entries)
    target, planned_keys, contract_issues = publication_context(workdir)
    issues.extend(contract_issues)
    cited: set[str] = set()
    cited_by_section: dict[str, set[str]] = {}
    tex_files = [workdir / "main.tex"] if (workdir / "main.tex").is_file() else []
    tex_files.extend(sorted(sections.rglob("*.tex")))
    for tex in tex_files:
        if tex.name.endswith(".proc.tex"):
            continue
        bucket = cited_by_section.setdefault(tex.relative_to(workdir).as_posix(), set())
        pattern = r"\\(?:cite[tp]?|citeauthor|citeyear|parencite|textcite|autocite)\*?(?:\[[^]]*\]){0,2}\{([^}]*)\}"
        for match in re.finditer(pattern, tex.read_text(encoding="utf-8")):
            for raw_key in match.group(1).split(","):
                key = raw_key.strip()
                if key:
                    cited.add(key); bucket.add(key)
    bibkeys = set(entries)
    for key in sorted(cited - bibkeys):
        issues.append({"rule": "cite_without_entry", "key": key})
    if len(cited) < target:
        issues.append({"rule": "unique_cited_reference_floor", "actual": len(cited), "required": target})
    unplanned = sorted(cited - planned_keys) if planned_keys else []
    if unplanned:
        issues.append({"rule": "cited_key_missing_from_coverage", "keys": unplanned})
    warnings = [{"rule": "uncited_entry", "key": key} for key in sorted(bibkeys - cited)]
    if not cited:
        warnings.append({"rule": "no_citations_in_current_draft", "note": "Main-model review must decide whether the paper actually requires citations."})
    report = {
        "ok": not issues,
        "n_entries": len(entries),
        "n_cited": len(cited),
        "required_unique_cited_references": target,
        "issues": issues,
        "warnings": warnings,
        "cites_per_section": {key: len(value) for key, value in sorted(cited_by_section.items())},
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
