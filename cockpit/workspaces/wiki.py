#!/usr/bin/env python3
"""Paper Wiki reader — a compiled wiki project directory turned into corpus JSON.

A wiki project is plain Markdown + YAML front-matter + Obsidian-style
`[[wikilinks]]` on disk (protocol `llm-wiki/1.1`; variants research | course).
Nothing here rewrites it: every function reads a file the tool already compiled
and returns plain JSON-able dicts/lists. Missing file -> {} / null / [] — an
absent note is reported as absent, never invented.

The one non-trivial parse is YAML front-matter WITHOUT pyyaml: a small
indentation tokenizer (`_parse_yaml`) that covers exactly the shapes the wiki
schema uses — scalars, `[inline, lists]`, block `- lists`, and one level of
nested `key:`/`sub:` maps (the idea card's `execution` / `interest` blocks).

The signature feature is `backlinks(id)`: inbound reverse-links are NOT stored
anywhere, so they are computed by scanning every note body for `[[id]]` and
keeping the annotation that trails the link on its line. `graph()` is the same
scan widened to every `[[link]]` (front-matter link fields + in-body).

stdlib only.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

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


# ---------------------------------------------------------------- front-matter
#
# A hand-rolled YAML subset. It is deliberately narrow: the wiki schema only
# ever nests one level (execution/interest maps, block lists), so a full parser
# would be more surface than the data needs. Unknown-but-well-formed lines pass
# through as scalars rather than raising — an unreadable key hides itself, not
# the note.

_FM_FENCE = "---"


def _split_front_matter(text: str):
    """(front_dict, body). A note has front-matter only when its first non-BOM
    line is `---`; everything else is body verbatim."""
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FM_FENCE:
        return {}, text
    for j in range(1, len(lines)):
        if lines[j].strip() == _FM_FENCE:
            front = _parse_yaml("\n".join(lines[1:j]))
            return (front if isinstance(front, dict) else {}), "\n".join(lines[j + 1:])
    return {}, text  # an unclosed fence is not front-matter


def _tokenize(text: str):
    """(indent, stripped-text) per meaningful line; blanks and #comment lines out."""
    out = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        out.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    return out


def _split_csv(s: str):
    """Comma-split respecting quotes and nested [brackets] — for inline lists."""
    out, buf, depth, q = [], "", 0, None
    for c in s:
        if q:
            buf += c
            if c == q:
                q = None
        elif c in "\"'":
            q, buf = c, buf + c
        elif c == "[":
            depth, buf = depth + 1, buf + c
        elif c == "]":
            depth, buf = depth - 1, buf + c
        elif c == "," and depth == 0:
            out.append(buf)
            buf = ""
        else:
            buf += c
    if buf.strip():
        out.append(buf)
    return out


def _scalar(v: str):
    """One YAML scalar: quotes, null, bool, int, or an [inline, list]. Wikilink
    refs ("[[x]]") are kept verbatim so link extraction still finds them."""
    v = v.strip()
    if v[:1] not in ("\"", "'", "["):        # strip a trailing ` # comment`
        h = v.find(" #")
        if h >= 0:
            v = v[:h].strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x) for x in _split_csv(inner)] if inner else []
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v in ("null", "~", ""):
        return None
    if v == "true":
        return True
    if v == "false":
        return False
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def _parse_block(tokens, i, indent):
    """Recursive descent over (indent,text) tokens at a fixed indent level.
    A `- ` first line makes a list; otherwise a `key:` map. Empty value with
    deeper-indented children recurses (one level is all the schema uses)."""
    if i < len(tokens) and tokens[i][1].startswith("- "):
        arr = []
        while i < len(tokens) and tokens[i][0] == indent and tokens[i][1].startswith("- "):
            arr.append(_scalar(tokens[i][1][2:]))
            i += 1
        return arr, i
    obj = {}
    while i < len(tokens) and tokens[i][0] == indent:
        line = tokens[i][1]
        if ":" not in line:
            i += 1
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        i += 1
        if val == "" and i < len(tokens) and tokens[i][0] > indent:
            child, i = _parse_block(tokens, i, tokens[i][0])
            obj[key] = child
        else:
            obj[key] = _scalar(val)
    return obj, i


def _parse_yaml(text: str) -> dict:
    tokens = _tokenize(text)
    if not tokens:
        return {}
    obj, _ = _parse_block(tokens, 0, tokens[0][0])
    return obj if isinstance(obj, dict) else {}


# ---------------------------------------------------------------- markdown

