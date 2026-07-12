#!/usr/bin/env python3
"""Validate bibliography structure before manuscript sections exist."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED_VENUE = ("journal", "booktitle", "publisher", "howpublished")
FIELD = re.compile(r'(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|"([^"]*)")\s*,?')


def parse_bib(text: str) -> dict[str, list[tuple[str, dict[str, str]]]]:
    entries: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for match in re.finditer(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\}", text, re.S):
        entry_type, key, body = match.group(1).lower(), match.group(2).strip(), match.group(3)
        fields = {name.lower(): (brace or quoted) for name, brace, quoted in FIELD.findall(body)}
        entries.setdefault(key, []).append((entry_type, fields))
    return entries


def validate(entries: dict[str, list[tuple[str, dict[str, str]]]]) -> list[dict]:
    issues: list[dict] = []
    if not entries:
        return [{"rule": "empty_or_unparseable_bibliography"}]
    for key, records in entries.items():
        if len(records) > 1:
            issues.append({"rule": "duplicate_key", "key": key})
            continue
        _, fields = records[0]
        missing = []
        if not fields.get("title"): missing.append("title")
        if not fields.get("author"): missing.append("author")
        if not fields.get("year"): missing.append("year")
        if not any(fields.get(name) for name in REQUIRED_VENUE): missing.append("venue")
        if not (fields.get("doi") or fields.get("url") or fields.get("eprint")): missing.append("doi/url/eprint")
        if missing:
            issues.append({"rule": "incomplete_entry", "key": key, "missing": missing})
    return issues


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: bib_integrity_lint.py <workdir>"}))
        return 2
    workdir = Path(sys.argv[1]).resolve()
    path = workdir / "refs.bib"
    if not path.is_file():
        report = {"ok": False, "n_entries": 0, "issues": [{"rule": "missing_refs_bib"}]}
    else:
        entries = parse_bib(path.read_text(encoding="utf-8"))
        issues = validate(entries)
        report = {"ok": not issues, "n_entries": len(entries), "issues": issues}
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
