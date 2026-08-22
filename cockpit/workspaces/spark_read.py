#!/usr/bin/env python3
"""Spark reader — a paper workdir / run root turned into reading + governance JSON.

Two artifact families live on disk. The **paper workdir** is the read content
(blueprint, sections, main.pdf, figures, facts, claims map, report.html); the
**run root's `.research/`** is the governance/telemetry layer (LEDGER, stage
seals, DECISION_QUEUE, E14 metrics, claim ledgers, dead-ends, STATE). The paper
workdir nests inside the run root that owns `.research/`, so the governance
functions walk up 1-2 parents to find it.

`report()` reuses build_report.py's own `collect_*` functions (the dashboard's
ready-made data API) via `runner._build_report()`, guarding each collector so a
broken one hides its own panel rather than the page. Everything else parses the
files directly, faithful to the writers' grammars: the claim/dead-end regexes
mirror `run_ledger.py`; the decision-queue open/state logic mirrors
`decision_queue.py` (a block-waiver clears every open row at its position).

Honest degradation throughout: missing file -> {} / [] / null / "not run".

stdlib only.
"""
from __future__ import annotations
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

REVIEW_DIRNAME = ".paper-review"

# ---- writer grammars, copied verbatim from run_ledger.py so a row parses here
#      exactly as it does there ------------------------------------------------
BELIEFS_REV_RE = re.compile(r"^beliefs-rev: k=(\d+) cards-covered=(\d+)\s*$", re.M)
CLAIM_RE = re.compile(
    r"^claim: id=(\S+) dir=(\S+) status=(hypothesis|supported|refuted|inconclusive) "
    r"since=(\S+) council=(\S+) facts=(\S+) margin=(\S+) provenance=(\S+)\s*$", re.M)
OPEN_RE = re.compile(r"^open: id=(\S+) kind=(backstop|unreviewed-fix) ref=(\S+)", re.M)
DEADEND_RE = re.compile(r"^dead-end: id=(\S+) dir=(\S+) run=(\S+) support=(explicit|inferred)\s*$")
STATE_SENTINEL_RE = re.compile(r"^state:(?: (?:round|active|mode|phase)=\S+)+[^\S\n]*$", re.M)

# decision_queue.py settlement vocabulary
SETTLEMENT_TYPES = {"disposition", "block-waiver"}


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


def _find_research(start) -> Path | None:
    """The `.research/` that owns this dir. Accepts the run root, the nested paper
    workdir, or the `.research` dir itself; walks up 1-2 parents."""
    p = Path(start).resolve()
    if p.name == ".research" and p.is_dir():
        return p
    for d in (p, p.parent, p.parent.parent):
        r = d / ".research"
        if r.is_dir():
            return r
    return None


def _find_review(start) -> Path | None:
    """The `.paper-review/` bound to this run, or None. Same walk as
    `_find_research`: accepts the run root, the nested paper workdir, or the
    `.paper-review` dir itself, climbing up 1-2 parents. A run that was never put
    through Paper Jury simply has none — reported as absent, never invented."""
    p = Path(start).resolve()
    if p.name == REVIEW_DIRNAME and p.is_dir():
        return p
    for d in (p, p.parent, p.parent.parent):
        r = d / REVIEW_DIRNAME
        if r.is_dir():
            return r
    return None


# ---------------------------------------------------------------- spark variant
#
# The public/older Spark (v1.1.0) is LINEAR: no `.research/` engine layer, no
# `.paper-review/` edit journal, proposal mode by default (no results.facts.json).
# The variant probe lets each payload say WHICH spark produced this run so the GUI
# can degrade honestly — a real, readable linear run is FLAT, distinct from a dir
# it simply could not read.

def _has_research(start) -> bool:
    """This run has a `.research/` engine subtree (the newer, engine-driven Spark)."""
    return _find_research(start) is not None


def _has_edit_journal(start) -> bool:
    """This run carries a `.paper-review/journal.jsonl` edit journal (Paper Jury)."""
    review = _find_review(start)
    return review is not None and (review / "journal.jsonl").is_file()


def _spark_variant(start) -> str:
    """"engine" when a `.research/` engine layer owns this run, else "flat" (a
    linear/public Spark run that never had a research engine)."""
    return "engine" if _has_research(start) else "flat"


# ---------------------------------------------------------------- report panels