_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
# target of a [[wikilink]], dropping an Obsidian |alias or #section and .md
_LINK = re.compile(r"\[\[\s*([^\[\]|#]+?)\s*(?:[|#][^\]]*)?\]\]")


def _linkid(raw: str) -> str:
    raw = raw.strip()
    return raw[:-3] if raw.lower().endswith(".md") else raw


def _links(text: str):
    """Unique wikilink target ids in appearance order."""
    seen, out = set(), []
    for m in _LINK.finditer(text):
        lid = _linkid(m.group(1))
        if lid and lid not in seen:
            seen.add(lid)
            out.append(lid)
    return out


def _sections(body: str):
    """`##`-delimited sections as [{heading, level, md}] — nothing lossy: each
    section's md is its raw body text. Prose before the first heading is not a
    section (it stays in body_md)."""
    secs, cur = [], None
    for line in body.splitlines():
        m = _HEAD.match(line)
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


def _h1(body: str) -> str:
    for line in body.splitlines():
        m = re.match(r"^#\s+(.*)$", line)
        if m:
            return m.group(1).strip()
    return ""


def _summary(body: str, sections) -> str:
    for s in sections:
        if "一句话总结" in s["heading"]:
            for ln in s["md"].splitlines():
                if ln.strip():
                    return ln.strip()
    for ln in body.splitlines():                    # else first real paragraph
        t = ln.strip()
        if t and not t.startswith(("#", ">", "|", "-", "```")):
            return t
    return ""


def _md_tables(text: str):
    """Every GitHub-pipe table as {title, columns, rows(list of cell-lists)}.
    title = the nearest preceding heading or **bold** line."""
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


def _row_cells(line: str):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


# ---------------------------------------------------------------- note walk

# folder name -> canonical note type (the schema's singular). Anything else
# falls back to the folder name verbatim, per the "type = folder or FM" rule.
_FOLDER_TYPE = {
    "papers": "paper", "concepts": "concept", "gaps": "gap", "ideas": "idea",
    "directions": "direction", "probes": "probe", "field": "field",
    "novelty": "novelty", "lectures": "lecture", "topics": "topic",
    "practice": "practice", "experiments": "experiment", "notes": "note",
    "salvage": "salvage",
}


def _wiki_dir(proj) -> Path:
    return Path(proj) / "wiki"


def _note_files(proj):
    wd = _wiki_dir(proj)
    return sorted(wd.rglob("*.md")) if wd.is_dir() else []


def _note_type(proj, p: Path, front: dict) -> str:
    if front.get("type"):
        return str(front["type"])
    if front.get("kind"):
        return str(front["kind"])
    try:
        rel = p.relative_to(_wiki_dir(proj)).parts
    except ValueError:
        rel = ()
    folder = rel[0] if len(rel) > 1 else "wiki"
    return _FOLDER_TYPE.get(folder, folder)


def _note_meta(proj, p: Path):
    text = _read_text(p)
    front, body = _split_front_matter(text)
    secs = _sections(body)
    return {
        "id": p.stem,
        "type": _note_type(proj, p, front),
        "title": front.get("title") or _h1(body) or p.stem,
        "path": p.relative_to(proj).as_posix(),
        "front": front,
        "tags": front.get("tags") or [],
        "fence_zone": front.get("fence_zone"),
        "summary": _summary(body, secs),
        "companion": p.name.endswith((".tiering.md", ".counter.md")),
    }


# ---------------------------------------------------------------- public API

def project_info(proj) -> dict:
    """Variant marker + research.md Scope fence -> the project-status header."""
    proj = Path(proj)
    wiki_md = _read_text(proj / "WIKI.md")
    m = re.search(r"<!--\s*paper-wiki-variant:\s*(research|course)\s*-->", wiki_md)
    variant = m.group(1) if m else None
    title = _h1(wiki_md) or proj.name

    research = _read_text(proj / "research.md")
    _, rbody = _split_front_matter(research)
    secs = _sections(rbody)
    fence = next((s for s in secs if s["heading"].strip().startswith("Scope fence")), None)
    life = mode = None
    if fence:
        lm = re.search(r"^lifecycle_state:\s*([^\s#]+)", fence["md"], re.M)
        em = re.search(r"^expansion_mode:\s*([^\s#]+)", fence["md"], re.M)
        life = lm.group(1) if lm else None
        mode = em.group(1) if em else None

    def _fence_body(*needles):
        for s in secs:
            if any(n in s["heading"] for n in needles):
                return s["md"].strip()
        return ""

    return {
        "variant": variant,
        "lifecycle_state": life,
        "expansion_mode": mode,
        "scope": {
            "core": _fence_body("核心焦点"),
            "adjacent": _fence_body("相邻可纳入"),
            "exclusions": _fence_body("排除范围"),
            "jurisdiction": _fence_body("管辖权声明"),
        },
        "title": title,
    }


