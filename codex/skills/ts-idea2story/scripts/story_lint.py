#!/usr/bin/env python3
"""story_lint.py — validate the 8-field Story (deterministic gate before story->paper handoff).

    python3 story_lint.py <workdir>     # validates <workdir>/story.json

The Story is the structured proposal ts-paper consumes. This checks the schema is complete and
not polluted by LLM schema-echo noise (a product failure mode), so a malformed story fails loudly.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

FIELDS = ["title", "abstract", "problem_framing", "gap_pattern", "solution",
          "method_skeleton", "innovation_claims", "experiments_plan"]
HYPOTHESIS_FIELDS = ["problem", "hypothesis", "proposed_mechanism", "scope", "assumptions",
                     "falsifiers", "alternative_explanations", "minimum_validation_path"]
NOISE = {"string", "todo", "tbd", "n/a", "none", "...", "<...>", "placeholder", "lorem ipsum"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: story_lint.py <workdir>"})); sys.exit(2)
    wd = Path(sys.argv[1]).resolve()
    sp = wd / "story.json"
    if not sp.exists():
        print(json.dumps({"ok": False, "error": f"no story.json in {wd}"})); sys.exit(2)
    s = json.loads(sp.read_text())
    issues = []

    for f in FIELDS:
        if f not in s:
            issues.append(f"missing field: {f}"); continue
        v = s[f]
        if f == "innovation_claims":
            if not isinstance(v, list) or not v:
                issues.append("innovation_claims must be a non-empty list")
            elif any(not str(x).strip() or str(x).strip().lower() in NOISE for x in v):
                issues.append("innovation_claims has empty/placeholder entries")
        else:
            if not isinstance(v, str):
                issues.append(f"{f} must be a string")
            elif not v.strip():
                issues.append(f"{f} is empty")
            elif v.strip().lower() in NOISE:
                issues.append(f"{f} is a placeholder/noise token: {v!r}")

    hypothesis = s.get("research_hypothesis")
    if not isinstance(hypothesis, dict):
        issues.append("research_hypothesis must be an object")
    else:
        for field in HYPOTHESIS_FIELDS:
            value = hypothesis.get(field)
            if value in (None, "", []):
                issues.append(f"research_hypothesis.{field} is required")
        for field in ("assumptions", "falsifiers", "alternative_explanations"):
            if field in hypothesis and not isinstance(hypothesis[field], list):
                issues.append(f"research_hypothesis.{field} must be a list")
    queries = s.get("benchmark_queries")
    if not isinstance(queries, list) or not queries:
        issues.append("benchmark_queries must be a non-empty list")

    warnings = []
    # These are editing signals only; concise or non-English methods and titles remain valid.
    ms = str(s.get("method_skeleton", ""))
    if ms and len(ms.split()) < 12:
        warnings.append("method_skeleton is concise; main-model review should confirm it is sufficiently specified")
    t = str(s.get("title", ""))
    if t and (len(t.split()) > 20 or len(t) > 180):
        warnings.append(f"title is long ({len(t.split())} whitespace-delimited words); venue review decides acceptability")
    # Numbers may be protocol constants, cited facts, mathematical parameters, targets, or measured
    # findings. A regex cannot distinguish them. Surface them for semantic provenance review only.
    pieces = [str(s.get(f, "")) for f in FIELDS if f != "innovation_claims"]
    pieces += [str(x) for x in (s.get("innovation_claims") or [])]
    if any(re.search(r"\d", piece) for piece in pieces):
        warnings.append("story contains numbers; main-model review must classify and source each result-like statement")

    report = {"ok": not issues, "n_issues": len(issues), "issues": issues,
              "fields_present": [f for f in FIELDS if f in s],
              "hypothesis_fields_present": [f for f in HYPOTHESIS_FIELDS if isinstance(hypothesis, dict) and f in hypothesis],
              "warnings": warnings}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if not issues else 1)


if __name__ == "__main__":
    main()