def _blueprint(wd: Path) -> dict:
    bp = _read_json(wd / "blueprint.json")
    if not isinstance(bp, dict) or not bp:
        return {"present": False}
    contribs = bp.get("contributions") or []
    return {
        "present": True,
        "paper_title": bp.get("paper_title"),
        "keywords": bp.get("keywords"),
        "contributions": contribs,
        "n_contributions": len(contribs),
        "sections": list((bp.get("sections") or {}).keys()) or (bp.get("section_order") or []),
        "n_sections": len(bp.get("section_order") or bp.get("sections") or []),
        "n_notation": len(bp.get("notation") or {}),
        "n_terminology": len(bp.get("terminology") or {}),
        "experiment_design": bp.get("experiment_design") or {},
    }


def _load_runner():
    try:
        from .. import runner            # package context (imported by serve.py)
        return runner
    except (ImportError, ValueError):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import runner                    # `python workspaces/spark_read.py`
        return runner


def report(workdir) -> dict:
    """A dict of dashboard panels, computed by build_report.py's own collectors.
    Each collector is guarded independently: a collector that raises hides its
    panel (value None + an entry in `errors`), never the whole page. When
    build_report is unavailable, {available: false}."""
    wd = Path(workdir)
    variant = _spark_variant(wd)
    try:
        runner = _load_runner()
    except Exception as e:                                       # noqa: BLE001
        return {"available": False, "spark_variant": variant,
                "error": f"runner import failed: {type(e).__name__}: {e}"}
    br = runner._build_report()
    if br is None:
        return {"available": False, "spark_variant": variant,
                "error": "build_report.py is not importable"}

    panels, errors = {}, {}

    def cap(name, fn, *args):
        try:
            panels[name] = fn(*args)
        except Exception as e:                                   # noqa: BLE001
            panels[name], errors[name] = None, f"{type(e).__name__}: {e}"

    cap("masthead", br.collect_masthead, wd)
    cap("freshness", br.collect_freshness, wd)
    cap("stages", br.collect_stages, wd)
    if isinstance(panels.get("stages"), dict):
        cap("ask", br.collect_ask, panels["stages"])            # None = no pending ask
    cap("gates", br.collect_gates, wd)
    cap("latex", br.collect_latex, wd)
    cap("review", br.collect_review, wd)
    cap("figures", br.collect_figures, wd)
    if isinstance(panels.get("gates"), dict) and isinstance(panels.get("latex"), dict):
        cap("refs", br.collect_refs, wd, panels["gates"], panels["latex"])
    if all(isinstance(panels.get(k), (dict, list)) for k in
           ("review", "refs", "gates", "figures", "latex", "freshness")):
        cap("dod", br.collect_dod, panels["review"], panels["refs"], panels["gates"],
            panels["figures"], panels["latex"], panels["freshness"])
    cap("blueprint", _blueprint, wd)

    return {"available": True, "workdir": str(wd), "panels": panels, "errors": errors,
            "spark_variant": variant}


# ---------------------------------------------------------------- story

def story(runroot) -> dict:
    """.research/story.json (or <wd>/story.json) — the idea -> story origin card."""
    research = _find_research(runroot)
    cands = []
    if research is not None:
        cands += [research / "story.json", research.parent / "story.json"]
    cands += [Path(runroot) / "story.json"]
    for c in cands:
        d = _read_json(c)
        if isinstance(d, dict):
            return d
    return {}


# ---------------------------------------------------------------- governance

def _sections(text: str):
    secs, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if cur:
                secs.append(cur)
            cur = {"heading": m.group(2).strip(), "level": len(m.group(1)), "md": ""}
        elif cur is not None:
            cur["md"] += line + "\n"
    if cur:
        secs.append(cur)
    for s in secs:
        s["md"] = s["md"].strip()
    return secs


def _gov_ledger(research: Path) -> dict:
    data = _read_json(research / "LEDGER.json")
    if not isinstance(data, dict):
        return {"present": False}
    runs = data.get("runs") or []
    booked = sum((r.get("gpu_h_actual") or 0) for r in runs if r.get("spend_basis") == "sacct")
    return {
        "present": True,
        "budget": data.get("budget") or {},
        "directions": data.get("directions") or {},
        "runs": runs,
        "councils": data.get("councils") or [],
        "scoped_accepts": data.get("scoped_accepts") or [],
        "pivots_used": data.get("pivots_used"),
        "stagnant_rounds": data.get("stagnant_rounds"),
        "gpu_h_booked_sacct": booked,
    }


