#!/usr/bin/env python3
"""Check deterministic manuscript integrity without pretending to understand prose."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"\[\s*[XY]\s*\]|\bXX\.X\b|\[TBD\]|\[CITATION NEEDED\]", re.I)
BANNED_TOP_LEVEL = re.compile(r"\\documentclass|\\usepackage|\\begin\{document\}|\\end\{document\}")
AI_STYLE_HINTS = re.compile(
    r"\bit is worth (?:noting|mentioning|emphasi[sz]ing)\b|\bdelv(?:e|es|ing) into\b|\bin order to\b",
    re.I,
)


def word_count(text: str) -> int:
    text = re.sub(r"\\begin\{(?:table|figure|equation|align)[^}]*\}.*?\\end\{[^}]+\}", " ", text, flags=re.S)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^]]*\])?", " ", text)
    return len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text))


def environment_balance(text: str) -> list[str]:
    begins = re.findall(r"\\begin\{([^}]+)\}", text)
    ends = re.findall(r"\\end\{([^}]+)\}", text)
    issues = []
    for name in sorted(set(begins) | set(ends)):
        if begins.count(name) != ends.count(name):
            issues.append(f"environment {name} begin/end count differs")
    return issues


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: draft_lint.py <workdir>"}))
        return 2
    workdir = Path(sys.argv[1]).resolve()
    try:
        template = json.loads((workdir / "template.json").read_text(encoding="utf-8"))
        blueprint = json.loads((workdir / "blueprint.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "issues": [{"rule": "missing_or_invalid_contract", "detail": str(exc)}]}, indent=2))
        return 1
    sections_dir = workdir / "sections"
    issues: list[dict] = []
    warnings: list[dict] = []
    order = blueprint.get("section_order") or []
    for section_id in order:
        path = sections_dir / f"{section_id}.tex"
        if not path.is_file():
            issues.append({"file": path.name, "rule": "missing_section"})
            continue
        text = path.read_text(encoding="utf-8")
        for match in PLACEHOLDER.finditer(text):
            issues.append({"file": path.name, "rule": "placeholder", "snippet": match.group(0)})
        if "```" in text:
            issues.append({"file": path.name, "rule": "markdown_fence"})
        if BANNED_TOP_LEVEL.search(text):
            issues.append({"file": path.name, "rule": "top_level_latex_in_section"})
        issues.extend({"file": path.name, "rule": "unbalanced_environment", "detail": item} for item in environment_balance(text))
        section = (blueprint.get("sections") or {}).get(section_id, {})
        band = section.get("target_words")
        if isinstance(band, list) and len(band) == 2:
            count = word_count(text)
            if count < band[0] or count > band[1]:
                warnings.append({"file": path.name, "rule": "word_target_advisory", "count": count, "target": band})
        for match in AI_STYLE_HINTS.finditer(text):
            warnings.append({"file": path.name, "rule": "style_advisory", "snippet": match.group(0)})
    abstract = sections_dir / "abstract.tex"
    if not abstract.is_file():
        issues.append({"file": "abstract.tex", "rule": "missing_abstract"})
    elif PLACEHOLDER.search(abstract.read_text(encoding="utf-8")):
        issues.append({"file": "abstract.tex", "rule": "placeholder"})
    if template.get("results_mode") == "proposal":
        for section_id, section in (blueprint.get("sections") or {}).items():
            for table in section.get("tables", []) if isinstance(section, dict) else []:
                if isinstance(table, dict) and (
                    table.get("source_of_truth") == "canonical_result_facts" or table.get("fact_ids")
                ):
                    issues.append({"file": section_id, "rule": "proposal_declares_measured_result_table", "table": table.get("id")})
    report = {"ok": not issues, "issues": issues, "warnings": warnings}
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