def notes(proj) -> list:
    """Every wiki/**/*.md as a metadata row (front-matter chips + summary)."""
    return [_note_meta(proj, p) for p in _note_files(proj)]


def note(proj, rel: str) -> dict:
    """One note rendered faithfully: front-matter, `##` sections (raw md),
    outbound link ids, and the whole body_md. Jailed under the project dir."""
    proj = Path(proj).resolve()
    target = (proj / rel).resolve()
    if target != proj and proj not in target.parents:
        return {"error": "path is outside the wiki project"}
    if not target.is_file():
        return {"error": f"no such note: {rel}"}
    text = _read_text(target)
    front, body = _split_front_matter(text)
    return {
        "id": target.stem,
        "title": front.get("title") or _h1(body) or target.stem,
        "path": target.relative_to(proj).as_posix(),
        "front": front,
        "sections": _sections(body),
        "outbound": _links(text),   # front-matter link fields + in-body [[links]]
        "body_md": body,
    }


def backlinks(proj, note_id: str) -> list:
    """THE signature feature. Inbound links are not stored — scan every note for
    `[[note_id]]` and keep the text trailing the link on its line as `anno`
    (papers annotate their reverse-links: `[[x]]（提出 A，本文改进 B）`)."""
    pat = re.compile(r"\[\[\s*" + re.escape(note_id) + r"\s*(?:[|#][^\]]*)?\]\]")
    out = []
    for p in _note_files(proj):
        if p.stem == note_id:
            continue                                # a note is not its own backlink
        text = _read_text(p)
        anno = None
        hit = False
        for line in text.splitlines():
            m = pat.search(line)
            if not m:
                continue
            hit = True
            tail = line[m.end():].strip()
            if tail:
                anno = tail                         # first annotated occurrence wins
                break
        if hit:
            front, body = _split_front_matter(text)
            out.append({
                "id": p.stem,
                "title": front.get("title") or _h1(body) or p.stem,
                "type": _note_type(proj, p, front),
                "path": p.relative_to(proj).as_posix(),
                "anno": anno,
            })
    return out


def graph(proj) -> dict:
    """{nodes, edges} over every [[link]] (front-matter fields + in-body).
    Edges only connect known notes; a dangling `[[x]]` yields no edge."""
    metas = notes(proj)
    ids = {m["id"] for m in metas}
    nodes = [{"id": m["id"], "type": m["type"], "title": m["title"]} for m in metas]
    edges = []
    for p in _note_files(proj):
        src = p.stem
        for tgt in _links(_read_text(p)):
            if tgt in ids and tgt != src:
                edges.append({"from": src, "to": tgt})
    return {"nodes": nodes, "edges": edges}


def ideas(proj) -> list:
    """Idea cards for the tier-sorted candidates inbox: status + complexity_tier,
    the dual-column Claim (Hypothesis / 当前可断言), the 实验台账 table, and any
    .tiering.md / .counter.md companion text (the 'why this rating' panels)."""
    ideadir = _wiki_dir(proj) / "ideas"
    if not ideadir.is_dir():
        return []
    out = []
    for p in sorted(ideadir.glob("*.md")):
        if p.name.endswith((".tiering.md", ".counter.md")):
            continue
        front, body = _split_front_matter(_read_text(p))
        secs = _sections(body)

        def _sec(*needles):
            return next((s["md"] for s in secs if any(n in s["heading"] for n in needles)), "")

        tier_p = p.with_name(p.stem + ".tiering.md")
        counter_p = p.with_name(p.stem + ".counter.md")
        ledger_tables = _md_tables(_sec("实验台账"))
        out.append({
            "id": p.stem,
            "path": p.relative_to(proj).as_posix(),
            "status": front.get("status"),
            "complexity_tier": front.get("complexity_tier"),
            "seed_type": front.get("seed_type"),
            "pitch": front.get("pitch"),
            "seeded_from": front.get("seeded_from") or [],
            "novelty_ref": front.get("novelty_ref"),
            "venue_targets": front.get("venue_targets") or [],
            "interest": front.get("interest") or {},
            "execution": front.get("execution") or {},
            "residual_destination": front.get("residual_destination"),
            "claim": {
                "hypothesis": _sec("Hypothesis", "大胆版"),
                "assertable": _sec("当前可断言", "assertable"),
            },
            "ledger": ledger_tables[0]["rows"] if ledger_tables else [],
            "tiering_md": _read_text(tier_p) if tier_p.is_file() else None,
            "counter_md": _read_text(counter_p) if counter_p.is_file() else None,
        })
    return out