def _seals(research: Path, runroot: Path) -> dict:
    for base in (research, runroot):
        sd = base / "logs" / "seals"
        if not sd.is_dir():
            continue
        seals = []
        for f in sorted(sd.glob("*.seal.json")):
            d = _read_json(f) or {}
            rows = (d.get("rollcall") or {}).get("rows") or []
            mn = re.match(r"^(\d+)-", f.name)
            seals.append({
                "file": f.name,
                "stage_no": int(mn.group(1)) if mn else None,
                "stage": d.get("stage"), "ts": d.get("ts"), "minter": d.get("minter"),
                "tree_hash": d.get("tree_hash"), "checklist_hash": d.get("checklist_hash"),
                "rollcall": {"rows": rows, "counts": dict(Counter(r.get("status") for r in rows))},
            })
        return {"present": True, "dir": sd.as_posix(),
                "sealed_stages": sorted(s["stage_no"] for s in seals if s["stage_no"] is not None),
                "seals": seals}
    return {"present": False, "seals": [], "sealed_stages": []}


def _settle(rows):
    """Single pass faithful to decision_queue.open_rows, also recording WHO
    settled each decision row (its disposition, or the block-waiver that cleared
    the queue at its position). Returns (open_rows, settled_by:{id->{by,how}})."""
    open_by_id: dict = {}
    settled: dict = {}
    for row in rows:
        t = row.get("type")
        if t == "disposition":
            ref = row.get("ref")
            if ref in open_by_id:
                settled[ref] = {"by": row.get("id"), "how": "disposition",
                                "outcome": row.get("outcome")}
                open_by_id.pop(ref, None)
        elif t == "block-waiver":
            for rid in list(open_by_id):
                settled[rid] = {"by": row.get("id"), "how": "block-waiver"}
            open_by_id.clear()
        else:
            rid = row.get("id")
            if rid is not None:
                open_by_id[rid] = row
    return list(open_by_id.values()), settled


def _decisions(research: Path, runroot: Path) -> dict:
    dq = None
    for base in (research, runroot):
        cand = base / "decisions" / "DECISION_QUEUE.jsonl"
        if cand.is_file():
            dq = cand
            break
    if dq is None:
        return {"present": False, "rows": [], "open": [], "state": None}
    rows = _read_jsonl(dq)
    opened, settled = _settle(rows)
    # each decision (non-settlement) row with its resolution — makes the
    # PENDING_REVIEW -> SUBMITTABLE state auditable (a block-waiver settles every
    # open row at its position, which is why an explicit waiver can flip the state)
    decisions = [{**r, "settled_by": settled.get(r.get("id"))}
                 for r in rows if r.get("type") not in SETTLEMENT_TYPES]
    return {
        "present": True,
        "path": dq.as_posix(),
        "rows": rows,
        "decisions": decisions,
        "open": opened,
        "state": "SUBMITTABLE" if not opened else "PENDING_REVIEW",
        "counts": {
            "decisions": len(decisions),
            "open": len(opened),
            "cheap": sum(1 for r in opened if r.get("reversal_cost") == "cheap"),
            "expensive": sum(1 for r in opened if r.get("reversal_cost") == "expensive"),
            "settlements": sum(1 for r in rows if r.get("type") in SETTLEMENT_TYPES),
        },
    }


def _claims(research: Path) -> dict:
    droot = research / "directions"
    directions, allrows = {}, []
    if droot.is_dir():
        for ddir in sorted(d for d in droot.iterdir() if d.is_dir()):
            ev = _read_text(ddir / "EVIDENCE.md")
            if not ev:
                continue
            claims = []
            for m in CLAIM_RE.finditer(ev):
                row = dict(zip(("id", "dir", "status", "since", "council",
                                "facts", "margin", "provenance"), m.groups()))
                claims.append(row)
                allrows.append(row)
            brev = BELIEFS_REV_RE.search(ev)
            directions[ddir.name] = {
                "beliefs_rev": ({"k": int(brev.group(1)), "cards_covered": int(brev.group(2))}
                                if brev else None),
                "claims": claims,
                "open": [{"id": m.group(1), "kind": m.group(2), "ref": m.group(3)}
                         for m in OPEN_RE.finditer(ev)],
            }
    return {"directions": directions, "rows": allrows,
            "counts": dict(Counter(r["status"] for r in allrows))}


