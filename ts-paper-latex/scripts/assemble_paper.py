#!/usr/bin/env python3
"""Assemble + compile a paper from drafted section bodies — TEMPLATE-DRIVEN.

Deterministic backbone for the ts-paper suite. Reads a `template.json` spec from the
working dir (copied there by the plan stage) and threads it through every step: section
order + canonical headings, table/figure caption position, keyword cap, citation-merge,
the document preamble (the template's own `main.tex.tmpl`, filled by safe @@token@@
substitution), and which style/asset files to copy. Falls back to the bundled
`ts_iieta` template when no `template.json` is present (backward-compatible).

The content-quality / LaTeX-safety logic is template-INDEPENDENT and unchanged:
escaping, brace-matching, table-width fit. Compilation is a one-shot latexmk run with
log-trust error counting (the script does NOT loop or auto-fix); the optional --backup
snapshot is what the AGENT uses to drive its own bounded compile-fix loop.

Working dir layout (inputs):
  template.json       the parametric template spec (optional; defaults to bundled ts_iieta)
  blueprint.json      {paper_title, keywords, abstract, section_order, authors?, doi?, dates?, journal?}
  sections/<id>.tex   LaTeX *body* of each section (NO top-level \\section line; subsections ok)
  refs.bib            complete BibTeX (built by the citation stage)

Usage:  python assemble_paper.py <workdir> [--no-compile] [--backup]
Prints a one-line JSON status object.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEGACY_ASSETS = HERE.parent / "assets"                      # ts-paper-latex/assets (legacy fallback)
TEMPLATES_ROOT = HERE.parent.parent / "ts-paper" / "templates"

# ---------------------------------------------------------------------------
# Template loading (spec + the dir that holds its main.tex.tmpl + assets)
# ---------------------------------------------------------------------------
def load_template(wd: Path):
    spec_path = wd / "template.json"
    if spec_path.exists():
        spec = json.loads(spec_path.read_text())
        name = spec.get("name", "ts_iieta")
        tmpl_name = (spec.get("engine") or {}).get("main_template", "main.tex.tmpl")
        # prefer assets the plan stage copied into the workdir; else the bundled template dir
        tdir = wd if (wd / tmpl_name).exists() else (TEMPLATES_ROOT / name)
    else:
        tdir = TEMPLATES_ROOT / "ts_iieta"
        spec = json.loads((tdir / "template.json").read_text())
    return spec, tdir

# ---------------------------------------------------------------------------
# LaTeX escaping + post-processes
# ---------------------------------------------------------------------------
_ESCAPE = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
           "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
           "^": r"\textasciicircum{}"}

def escape_latex(s: str) -> str:
    return "".join(_ESCAPE.get(c, c) for c in str(s))

def format_keywords(value, cap: int = 6) -> str:
    """Dedup (case-insensitive, order-preserving), cap, comma-join. '' -> omit."""
    if isinstance(value, (list, tuple)):
        items = [p.strip() for x in value for p in str(x).split(",") if p.strip()]
    else:
        items = [p.strip() for p in str(value or "").split(",") if p.strip()]
    seen, out = set(), []
    for it in items:
        k = it.lower()
        if k in seen:
            continue
        seen.add(k); out.append(it)
        if cap and len(out) >= cap:
            break
    return escape_latex(", ".join(out))

def _brace_end(s: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1

def merge_adjacent_cites(latex: str) -> str:
    """\\cite{a} \\cite{b} -> \\cite{a,b} (numeric+sort&compress templates only)."""
    cmd = r"\\cite[tp]?\*?"
    pair = re.compile(r"(" + cmd + r")\{([^}]*)\}([~ \t]*)(" + cmd + r")\{([^}]*)\}")

    def merge_keys(a, b):
        keys = []
        for grp in (a, b):
            for k in grp.split(","):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)
        return ",".join(keys)

    def sub(m):
        if m.group(1) != m.group(4):
            return m.group(0)
        return m.group(1) + "{" + merge_keys(m.group(2), m.group(5)) + "}"

    out = latex
    for _ in range(20):
        new = pair.sub(sub, out)
        if new == out:
            break
        out = new
    return out

def move_table_captions_above(latex: str) -> str:
    """Place table captions ABOVE the table (when the template asks for it)."""
    def fix_float(m):
        begin, ttype, content = m.group(1), m.group(2), m.group(3)
        cm = re.search(r"\\caption\{", content)
        if not cm:
            return m.group(0)
        cb = content.find("{", cm.start()); ce = _brace_end(content, cb)
        if ce == -1:
            return m.group(0)
        cap = content[cm.start():ce]
        lab = re.search(r"\\label\{[^}]*\}", content)
        lab_t = lab.group(0) if lab else ""
        body = content[:cm.start()] + content[ce:]
        if lab_t:
            body = body.replace(lab_t, "", 1)
        body = re.sub(r"\n\s*\n\s*\n+", "\n\n", body).strip()
        parts = [cap] + ([lab_t] if lab_t else []) + [body]
        new = "\n".join(parts)
        return m.group(0) if new.strip() == content.strip() else f"{begin}\n{new}\n\\end{{{ttype}}}"

    latex = re.sub(r"(\\begin\{(table\*?)\}(?:\[[^\]]*\])?)(.*?)\\end\{\2\}",
                   fix_float, latex, flags=re.DOTALL)

    def fix_inline(m):
        block = m.group(0)
        if r"\captionof{table}" not in block:
            return block
        cs = block.find(r"\captionsetup{type=table}")
        co = block.find(r"\captionof{table}")
        cands = [x for x in (cs, co) if x != -1]
        if not cands:
            return block
        start = min(cands)
        brace = block.find("{", co + len(r"\captionof{table}"))
        end = _brace_end(block, brace)
        if end == -1:
            return block
        labm = re.match(r"[ \t]*\n?[ \t]*\\label\{[^}]*\}", block[end:])
        if labm:
            end += labm.end()
        ci = block.find(r"\centering")
        if ci == -1:
            return block
        insert_at = ci + len(r"\centering")
        if block[insert_at:start].strip() == "":
            return block
        cap = block[start:end].strip()
        nb = block[:start] + block[end:]
        ci2 = nb.find(r"\centering") + len(r"\centering")
        nb = nb[:ci2] + "\n" + cap + nb[ci2:]
        return re.sub(r"\n\s*\n\s*\n+", "\n\n", nb)

    latex = re.sub(r"\\begin\{minipage\}\{\\columnwidth\}.*?\\end\{minipage\}",
                   fix_inline, latex, flags=re.DOTALL)
    return latex

def strip_heading_numbers(s: str) -> str:
    """\\subsection{3.1 Foo} -> \\subsection{Foo} (LaTeX auto-numbers)."""
    return re.sub(r"(\\(?:sub)*section\*?\{)\s*\d+(?:\.\d+)*\.?\s+", r"\1", s)

def ensure_table_width(s: str) -> str:
    """Safety net: wrap a bare \\begin{tabular} in a float table in \\adjustbox (idempotent)."""
    def wrap(m):
        env, ttype = m.group(0), m.group(1)
        if r"\adjustbox" in env:
            return env
        tab = re.search(r"\\begin\{tabular\}.*?\\end\{tabular\}", env, re.S)
        if not tab:
            return env
        width = r"\textwidth" if ttype == "table*" else r"\columnwidth"
        return env.replace(tab.group(0), r"\adjustbox{max width=" + width + "}{%\n" + tab.group(0) + "}", 1)
    return re.sub(r"\\begin\{(table\*?)\}.*?\\end\{\1\}", wrap, s, flags=re.S)

def process_section(sid: str, body: str, titles: dict, tables_above: bool, merge_cites: bool) -> str:
    """Prepend canonical \\section heading + apply (template-gated) post-processes."""
    body = body.strip()
    body = re.sub(r"^\s*\\section\*?\{[^}]*\}\s*", "", body)   # we own the heading
    body = strip_heading_numbers(body)
    if tables_above:
        body = move_table_captions_above(body)
    body = ensure_table_width(body)
    if merge_cites:
        body = merge_adjacent_cites(body)
    title = titles.get(sid, sid.replace("_", " ").title())
    return f"\\section{{{title}}}\n{body}\n"

# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def fill_template(tmpl: str, fields: dict) -> str:
    """Safe @@token@@ substitution (named, never KeyErrors). Unknown @@x@@ -> ''."""
    for k, v in fields.items():
        tmpl = tmpl.replace(f"@@{k}@@", str(v))
    tmpl = re.sub(r"@@[a-zA-Z0-9_]+@@", "", tmpl)   # blank any leftover token
    return tmpl

def assemble(workdir: Path) -> dict:
    spec, tdir = load_template(workdir)
    bp = json.loads((workdir / "blueprint.json").read_text())

    sections_spec = spec.get("sections") or []
    titles = {s["id"]: s.get("title", s["id"].replace("_", " ").title()) for s in sections_spec}
    spec_order = [s["id"] for s in sections_spec]
    tables_above = (spec.get("tables") or {}).get("caption_position", "above") == "above"
    merge_cites = (spec.get("citations") or {}).get("merge_adjacent", True)
    kw_cap = (spec.get("keywords") or {}).get("cap", 6)

    order = bp.get("section_order") or [s for s in spec_order
                                        if (workdir / "sections" / f"{s}.tex").exists()]
    sec_dir = workdir / "sections"
    includes = []
    for sid in order:
        f = sec_dir / f"{sid}.tex"
        if not f.exists():
            continue
        out = process_section(sid, f.read_text(), titles, tables_above, merge_cites)
        (sec_dir / f"{sid}.proc.tex").write_text(out)
        includes.append(f"\\input{{sections/{sid}.proc}}")

    authors = bp.get("authors") or []
    if authors:
        au = ", ".join(
            a["name"] + ("$^{%d*}$" % (i + 1) if a.get("corresponding") else "$^{%d}$" % (i + 1))
            for i, a in enumerate(authors))
        af = r" \\ ".join("$^{%d}$ %s" % (i + 1, a.get("affil", "")) for i, a in enumerate(authors))
        email = next((a.get("email", "") for a in authors if a.get("corresponding")), authors[0].get("email", ""))
    else:
        au = r"[AUTHORS TBD]$^{1*}$"
        af = r"$^{1}$ [Affiliation TBD]"
        email = "[CORRESPONDING EMAIL TBD]"

    abstract = bp.get("abstract", "")
    abs_f = sec_dir / "abstract.tex"
    if abs_f.exists():
        abstract = re.sub(r"^\s*\\section\*?\{[^}]*\}\s*", "", abs_f.read_text().strip())
    if (spec.get("abstract") or {}).get("single_paragraph", True):
        abstract = re.sub(r"\s*\n\s*\n\s*", " ", abstract).strip()

    mh = spec.get("masthead") or {}
    j = bp.get("journal", {})
    dates = bp.get("dates", {})
    fields = {
        "title": escape_latex(bp.get("paper_title", "Untitled")),
        "authors": au, "affil": af, "email": email,
        "doi": bp.get("doi", (mh.get("doi_prefix", "") + "XXXXXX") or "10.0000/x"),
        "received": dates.get("received", ""), "revised": dates.get("revised", ""),
        "accepted": dates.get("accepted", ""), "available": dates.get("available", ""),
        "keywords": format_keywords(bp.get("keywords", ""), kw_cap),
        "vol": j.get("vol", mh.get("default_vol", "")),
        "issue": j.get("issue", mh.get("default_issue", "")),
        "month": j.get("month", mh.get("default_month", "")),
        "year": j.get("year", mh.get("default_year", "")),
        "pstart": j.get("pstart", "1"), "pend": j.get("pend", "12"),
        "abstract": abstract.strip(),
        "sections": "\n".join(includes),
    }
    tmpl_name = (spec.get("engine") or {}).get("main_template", "main.tex.tmpl")
    tmpl = (tdir / tmpl_name).read_text()
    (workdir / "main.tex").write_text(fill_template(tmpl, fields))

    # copy the template's style/asset files (incl. .cls when is_class)
    assets = (spec.get("engine") or {}).get("assets", ["ts_iieta.sty", "iieta_logo.png"])
    copied = []
    for asset in assets:
        dst = workdir / asset
        for src in (tdir / asset, LEGACY_ASSETS / asset):
            if src.exists():
                if src.resolve() != dst.resolve():   # plan stage may have already copied it into the workdir
                    shutil.copy2(src, dst)
                copied.append(asset); break
    return {"template": spec.get("name", "ts_iieta"), "sections": len(includes),
            "order": order, "assets": copied}


def compile_pdf(workdir: Path) -> dict:
    env = dict(os.environ)
    tinytex = os.path.expanduser("~/.TinyTeX/bin/x86_64-linux")
    if os.path.isdir(tinytex):
        env["PATH"] = tinytex + os.pathsep + env.get("PATH", "")
    r = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                       cwd=str(workdir), env=env, capture_output=True, text=True)
    pdf = workdir / "main.pdf"
    log = (workdir / "main.log")
    tail, error_count = "", 0
    if log.exists():
        lines = log.read_text(errors="ignore").splitlines()
        errs = [l for l in lines if l.startswith("!")]
        error_count = len(errs)
        tail = "\n".join(l for l in lines if l.startswith("!") or "Error" in l or "Undefined" in l)[-1500:]
    return {"compiled": pdf.exists() and error_count == 0, "exit": r.returncode,
            "error_count": error_count, "error_tail": tail}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: assemble_paper.py <workdir> [--no-compile]"}))
        sys.exit(2)
    workdir = Path(sys.argv[1]).resolve()
    if "--backup" in sys.argv:
        bak = workdir / "sections.bak"; bak.mkdir(exist_ok=True)
        for f in (workdir / "sections").glob("*.tex"):
            if not f.name.endswith(".proc.tex") and not (bak / f.name).exists():
                shutil.copy2(f, bak / f.name)   # preserve the good baseline: never clobber an existing snapshot
    result = {"ok": True, "workdir": str(workdir)}
    result.update(assemble(workdir))
    if "--no-compile" not in sys.argv:
        result.update(compile_pdf(workdir))
        result["ok"] = bool(result.get("compiled"))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