def coverage(proj) -> dict:
    """The field/coverage panel: saturation (crowded/blank/messy), problems.md
    backlog, tensions, and each field map's staleness."""
    field = _wiki_dir(proj) / "field"

    # saturation: one section per kind, each citing >=3 papers
    sat = []
    for s in _sections(_split_front_matter(_read_text(field / "saturation.md"))[1]):
        kind = next((k for k in ("crowded", "blank", "messy") if k in s["heading"]), None)
        if kind:
            sat.append({"kind": kind, "heading": s["heading"],
                        "sources": _links(s["md"]), "body": s["md"]})

    # problems.md: a Hamming-style bullet list, one capability-gap each
    _, pbody = _split_front_matter(_read_text(field / "problems.md"))
    problems = [{"text": ln.strip()[2:].strip(), "sources": _links(ln)}
                for ln in pbody.splitlines() if ln.strip().startswith("- ")]

    # tensions: side_a / side_b / same_object / resolution_type_guess per entry
    tensions = []
    for s in _sections(_split_front_matter(_read_text(field / "tensions.md"))[1]):
        md = s["md"]

        def _f(key):
            m = re.search(rf"^-?\s*{key}:\s*(.+)$", md, re.M)
            return m.group(1).strip().strip('"') if m else None
        if s["level"] >= 2 and (_f("side_a") or _f("side_b")):
            tensions.append({
                "heading": s["heading"], "side_a": _f("side_a"), "side_b": _f("side_b"),
                "same_object": _f("same_object"),
                "resolution_type_guess": _f("resolution_type_guess"),
                "sources": _links(md),
            })

    def _staleness(name):
        fm, _ = _split_front_matter(_read_text(field / name))
        if not fm:
            return None
        return {"staleness": fm.get("staleness"), "last_zoomout": fm.get("last_zoomout"),
                "papers_at_zoomout": fm.get("papers_at_zoomout")}

    return {
        "saturation": sat,
        "problems": problems,
        "tensions": tensions,
        "staleness": {n: _staleness(n + ".md")
                      for n in ("assumptions", "tensions", "saturation")},
    }


_OCR_RES = (("committed", "*.committed.json"), ("pending", "*.pending.json"),
            ("aborted", "*.aborted.json"))


def sources(proj) -> dict:
    """The sources library: raw/ entries with OCR status (committed/pending/
    aborted/needs-OCR), the IMPORT-LOG n/200 ledger, and a search-latest feed."""
    proj = Path(proj)
    raw = proj / "raw"
    entries = {}

    def _entry(name, topic):
        return entries.setdefault(name, {
            "source": name, "topic": topic, "pdf": None, "projectpage": None,
            "ocr_status": "needs-OCR", "ocr_markdown": None, "ocr_complete": False})

    if raw.is_dir():
        for topicdir in sorted([d for d in raw.iterdir() if d.is_dir()]):
            topic = topicdir.name
            for pdf in sorted(topicdir.glob("*.pdf")):
                _entry(pdf.stem, topic)["pdf"] = pdf.relative_to(proj).as_posix()
            for pp in sorted(topicdir.glob("*-projectpage.md")):
                _entry(pp.name[:-len("-projectpage.md")], topic)["projectpage"] = \
                    pp.relative_to(proj).as_posix()
            mineru = topicdir / "mineru"
            if mineru.is_dir():
                for sdir in sorted([d for d in mineru.iterdir() if d.is_dir()]):
                    e = _entry(sdir.name, topic)
                    for status, pat in _OCR_RES:
                        if any(sdir.glob(pat)):
                            e["ocr_status"] = status
                            break
                    if (sdir / "_paper-wiki-ocr-complete.json").is_file():
                        e["ocr_complete"] = True
                    md = sdir / "auto" / f"{sdir.name}.md"
                    if md.is_file():
                        e["ocr_markdown"] = md.relative_to(proj).as_posix()

    # IMPORT-LOG.md: rows 日期|paper id|sponsor|累计 n/200|该 sponsor m/10
    import_rows, cap = [], None
    tabs = _md_tables(_read_text(raw / "IMPORT-LOG.md"))
    if tabs:
        for r in tabs[-1]["rows"]:
            import_rows.append(r)
        m = re.search(r"(\d+)\s*/\s*200", " | ".join(import_rows[-1])) if import_rows else None
        cap = {"n": int(m.group(1)), "of": 200} if m else None

    # search-latest.json: documented at <proj>/wiki/, sometimes shipped a level up
    sl = None
    for cand in (proj / "wiki" / "search-latest.json", proj / "search-latest.json",
                 proj.parent / "search-latest.json"):
        data = _read_json(cand)
        if data is not None:
            sl = data
            break

    return {
        "entries": sorted(entries.values(), key=lambda e: (e["topic"], e["source"])),
        "import_log": {"rows": import_rows, "cap": cap},
        "search_latest": sl,
    }


