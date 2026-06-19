#!/usr/bin/env python3
"""Validate a template spec before the suite uses it — fail loudly, not silently.

    python template_lint.py <template.json | templates/<name>/ | workdir>

Checks the required keys are present and internally consistent so a misconfigured
template errors up-front instead of degrading mid-pipeline. Prints a JSON report.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REQUIRED_TOP = ["name", "engine", "sections", "abstract", "citations"]
VALID_CITE_STYLE = {"numeric", "author_year"}


def find_spec(arg: str) -> Path:
    p = Path(arg).resolve()
    if p.is_dir():
        return p / "template.json"
    return p


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: template_lint.py <template.json|dir|workdir>"})); sys.exit(2)
    sp = find_spec(sys.argv[1])
    if not sp.exists():
        print(json.dumps({"ok": False, "error": f"no template.json at {sp}"})); sys.exit(2)
    spec = json.loads(sp.read_text())
    issues = []

    for k in REQUIRED_TOP:
        if k not in spec:
            issues.append(f"missing top-level key: {k}")

    eng = spec.get("engine") or {}
    if not eng.get("documentclass"):
        issues.append("engine.documentclass missing")
    tmpl = eng.get("main_template", "main.tex.tmpl")
    if not (sp.parent / tmpl).exists():
        issues.append(f"engine.main_template '{tmpl}' not found next to template.json")
    for a in eng.get("assets", []):
        if not (sp.parent / a).exists():
            issues.append(f"engine asset '{a}' not found next to template.json")

    sections = spec.get("sections") or []
    ids = [s.get("id") for s in sections]
    if not sections:
        issues.append("sections is empty")
    if len(ids) != len(set(ids)):
        issues.append(f"duplicate section ids: {ids}")
    for s in sections:
        w = s.get("words")
        if not (isinstance(w, (list, tuple)) and len(w) == 2 and w[0] <= w[1]):
            issues.append(f"section {s.get('id')}: words must be [min,max] with min<=max, got {w}")

    wo = spec.get("writing_order") or []
    allowed_wo = set(ids) | {"abstract"}
    for sid in wo:
        if sid not in allowed_wo:
            issues.append(f"writing_order has unknown id '{sid}' (not a section or 'abstract')")

    cite = spec.get("citations") or {}
    if cite.get("style") not in VALID_CITE_STYLE:
        issues.append(f"citations.style must be one of {sorted(VALID_CITE_STYLE)}, got {cite.get('style')!r}")
    if not isinstance(cite.get("floor", 0), int):
        issues.append("citations.floor must be an int")
    if not (cite.get("types")):
        issues.append("citations.types must be a non-empty list")

    # template main_template should reference the core tokens
    if (sp.parent / tmpl).exists():
        t = (sp.parent / tmpl).read_text()
        for tok in ("@@title@@", "@@abstract@@", "@@sections@@"):
            if tok not in t:
                issues.append(f"main_template missing required token {tok}")

    report = {"ok": not issues, "name": spec.get("name"), "n_issues": len(issues), "issues": issues}
    print(json.dumps(report, indent=2))
    sys.exit(0 if not issues else 1)


if __name__ == "__main__":
    main()
