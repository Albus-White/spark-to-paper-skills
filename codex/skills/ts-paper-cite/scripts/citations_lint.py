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
    cited: set[str] = set()
    cited_by_section: dict[str, set[str]] = {}
    for tex in sorted(sections.glob("*.tex")):
        if tex.name.endswith(".proc.tex"):
            continue
        bucket = cited_by_section.setdefault(tex.stem, set())
        for match in re.finditer(r"\\cite[tp]?\*?\{([^}]*)\}", tex.read_text(encoding="utf-8")):
            for raw_key in match.group(1).split(","):
                key = raw_key.strip()
                if key:
                    cited.add(key); bucket.add(key)
    bibkeys = set(entries)
    for key in sorted(cited - bibkeys):
        issues.append({"rule": "cite_without_entry", "key": key})
    warnings = [{"rule": "uncited_entry", "key": key} for key in sorted(bibkeys - cited)]
    if not cited:
        warnings.append({"rule": "no_citations_in_current_draft", "note": "Main-model review must decide whether the paper actually requires citations."})
    report = {
        "ok": not issues,
        "n_entries": len(entries),
        "n_cited": len(cited),
        "issues": issues,
        "warnings": warnings,
        "cites_per_section": {key: len(value) for key, value in sorted(cited_by_section.items())},
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
