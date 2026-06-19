#!/usr/bin/env python3
"""kg_lint.py — validate a built KG dir (deterministic gate).

    python3 kg_lint.py <kg_dir>

Checks node/edge schema completeness and reports tier distribution, so a
half-built or empty-field KG fails loudly before ts-idea2story tries to recall over it.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REL = {"uses_pattern", "in_domain", "belongs_to", "works_well_in"}


def load(d, name):
    p = Path(d) / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: kg_lint.py <kg_dir>"})); sys.exit(2)
    d = Path(sys.argv[1])
    issues = []
    papers = load(d, "nodes_paper") or []
    patterns = load(d, "nodes_pattern")
    edges = load(d, "edges")
    if patterns is None:
        issues.append("nodes_pattern.json missing")
    if edges is None:
        issues.append("edges.json missing")
    patterns = patterns or []
    edges = edges or []

    paper_ids = {p.get("paper_id") for p in papers}
    for pat in patterns:
        pid = pat.get("pattern_id", "?")
        for f in ("name", "summary", "exemplar_paper_ids", "domain"):
            if not pat.get(f):
                issues.append(f"pattern {pid}: empty/missing {f}")
        for ex in pat.get("exemplar_paper_ids", []):
            if ex not in paper_ids:
                issues.append(f"pattern {pid}: exemplar {ex} not a known paper")
    for e in edges:
        if e.get("relation") not in REL:
            issues.append(f"edge with unknown relation: {e.get('relation')}")
        if not e.get("source") or not e.get("target"):
            issues.append(f"edge missing source/target: {e}")

    tiers = {}
    for pat in patterns:
        tiers[pat.get("tier", "")] = tiers.get(pat.get("tier", ""), 0) + 1

    report = {"ok": not issues, "counts": {"papers": len(papers), "patterns": len(patterns), "edges": len(edges)},
              "tier_distribution": tiers, "n_issues": len(issues), "issues": issues[:40]}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if not issues else 1)


if __name__ == "__main__":
    main()