def _deadends(frontier: Path) -> dict:
    lines = _read_text(frontier).splitlines()
    entries = []
    for i, ln in enumerate(lines):
        m = DEADEND_RE.match(ln)
        if not m:
            continue
        entry = {"id": m.group(1), "dir": m.group(2), "run": m.group(3),
                 "support": m.group(4), "hypothesis": None, "failure_mode": None, "lesson": None}
        for sub in lines[i + 1:]:
            if DEADEND_RE.match(sub) or (sub.strip() and not sub.startswith((" ", "\t"))):
                break
            sm = re.match(r"^\s+(hypothesis|failure_mode|lesson):\s*(.*)$", sub)
            if sm:
                entry[sm.group(1)] = sm.group(2).strip()
        entries.append(entry)
    return {"entries": entries, "census": dict(Counter(e["support"] for e in entries))}


def _state(state_md: Path) -> dict:
    text = _read_text(state_md)
    if not text.strip():
        return {"present": False}
    sm = STATE_SENTINEL_RE.search(text)
    sentinel = {}
    if sm:
        for tok in sm.group(0).split():
            if "=" in tok:
                k, _, v = tok.partition("=")
                sentinel[k] = v
    pm = re.search(r"^phases-pending:\s*(.*)$", text, re.M)
    pending = pm.group(1).split() if pm else []
    alarms = []
    for s in _sections(text):
        if "报警" in s["heading"] or "alarm" in s["heading"].lower():
            alarms = [ln.strip()[2:].strip() for ln in s["md"].splitlines()
                      if ln.strip().startswith("- ")]
    return {"present": True, "sentinel": sentinel, "phases_pending": pending,
            "alarms": alarms, "raw": text}


def _tier(route, e14_rows) -> dict:
    best = e14_rows[-1].get("best_tier_at_end") if e14_rows else None
    return {
        "route_tier": (route or {}).get("tier"),
        "best_tier": best,
        "floors": None,   # per-tier blocking floors need sr5_render; not derivable here
        "note": "best_tier is the newest E14 row's best_tier_at_end; blocking floors "
                "require sr5_render and are not surfaced.",
    }


def governance(runroot) -> dict:
    """The full `.research/` governance bundle: ledger (budget/directions/runs),
    stage seals, decision queue (+ derived state), E14 metrics, tier, claim
    ledgers, dead-ends, and STATE. Walks up to find `.research/`; degrades to
    found:false when there is none."""
    research = _find_research(runroot)
    if research is None:
        # A real, readable LINEAR run (public Spark v1.1.0) that never had a
        # research engine — NOT a dir we failed to read. A distinct state so the
        # GUI shows an honest one-line note instead of a fabricated governance
        # dashboard behind a banner.
        return {
            "found": False,
            "spark_variant": "flat",
            "variant": "flat",
            "not_applicable": True,
            "reason": "线性流程 · 无研究引擎治理 / linear pipeline — no research-engine governance",
        }
    rr = research.parent
    route = _read_json(research / "route.json")
    e14 = _read_jsonl(research / "E14-metrics.jsonl")
    return {
        "found": True,
        "spark_variant": "engine",
        "research_dir": research.as_posix(),
        "route": route or {},
        "ledger": _gov_ledger(research),
        "seals": _seals(research, rr),
        "decisions": _decisions(research, rr),
        "e14": e14,
        "tier": _tier(route, e14),
        "claims": _claims(research),
        "deadends": _deadends(research / "FRONTIER.md"),
        "state": _state(research / "STATE.md"),
    }


# ---------------------------------------------------------------- paper facts

def _results_mode(wd: Path) -> str:
    """The run's results mode: 'data_aware' (measured numbers) vs proposal. A
    `.run_mode` file wins; else template.json's results_mode; else proposal. This
    is how a public/linear run that only ever drafted a PROPOSAL is told apart from
    an engine run whose facts ledger merely failed to read."""
    rm = wd / ".run_mode"
    if rm.is_file():
        t = _read_text(rm).strip()
        if t:
            return t
    tmpl = _read_json(wd / "template.json")
    if isinstance(tmpl, dict):
        v = tmpl.get("results_mode")
        if v:
            return str(v)
    return "proposal"


def facts(workdir) -> dict:
    """results.facts.json — the verified numbers ledger every paper number traces
    to (the fabrication-gate substrate). When it is absent AND the run is in
    proposal mode, {found:false, mode:"proposal"} so the GUI labels it rather than
    sampling. Every payload carries spark_variant (engine vs linear/public)."""
    wd = Path(workdir)
    variant = _spark_variant(wd)
    data = _read_json(wd / "results.facts.json")
    if isinstance(data, dict) and data:
        return {**data, "spark_variant": variant}
    # facts.json missing (or empty): distinguish a proposal-mode run from a
    # data-aware run whose ledger simply is not there yet.
    if _results_mode(wd) != "data_aware":
        return {"found": False, "mode": "proposal", "spark_variant": variant}
    return {"spark_variant": variant}


