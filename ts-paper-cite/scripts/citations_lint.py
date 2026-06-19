#!/usr/bin/env python3
"""Lint a TS paper's citations: stub detection + cite/bib cross-check + dup keys + claims_map claim<->cite verification + template-driven coverage floor.

This is the hard gate that kills the old "title-only @misc stub" fabrication path.
Run from the working dir (containing refs.bib and sections/*.tex):

    python citations_lint.py <workdir> [--resolve]

By default it is a pure-local, offline, deterministic textual check (no network).
With --resolve (opt-in) it additionally resolves each entry's DOI via doi2bib.py:
a definitive 404 hard-fails ("doi_unresolved"); a network/5xx error degrades to a
non-fatal "doi_unverified" warning. arXiv-only entries (eprint, no doi) are skipped.

Prints a JSON report and exits non-zero if any issue is found.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

REQUIRED_VENUE = ("journal", "booktitle", "publisher", "howpublished")

HERE = Path(__file__).resolve().parent
TEMPLATES_ROOT = HERE.parent.parent / "ts-paper" / "templates"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))  # so `--resolve` can import sibling doi2bib.py

def load_spec(wd: Path) -> dict:
    p = wd / "template.json"
    if p.exists():
        return json.loads(p.read_text())
    bundled = TEMPLATES_ROOT / "ts_iieta" / "template.json"
    return json.loads(bundled.read_text()) if bundled.exists() else {}

def resolve_doi(doi: str, cache: dict) -> str:
    """Resolve a DOI via doi2bib.py's fetch() (the single Crossref impl — DRY).
    Returns 'ok' (resolved), 'dead' (definitive 404 — hard fail), or
    'unverified' (network/5xx/other — non-fatal warning). Cached per-DOI."""
    if doi in cache:
        return cache[doi]
    try:
        from doi2bib import fetch  # sibling script; HERE is on sys.path
        fetch(doi)
        result = "ok"
    except Exception as e:
        # urllib raises HTTPError (has .code) for HTTP statuses; 404 = definitive.
        code = getattr(e, "code", None)
        result = "dead" if code == 404 else "unverified"
    cache[doi] = result
    return result

_FIELD = re.compile(r'(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|"([^"]*)")\s*,?')

def parse_bib(text: str):
    entries = {}
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\}", text, re.S):
        etype, key, body = m.group(1).lower(), m.group(2).strip(), m.group(3)
        # brace-aware value capture: handles one nested {..} level (e.g. title={A {Nested} Title})
        # and "quoted" values; group 2 = brace value, group 3 = quoted value.
        fields = {f.lower(): (brace or quoted) for f, brace, quoted in _FIELD.findall(body)}
        entries.setdefault(key, []).append((etype, fields))
    return entries

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    resolve = "--resolve" in sys.argv[1:]  # opt-in; default OFF (offline/deterministic)
    if not args:
        print(json.dumps({"ok": False, "error": "usage: citations_lint.py <workdir> [--resolve]"})); sys.exit(2)
    wd = Path(args[0]).resolve()
    spec = load_spec(wd)
    bib_text = (wd / "refs.bib").read_text() if (wd / "refs.bib").exists() else ""
    entries = parse_bib(bib_text)

    issues = []
    warnings = []  # non-fatal (do not affect exit code), e.g. unverifiable DOIs offline
    # duplicate keys
    for key, lst in entries.items():
        if len(lst) > 1:
            issues.append({"rule": "duplicate_key", "key": key})
    # stub / incomplete entries
    for key, lst in entries.items():
        _, f = lst[0]
        missing = []
        if not f.get("author"): missing.append("author")
        if not f.get("year"): missing.append("year")
        if not any(f.get(v) for v in REQUIRED_VENUE): missing.append("venue")
        if not (f.get("doi") or f.get("url") or f.get("eprint")): missing.append("doi/url")
        if missing:
            issues.append({"rule": "stub_or_incomplete", "key": key, "missing": missing})

    # opt-in DOI existence gate (--resolve): a fabricated well-formed DOI is only
    # caught here. Per CITE-02, arXiv-only entries (eprint, no doi) are SKIPPED.
    if resolve:
        _cache: dict = {}
        for key, lst in entries.items():
            _, f = lst[0]
            doi = (f.get("doi") or "").strip()
            if not doi:
                continue  # url/eprint-only (incl. arXiv preprints): not a DOI gate target
            status = resolve_doi(doi, _cache)
            if status == "dead":
                issues.append({"rule": "doi_unresolved", "key": key, "doi": doi})
            elif status == "unverified":
                warnings.append({"rule": "doi_unverified", "key": key, "doi": doi,
                                 "note": "network/transient error — could not confirm; non-fatal"})

    # cite <-> bib cross-check + per-section bucketing.
    # We keep BOTH a flat `cited` set (for the global floor / orphan check) and a
    # `cited_by_section` map (section_id -> set of keys) so coverage can be enforced
    # per section, not just globally. The section_id is the file stem with any
    # `.proc` suffix stripped, so `related_work.tex` and `related_work.proc.tex`
    # collapse to one logical section `related_work` (the .proc.tex is the processed
    # mirror — counting both would double-count). This restores the source engine's
    # per-section assignment view (citation_resolver._build_assignment_index /
    # global_slot_to_section) that distillation had flattened to a single global set.
    cited = set()
    cited_by_section: dict[str, set] = {}
    for tex in sorted((wd / "sections").glob("*.tex")) if (wd / "sections").is_dir() else []:
        sec_id = re.sub(r"\.proc$", "", tex.stem)  # related_work.proc -> related_work
        bucket = cited_by_section.setdefault(sec_id, set())
        for m in re.finditer(r"\\cite[tp]?\*?\{([^}]*)\}", tex.read_text()):
            for k in m.group(1).split(","):
                if k.strip():
                    cited.add(k.strip())
                    bucket.add(k.strip())
    bibkeys = set(entries)
    for k in sorted(cited - bibkeys):
        issues.append({"rule": "cite_without_entry", "key": k})
    for k in sorted(bibkeys - cited):
        issues.append({"rule": "orphan_entry", "key": k})

    # claim->citation match verification (enforced when claims_map.json is present)
    cm_path = wd / "claims_map.json"
    GOOD = {"direct_core", "same_line_support", "core", "context", "baseline",
            "dataset", "metric", "dataset_metric", "definition"}
    BAD = {"off_topic", "adjacent", "weak", "cross_domain", "unrelated", ""}
    # where is each key ACTUALLY cited? (key -> set of section_ids). Used both for the
    # claims_map 'section' verification below and for per-section coverage.
    section_of_key: dict[str, set] = {}
    for sec_id, keys in cited_by_section.items():
        for k in keys:
            section_of_key.setdefault(k, set()).add(sec_id)

    if cm_path.exists():
        cm = json.loads(cm_path.read_text())
        for k in sorted(cited):
            e = cm.get(k)
            if not e or not e.get("claim"):
                issues.append({"rule": "cite_without_claim_justification", "key": k})
                continue
            label = str(e.get("support_label", "")).lower()
            if label in BAD or label not in GOOD:
                issues.append({"rule": "weak_claim_match", "key": k, "label": label or "missing"})
            # verify the claims_map 'section' against where the key is actually cited.
            # The source engine bound every citation marker to its assigned section and
            # flagged mismatches as `cross_section_marker_errors` (citation_resolver.py
            # :303,401-410); distillation kept the 'section' field but never checked it,
            # making it an unverified, drifting annotation. We make it auditable again.
            claimed_sec = re.sub(r"\.proc$", "", str(e.get("section", "")).strip())
            if claimed_sec:
                actual = section_of_key.get(k, set())
                if actual and claimed_sec not in actual:
                    issues.append({"rule": "claims_map_section_mismatch", "key": k,
                                   "claimed": claimed_sec, "actual": sorted(actual)})
    else:
        issues.append({"rule": "missing_claims_map",
                       "key": "claims_map.json absent — cannot verify claim<->citation matching"})

    # ---- coverage: GLOBAL floor AND per-section distribution (template-driven) ----
    # The global floor alone is a blind spot: a paper can clear 40 total cites while
    # whole body sections (experiments/analysis/conclusion) carry ZERO and related_work
    # blows past its band. The source engine never had this hole — it assigned a
    # `coverage_target` per section (citation_route.py:1024-1032) and derived a
    # per-section `unique_marker_hard_floor` (section_writer.py:952-963). We restore
    # that here as the irreducible deterministic gate, driven by template.json's
    # `citations.per_section_coverage` (already present in every template).
    cites_cfg = spec.get("citations") or {}

    # (1) global floor — unchanged: "search more broadly for REAL papers", never fabricate.
    floor = int(cites_cfg.get("floor", 40))
    if len(cited) < floor:
        issues.append({"rule": "coverage_below_floor",
                       "key": f"{len(cited)} cited refs < {floor} (template floor) — broaden the search; never fabricate"})

    # (2) per-section bands. Body sections that should carry citations but have ZERO are a
    #     HARD ERROR (a prior-work/dataset/baseline section with no evidence is broken).
    #     A non-empty section that falls OUTSIDE its [lo,hi] band is a WARNING (distribution
    #     drift — fix by rebalancing, not by fabricating). Sections legitimately citation-free
    #     in a proposal (abstract, conclusion, future_work) are exempt from the zero-error.
    per_sec = cites_cfg.get("per_section_coverage") or {}
    NO_CITE_OK = {"abstract", "conclusion", "future_work", "acknowledgments", "appendix"}
    # body sections we KNOW must be evidence-bearing even if the template gives no band
    EVIDENCE_BEARING = {"introduction", "related_work", "method", "experiments", "analysis"}
    body_secs = (set(cited_by_section) - NO_CITE_OK) | (set(per_sec) - NO_CITE_OK)
    for sec_id in sorted(body_secs):
        n = len(cited_by_section.get(sec_id, set()))
        band = per_sec.get(sec_id)
        if n == 0 and (sec_id in EVIDENCE_BEARING or sec_id in per_sec):
            issues.append({"rule": "section_zero_citations", "key": sec_id,
                           "note": "evidence-bearing body section has 0 citations — every prior-work/dataset/baseline claim must cite a real paper; broaden the search, never fabricate"})
            continue
        if band and isinstance(band, (list, tuple)) and len(band) == 2 and n:
            lo, hi = int(band[0]), int(band[1])
            if n < lo or n > hi:
                warnings.append({"rule": "section_coverage_out_of_band", "key": sec_id,
                                 "n": n, "band": [lo, hi],
                                 "note": "redistribute cites across sections (move/merge real cites; do not fabricate or delete real support)"})

    report = {"ok": not issues, "n_entries": len(entries), "n_cited": len(cited),
              "n_issues": len(issues), "issues": issues,
              "cites_per_section": {s: len(v) for s, v in sorted(cited_by_section.items())}}
    # warnings are now produced both by --resolve (unverifiable DOIs) and by the
    # per-section out-of-band check, so always surface them (non-fatal, no exit effect).
    report["n_warnings"] = len(warnings)
    report["warnings"] = warnings
    print(json.dumps(report, indent=2))
    sys.exit(0 if not issues else 1)

if __name__ == "__main__":
    main()
