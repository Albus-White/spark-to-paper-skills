#!/usr/bin/env python3
"""Paper Jury reader — a manuscript directory with `.paper-review/` turned into
courtroom JSON.

Paper Jury is a pre-submission adversarial peer-review courtroom: every reviewer
complaint is put on trial and gets one of three verdicts (valid-fixable /
author-required / invalid-drop). Its durable state is the LEDGER; the per-stage
workflow outputs (reviewers, coverage, trials, clerk) and deterministic side
artifacts (journal, spine, compile, compliance) land beside it.

Every function reads a file the tool already wrote and returns plain JSON-able
data. Missing file -> {} / [] / null — never a fabricated value. In particular
`compile()` keeps `compiled: null` as null ("compile not run / no toolchain"),
which is a real state the GUI must not paint green.

`.paper-review/` holds the courtroom state; RUN_REPORT.md and run-stages.json
sit at the manuscript-dir root (matching the dogfood sample layout).

stdlib only.
"""
from __future__ import annotations
import json
import re
import sys
from collections import Counter
from pathlib import Path

REVIEW_DIRNAME = ".paper-review"

# ACTIVE-and-gate-blocking statuses: a run cannot complete while a MAJOR sits in
# any of these. author-required / queued / dropped / closed do NOT block.
GATE_BLOCKING = {"raised", "in-trial", "re-trial", "valid-fixable"}


# ---------------------------------------------------------------- io helpers

def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def _read_jsonl(p: Path):
    """One JSON object per line; a malformed line is skipped, not fatal."""
    rows = []
    for line in _read_text(p).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _rdir(mdir) -> Path:
    return Path(mdir) / REVIEW_DIRNAME


# ---------------------------------------------------------------- markdown tables

_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")


def _row_cells(line: str):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _md_tables(text: str):
    """Every GitHub-pipe table as {title, columns, rows} where rows is a list of
    cell-lists (cells kept verbatim, markdown and all). title = the nearest
    preceding heading or **bold** line — how RUN_REPORT labels its tables."""
    lines, tables, title, i = text.splitlines(), [], "", 0
    while i < len(lines):
        line = lines[i]
        h = _HEAD.match(line)
        if h:
            title = h.group(2).strip()
            i += 1
            continue
        b = re.match(r"^\s*\*\*(.+?)\*\*\s*$", line)
        if b:
            title = b.group(1).strip()
            i += 1
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if line.lstrip().startswith("|") and "-" in nxt and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", nxt):
            cols = _row_cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_row_cells(lines[i]))
                i += 1
            tables.append({"title": title, "columns": cols, "rows": rows})
            continue
        i += 1
    return tables


# ---------------------------------------------------------------- public API

def ledger(mdir) -> dict:
    """The spine: LEDGER.json verbatim ({meta, issues}) plus derived lane counts
    and the completion gate. gatePass = zero gate-blocking active MAJORs."""
    data = _read_json(_rdir(mdir) / "LEDGER.json")
    if not isinstance(data, dict):
        return {"present": False, "meta": {}, "issues": [], "gatePass": None}
    issues = data.get("issues") or []
    by_status = Counter(str(i.get("status")) for i in issues)
    by_verdict = Counter(str(i.get("verdict")) for i in issues if i.get("verdict"))
    by_significance = Counter(str(i.get("significance")) for i in issues)
    by_kind = Counter(str(i.get("kind")) for i in issues)
    blocking = [i.get("id") for i in issues
                if i.get("significance") == "major" and i.get("status") in GATE_BLOCKING]
    return {
        "present": True,
        "schema": data.get("schema"),
        "meta": data.get("meta") or {},
        "issues": issues,
        "counts": {
            "total": len(issues),
            "by_status": dict(by_status),
            "by_verdict": dict(by_verdict),
            "by_significance": dict(by_significance),
            "by_kind": dict(by_kind),
        },
        "gate_blocking_majors": blocking,
        "gatePass": len(blocking) == 0,
        "revision_inbox": [i.get("id") for i in issues if i.get("drafted_patch")],
        "author_queue": [i.get("id") for i in issues
                         if i.get("status") in ("author-required", "queued")],
    }


def journal(mdir) -> list:
    """journal.jsonl — every applied edit as an atomic reversible unit (the
    revision-history feed with per-edit undo)."""
    return _read_jsonl(_rdir(mdir) / "journal.jsonl")


def spine(mdir) -> dict:
    """spine.json — the frozen claim sentences a fix must not drift."""
    data = _read_json(_rdir(mdir) / "spine.json")
    return data if isinstance(data, dict) else {}