def claims_map(workdir) -> dict:
    """claims_map.json — bibkey -> {claim, support_label, section} for the
    citation-hover popovers."""
    data = _read_json(Path(workdir) / "claims_map.json")
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------- manuscript

def _file_url(p: Path) -> str:
    """A jailed library-file URL for the native tex editor / PDF preview. quote()
    keeps a Windows drive-colon and spaces from breaking the query string; the
    /api/file route re-jails on read, so this is a reference, not an escape."""
    return "/api/file?path=" + quote(str(p))


def manuscript(workdir) -> dict:
    """The tex sources of a paper workdir as an ordered file tree for the native
    'Manuscript' editor: main.tex, then sections/*.tex in blueprint section_order
    (falling back to sorted), then refs.bib — each with a /api/file?path= URL. The
    PDF is a URL too, or null when it has not compiled. Faithful to what is on
    disk: a missing file simply does not appear."""
    wd = Path(workdir)
    files, order = [], 0

    main = wd / "main.tex"
    main_name = "main.tex" if main.is_file() else None
    if main_name:
        files.append({"name": "main.tex", "rel": "main.tex",
                      "url": _file_url(main), "order": order})
        order += 1

    secdir = wd / "sections"
    sec_order = None
    bp = _read_json(wd / "blueprint.json")
    if isinstance(bp, dict) and isinstance(bp.get("section_order"), list) and bp["section_order"]:
        sec_order = bp["section_order"]
    sec_paths = []
    if secdir.is_dir():
        if sec_order:
            named = [secdir / f"{sid}.tex" for sid in sec_order
                     if (secdir / f"{sid}.tex").is_file()]
            rest = sorted(p for p in secdir.glob("*.tex") if p not in named)
            sec_paths = named + rest
        else:
            sec_paths = sorted(secdir.glob("*.tex"))
    for p in sec_paths:
        files.append({"name": p.name, "rel": p.relative_to(wd).as_posix(),
                      "url": _file_url(p), "order": order})
        order += 1

    bib_url = None
    for cand in ("refs.bib", "references.bib"):
        bp_path = wd / cand
        if bp_path.is_file():
            bib_url = _file_url(bp_path)
            files.append({"name": cand, "rel": cand, "url": bib_url, "order": order})
            order += 1
            break

    pdf = wd / "main.pdf"
    return {
        "main": main_name,
        "pdf": _file_url(pdf) if pdf.is_file() else None,
        "files": files,
        "bib": bib_url,
        "workdir": str(wd),
        "spark_variant": _spark_variant(wd),
    }


# ---------------------------------------------------------------- edits (PR view)

def edits(workdir) -> dict:
    """PR-style edit history from the run's linked `.paper-review/`: the applied
    edits in journal.jsonl (each an atomic before/after with its close criterion),
    reconciled with the LEDGER issue for the fields the journal row omits (section,
    passage_id, drafted_patch before/after). When no jury ledger is bound to this
    run, {edits: [], source_dir: null} — honest, not empty-because-broken."""
    variant = _spark_variant(workdir)
    review = _find_review(workdir)
    if review is None:
        # source_dir:null = this run has no edit journal (a linear/public run),
        # distinct from a dir we could not read.
        return {"edits": [], "source_dir": None, "spark_variant": variant}

    journal_rows = _read_jsonl(review / "journal.jsonl")
    ledger = _read_json(review / "LEDGER.json")
    issues = {}
    if isinstance(ledger, dict):
        for it in ledger.get("issues") or []:
            iid = it.get("id")
            if iid is not None and isinstance(it, dict):
                issues[iid] = it

    out = []
    for i, row in enumerate(journal_rows):
        if not isinstance(row, dict):
            continue
        iid = row.get("issue_id") or row.get("issue") or row.get("id")
        issue = issues.get(iid, {})
        patch = issue.get("drafted_patch") if isinstance(issue.get("drafted_patch"), dict) else {}
        before = row.get("before")
        after = row.get("after")
        out.append({
            "seq": row.get("seq", i + 1),
            "issue_id": iid,
            "section": row.get("section") or issue.get("section"),
            "passage_id": row.get("passage_id") or issue.get("passage_id"),
            "round": row.get("round") if row.get("round") is not None else issue.get("round_raised"),
            "close_criterion": row.get("close_criterion") or issue.get("close_criterion"),
            "before": before if before is not None else patch.get("before"),
            "after": after if after is not None else patch.get("after"),
            "ts": row.get("ts") or row.get("t"),
            "applied": row.get("applied", True),
        })
    return {"edits": out, "source_dir": review.as_posix(), "spark_variant": variant}