def inbox(proj) -> dict:
    """/wiki-auto INBOX: the machine-decision audit rows (日期/环节/对象/事项/
    状态) plus the closing reconciliation block (numbered lines, each with a
    re-runnable command)."""
    text = _read_text(_wiki_dir(proj) / "INBOX.md")
    if not text.strip():
        return {"present": False, "rows": [], "reconciliation": []}
    tabs = _md_tables(text)
    rows = []
    for t in tabs:
        cols = [c for c in t["columns"]]
        if any("状态" in c for c in cols):
            for r in t["rows"]:
                cells = r + [""] * (len(cols) - len(r))
                rows.append(dict(zip(cols, cells)))
    # reconciliation: the numbered lines under the 收尾对账块 heading
    recon = []
    for s in _sections(text):
        if "对账" in s["heading"] or "reconcil" in s["heading"].lower():
            for ln in s["md"].splitlines():
                if re.match(r"^\s*\d+\.", ln):
                    recon.append(ln.strip())
    reversal = [ln.strip() for ln in text.splitlines() if "翻案回执" in ln]
    return {"present": True, "rows": rows, "reconciliation": recon,
            "reversal_notes": reversal}


# ---------------------------------------------------------------- smoke test

def _smoke():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    proj = Path("C:/Users/terry/AppData/Local/Temp/claude/D--paper-spark/"
                "c6c7ab12-839a-48ae-93db-6c98e72d01f4/scratchpad/fixtures/wiki/"
                "sample-research-wiki")
    print(f"wiki fixture: {proj}\n  exists={proj.is_dir()}")
    info = project_info(proj)
    print(f"project_info: variant={info['variant']} lifecycle={info['lifecycle_state']} "
          f"expansion={info['expansion_mode']} scope.core={'yes' if info['scope']['core'] else 'no'}")
    ns = notes(proj)
    types = {}
    for n in ns:
        types[n["type"]] = types.get(n["type"], 0) + 1
    print(f"notes: {len(ns)} total by type={types}")
    g = graph(proj)
    print(f"graph: {len(g['nodes'])} nodes, {len(g['edges'])} edges")
    # backlink counts for the core spine nodes
    for nid in ("edge-hotspot", "thermal-state", "content-aware-browning",
                "what-governs-scorch"):
        bl = backlinks(proj, nid)
        annotated = sum(1 for b in bl if b["anno"])
        print(f"  backlinks[{nid}] = {len(bl)} (annotated {annotated})")
    one = note(proj, "wiki/papers/edge-hotspot.md")
    print(f"note(edge-hotspot): {len(one['sections'])} sections, "
          f"outbound={one['outbound']}")
    idl = ideas(proj)
    for it in idl:
        print(f"idea[{it['id']}]: status={it['status']} tier={it['complexity_tier']} "
              f"hyp={'yes' if it['claim']['hypothesis'] else 'no'} "
              f"ledger_rows={len(it['ledger'])} tiering={'yes' if it['tiering_md'] else 'no'}")
    cov = coverage(proj)
    print(f"coverage: saturation={[s['kind'] for s in cov['saturation']]} "
          f"problems={len(cov['problems'])} tensions={len(cov['tensions'])}")
    src = sources(proj)
    ocr = {e["source"]: e["ocr_status"] for e in src["entries"]}
    print(f"sources: {len(src['entries'])} entries ocr={ocr} "
          f"import_cap={src['import_log']['cap']} "
          f"search_latest={'yes(' + str(len(src['search_latest']['candidates'])) + ')' if src['search_latest'] else 'none'}")
    ib = inbox(proj)
    print(f"inbox: {len(ib['rows'])} rows, {len(ib['reconciliation'])} reconciliation lines, "
          f"reversal_notes={len(ib['reversal_notes'])}")


if __name__ == "__main__":
    _smoke()