def compile(mdir) -> dict:  # noqa: A001 (public name is part of the route contract)
    """compile.json — the build-status banner. `compiled: null` is honest
    UNKNOWN (no toolchain) and is preserved as null, never coerced to a verdict."""
    data = _read_json(_rdir(mdir) / "compile.json")
    if not isinstance(data, dict):
        return {"present": False, "compiled": None}
    return {"present": True, **data}


def compliance(mdir) -> dict:
    """compliance.json — the desk-reject shield checklist (pass/warn per rule)."""
    data = _read_json(_rdir(mdir) / "compliance.json")
    return data if isinstance(data, dict) else {}


def stages(mdir) -> dict:
    """run-stages.json — the per-stage workflow outputs: reviewer persona cards,
    reviewer x section coverage_flags, per-charge trials, and the clerk block."""
    data = _read_json(Path(mdir) / "run-stages.json")
    return data if isinstance(data, dict) else {}


_COUNT_RE = re.compile(
    r"(\d+)\s+reviewer weaknesses.*?(\d+)\s+issues.*?"
    r"(\d+)\s+applied\s*/\s*(\d+)\s+queued\s*/\s*(\d+)\s+dropped", re.S | re.I)
_PAGES_RE = re.compile(r"(\d+)\s*pp", re.I)


def run_report(mdir) -> dict:
    """Parse RUN_REPORT.md into {summary_counts, tables}. The 152 -> 55 ->
    26/10/19 taxonomy is pulled from the ledger line; the F/A/B defect tables are
    parsed generically (title from each `## Table N` heading)."""
    text = _read_text(Path(mdir) / "RUN_REPORT.md")
    if not text.strip():
        return {"present": False, "summary_counts": {}, "tables": []}
    counts = {}
    m = _COUNT_RE.search(text)
    if m:
        counts = {"weaknesses": int(m.group(1)), "issues": int(m.group(2)),
                  "applied": int(m.group(3)), "queued": int(m.group(4)),
                  "dropped": int(m.group(5))}
    pages = _PAGES_RE.findall(text)
    if pages:
        counts["pages"] = int(pages[-1])            # the revised-draft page count
    return {"present": True, "summary_counts": counts, "tables": _md_tables(text)}


# ---------------------------------------------------------------- smoke test

def _smoke():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    mdir = Path("C:/Users/terry/AppData/Local/Temp/claude/D--paper-spark/"
                "c6c7ab12-839a-48ae-93db-6c98e72d01f4/scratchpad/fixtures/jury")
    print(f"jury fixture: {mdir}\n  exists={mdir.is_dir()}")

    led = ledger(mdir)
    print(f"ledger: {led['counts']['total']} issues  gatePass={led['gatePass']}  "
          f"blocking={led['gate_blocking_majors']}")
    print(f"  by_status={led['counts']['by_status']}")
    print(f"  by_verdict={led['counts']['by_verdict']}")
    print(f"  revision_inbox={len(led['revision_inbox'])}  author_queue={led['author_queue']}")

    jr = journal(mdir)
    print(f"journal: {len(jr)} applied edits  first={jr[0]['jid'] if jr else None}  "
          f"last={jr[-1]['jid'] if jr else None}")

    sp = spine(mdir)
    anchors = sp.get("anchors", [])
    frozen = sum(1 for a in anchors if a.get("status") == "frozen")
    print(f"spine: {len(anchors)} anchors ({frozen} frozen, "
          f"{sum(1 for a in anchors if not a.get('located'))} not-located)")

    cp = compile(mdir)
    print(f"compile: compiled={cp.get('compiled')} pages={cp.get('pages')} "
          f"errors={len(cp.get('errors', []))} overfull={cp.get('overfull')}")

    cm = compliance(mdir)
    checks = cm.get("checks", [])
    print(f"compliance: overall={cm.get('overall')} checks={len(checks)} "
          f"warn={sum(1 for c in checks if c.get('status') == 'warn')}")

    st = stages(mdir)
    print(f"stages: reviewers={len(st.get('reviewers', []))} "
          f"coverage_flags={len(st.get('coverage_flags', []))} "
          f"trials={len(st.get('trials', []))} converged={st.get('clerk', {}).get('converged')}")

    rr = run_report(mdir)
    print(f"run_report: summary={rr['summary_counts']}  tables={len(rr['tables'])} "
          f"({[t['title'][:16] for t in rr['tables']]})")


if __name__ == "__main__":
    _smoke()