# ---------------------------------------------------------------- telemetry

def telemetry(workdir) -> dict:
    """A library run keeps no token stream on disk (the live stream that carries
    modelUsage is only in memory while the run runs), so per-stage token
    attribution is honestly 'not captured' here — per_stage is null, never a
    fabricated heatmap. The live path (runner.telemetry_of) is the one that fills
    it in for an instrumented run."""
    return {
        "per_stage": None,
        "captured": False,
        "note": "library run — per-stage token usage was not captured on disk",
    }


# ---------------------------------------------------------------- smoke test

def _smoke():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    base = Path("C:/Users/terry/AppData/Local/Temp/claude/D--paper-spark/"
                "c6c7ab12-839a-48ae-93db-6c98e72d01f4/scratchpad/fixtures/spark")
    icml = Path("D:/paper-spark/_ICML__2027__Spark2Paper/_ICML__2027__Spark2Paper")

    print(f"spark governance fixture: {base}\n  exists={base.is_dir()}")
    gov = governance(base)
    print(f"governance: found={gov['found']} research={gov.get('research_dir')}")
    led = gov["ledger"]
    print(f"  ledger: directions={led['directions']} runs={len(led['runs'])} "
          f"gpu_h_booked_sacct={led['gpu_h_booked_sacct']} budget={led['budget'].get('gpu_hours_spent')}/"
          f"{led['budget'].get('gpu_hours_cap')}")
    print(f"  seals: sealed_stages={gov['seals']['sealed_stages']} ({len(gov['seals']['seals'])} seals)")
    dq = gov["decisions"]
    print(f"  decisions: rows={len(dq['rows'])} open={dq['counts']['open']} "
          f"state={dq['state']} (decisions={dq['counts']['decisions']} "
          f"settlements={dq['counts']['settlements']})")
    print(f"  e14: {len(gov['e14'])} rows  tier={gov['tier']}")
    cl = gov["claims"]
    print(f"  claims: {len(cl['rows'])} rows counts={cl['counts']} dirs={list(cl['directions'])}")
    de = gov["deadends"]
    print(f"  deadends: {len(de['entries'])} entries census={de['census']} "
          f"ids={[e['id'] for e in de['entries']]}")
    stt = gov["state"]
    print(f"  state: sentinel={stt.get('sentinel')} phases_pending={stt.get('phases_pending')} "
          f"alarms={len(stt.get('alarms', []))}")

    stry = story(base)
    print(f"story: title={stry.get('title')!r} claims={len(stry.get('innovation_claims', []))}")

    print(f"\npaper fixture: {base / 'paper'}")
    fx = facts(base / "paper")
    print(f"facts: groups={list(fx)}  rq3.pages={fx.get('rq3_end_to_end', {}).get('pages')}")
    cm = claims_map(base / "paper")
    labels = Counter(v.get("support_label") for v in cm.values())
    print(f"claims_map: {len(cm)} bibkeys  support_labels={dict(labels)}")

    print(f"\nreal ICML workdir: {icml}\n  exists={icml.is_dir()}")
    rep = report(icml)
    if rep.get("available"):
        pk = {k: ("None" if v is None else "ok") for k, v in rep["panels"].items()}
        print(f"report: available panels={pk}")
        mh = rep["panels"].get("masthead") or {}
        bp = rep["panels"].get("blueprint") or {}
        fg = rep["panels"].get("figures") or {}
        print(f"  masthead.title={str(mh.get('title'))[:48]!r}")
        print(f"  blueprint: contribs={bp.get('n_contributions')} sections={bp.get('n_sections')} "
              f"notation={bp.get('n_notation')}")
        print(f"  figures: {len(fg.get('items', []))} items  freshness="
              f"{(rep['panels'].get('freshness') or {}).get('state')}")
        if rep["errors"]:
            print(f"  collector errors: {rep['errors']}")
    else:
        print(f"report: {rep}")
    ifx = facts(icml)
    print(f"ICML facts: groups={list(ifx)}  rq1.mean_ssim="
          f"{ifx.get('rq1_figure_engine_ssim', {}).get('mean')}")


if __name__ == "__main__":
    _smoke()
