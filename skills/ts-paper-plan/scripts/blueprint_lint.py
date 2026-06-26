#!/usr/bin/env python3
"""Validate (and optionally repair) blueprint.json — TEMPLATE-DRIVEN.

    python blueprint_lint.py <workdir> [--fix]

Reads `template.json` from the workdir (the plan stage copies it in; falls back to the
bundled `ts_iieta` spec). The canonical section list, section titles, per-section word
targets, allowed citation types, the required contributions count, and the result-table
count all come from the template spec — they are NO LONGER hardcoded to Traitement du
Signal. The self-heal / alias-remap logic is template-independent and unchanged.

Hard-checks (auto-repaired with --fix):
  - citation_types ⊆ spec.citations.types; aliases remapped (DATASET->METRIC, METHOD->CORE, ...).
  - all template sections present (self-heal missing ones with spec defaults).
  - every section target_words is a 2-tuple [min,max] (default from spec).
  - experiments has exactly the spec's result-table count; total planned figures >= the template
    figures.min floor (whole-paper, no per-section check).
  - title within spec.title limits; contributions == spec.contributions.count (skipped if 0).
"""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES_ROOT = HERE.parent.parent / "ts-paper" / "templates"

# alias remap is template-independent (maps common synonyms onto whatever the spec allows)
CLAIM_TYPE_MAP = {
    "DATASET": "METRIC", "METHOD": "CORE", "BACKGROUND": "CONTEXT",
    "COMPARISON": "BASELINE", "PRIOR": "CONTEXT", "RELATED": "CONTEXT",
    "BENCHMARK": "METRIC", "EVALUATION": "METRIC", "TERM": "DEFINITION",
}

def load_spec(wd: Path) -> dict:
    p = wd / "template.json"
    if p.exists():
        return json.loads(p.read_text())
    bundled = TEMPLATES_ROOT / "ts_iieta" / "template.json"
    if bundled.exists():
        return json.loads(bundled.read_text())
    return {}   # ultimate fallback handled by .get defaults below

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: blueprint_lint.py <workdir> [--fix]"})); sys.exit(2)
    wd = Path(sys.argv[1]).resolve()
    fix = "--fix" in sys.argv
    spec = load_spec(wd)
    bp = json.loads((wd / "blueprint.json").read_text())
    issues, repaired = [], []

    sections_spec = spec.get("sections") or []
    CANONICAL = [s["id"] for s in sections_spec] or \
                ["introduction", "related_work", "method", "experiments", "analysis", "conclusion"]
    DEFAULT_TARGETS = {s["id"]: (s.get("words") or [400, 800]) for s in sections_spec}
    DEFAULT_TITLES = {s["id"]: s.get("title", s["id"].replace("_", " ").title()) for s in sections_spec}
    ALLOWED = set((spec.get("citations") or {}).get("types") or
                  ["CORE", "CONTEXT", "BASELINE", "METRIC", "DEFINITION"])
    contrib_count = (spec.get("contributions") or {}).get("count", 3)
    title_spec = spec.get("title") or {"max_words": 14, "max_chars": 120}
    # expected number of result tables (from the experiments section recipe)
    exp_spec = next((s for s in sections_spec if s["id"] == "experiments"), {})
    expected_tables = len((exp_spec.get("recipe") or {}).get("result_tables") or [])
    # results_mode gates the data-aware table-plan acceptance; proposal mode is unchanged.
    results_mode = spec.get("results_mode", "proposal")
    tables_min = int((spec.get("tables") or {}).get("min", 0))

    secs = bp.setdefault("sections", {})
    for sid, s in secs.items():
        if not isinstance(s, dict):
            continue
        cts = s.get("citation_types", [])
        new = []
        for c in cts:
            cu = str(c).upper()
            if cu in ALLOWED:
                new.append(cu)
            elif CLAIM_TYPE_MAP.get(cu) in ALLOWED:
                new.append(CLAIM_TYPE_MAP[cu])
                if fix: repaired.append(f"{sid}.citation_types: {cu}->{CLAIM_TYPE_MAP[cu]}")
            else:
                if fix: repaired.append(f"{sid}.citation_types: drop unknown {cu}")
        if new != cts:
            (s.__setitem__("citation_types", new) if fix else issues.append(f"{sid}.citation_types invalid: {cts}"))
        tw = s.get("target_words")
        if not (isinstance(tw, (list, tuple)) and len(tw) == 2):
            d = DEFAULT_TARGETS.get(sid, [400, 800])
            if fix:
                s["target_words"] = d
                repaired.append(f"{sid}.target_words -> {d}")
            else:
                issues.append(f"{sid}.target_words not a 2-tuple: {tw}")

    for sid in CANONICAL:
        if sid not in secs:
            if fix:
                secs[sid] = {"title": DEFAULT_TITLES.get(sid, sid), "target_words": DEFAULT_TARGETS.get(sid, [400, 800]),
                             "citation_types": []}
                repaired.append(f"added missing section {sid}")
            else:
                issues.append(f"missing template section: {sid}")

    exp = secs.get("experiments", {})
    n_tab = len(exp.get("tables", []) or [])
    if results_mode == "data_aware":
        # data-aware: tables carry the EXACT data keys (rows/cols = the real method/variant + metric
        # names Claude read). Don't force the proposal shape; just enforce the tables.min floor (and
        # flag zero tables — data-aware experiments must report results).
        floor = tables_min or expected_tables
        if floor and n_tab < floor:
            issues.append(f"experiments plans {n_tab} result tables, below the template minimum of {floor}")
    elif expected_tables and n_tab not in (0, expected_tables):
        issues.append(f"experiments should plan exactly {expected_tables} result tables, found {n_tab}")
    # figure floor (whole paper): the template requires >= figures.min schematic/conceptual figures
    fig_min = (spec.get("figures") or {}).get("min", 0)
    total_figs = sum(len(s.get("figures", []) or []) for s in secs.values() if isinstance(s, dict))
    if fig_min and total_figs < fig_min:
        distribute = (spec.get("figures") or {}).get("distribute_across") or []
        where = "/".join(distribute) if distribute else "the template's figure sections"
        issues.append(f"blueprint plans {total_figs} figures, below the template minimum of {fig_min} "
                      f"— distribute schematic/conceptual/qualitative figures across {where} "
                      f"(quantitative results go in tables, not figures)")
    title = str(bp.get("paper_title", ""))
    if len(title.split()) > title_spec.get("max_words", 14) or len(title) > title_spec.get("max_chars", 120):
        issues.append(f"title too long: {len(title.split())} words / {len(title)} chars "
                      f"(max {title_spec.get('max_words',14)}w/{title_spec.get('max_chars',120)}c)")
    if contrib_count:
        nc = len(bp.get("contributions", []) or [])
        if nc != contrib_count:
            issues.append(f"contributions must be exactly {contrib_count}, found {nc}")

    if fix and repaired:
        (wd / "blueprint.json").write_text(json.dumps(bp, indent=2, ensure_ascii=False))

    report = {"ok": not issues, "template": spec.get("name", "ts_iieta"),
              "n_issues": len(issues), "issues": issues,
              "repaired": repaired, "fixed_in_place": bool(fix and repaired)}
    print(json.dumps(report, indent=2))
    sys.exit(0 if not issues else 1)

if __name__ == "__main__":
    main()
