#!/usr/bin/env python3
"""Mechanical + structural linter for drafted section bodies — TEMPLATE-DRIVEN (no LLM).

    python draft_lint.py <workdir>

Two kinds of checks:
  * INVARIANT (template-independent — honesty + LaTeX safety, apply to EVERY template):
    fabricated numbers in prose, non-ASCII outside math, banned LaTeX in prose, numbered
    headings, markdown fences.
  * TEMPLATE-DRIVEN shape contracts read from `template.json` (copied into the workdir by
    the plan stage; falls back to bundled `ts_iieta`): per-section word bands, item counts,
    subsection counts, result-table order, display-math bans, notation-table requirement,
    single-paragraph / no-list rules, and the abstract length. These come from each
    section's `recipe` in the spec — NOT hardcoded to Traitement du Signal.

Prints a JSON list of violations; exits non-zero if any are found.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES_ROOT = HERE.parent.parent / "ts-paper" / "templates"

# --- INVARIANT: fabricated numbers in prose (outside math/tables/figures) ---
NUM_PATTERNS = [
    (r"\d+(?:\.\d+)?\s*%", "percent_in_prose"),
    # any decimal (incl >=1 like 1.8/12.4, not just 0.x) — fabricated metrics hide here.
    # Exclude Section/version refs (lookbehind) and common units (lookahead) to avoid false positives.
    (r"(?<![\w.$])(?<!Section )(?<!section )(?<!Sec\. )(?<!version )(?<!Version )(?<!v)"
     r"\d+\.\d+\b(?!\s*(?:GHz|Hz|dB|kHz|ms|s|mm|cm|seconds?|second)\b)", "decimal_in_prose"),
    # signed delta — exclude physical units (a signal-processing venue legitimately writes "-3 dB").
    (r"(?<![\w$])[+\-]\s?\d+(?:\.\d+)?\b(?!\s*(?:GHz|Hz|dB|kHz|ms|s|mm|cm|seconds?|second)\b)", "delta_in_prose"),
    # x-multipliers: 2.5x / 3x / 1.5× speedups are fabricated results in proposal mode.
    (r"(?<![\w.])\d+(?:\.\d+)?\s?[x×]\b", "multiplier_in_prose"),
    # word-form magnitudes, scoped to comparative/metric contexts so method idioms
    # ("halving the learning rate", "doubles as a regularizer", "three times per epoch") don't false-fire.
    (r"\b(?:doubl(?:e|es)|tripl(?:e|es)|quadrupl\w*|halv(?:e|es))\s+(?:the\s+)?"
     r"(?:accuracy|precision|recall|performance|throughput|speed|score|error|latency|runtime|fps|map|f1|auc|results?)\b"
     r"|\b(?:two|three|four|five|six|seven|eight|nine|ten)\s+times\s+"
     r"(?:faster|slower|better|worse|higher|lower|more|less|larger|smaller|greater)\b"
     r"|\b(?:ninety|eighty|seventy|sixty|fifty|forty|thirty|twenty)\s+percent\b",
     "word_form_number_in_prose"),
    (r"\[\s*[XY]\s*\]|\bXX\.X\b|\[TBD\]", "placeholder_token"),
]
# A decimal that is a DESIGN CONSTANT (hyperparameter) is not a fabricated result — exempt it,
# mirroring the bare-integer design-constant exemption. The cue must sit IMMEDIATELY before the
# number (anchored $ on the preceding window) so achievement/metric decimals ("achieves 0.72",
# "F1 of 0.85", "error rate of 0.9") are still flagged. Kept tight to unambiguous hyperparameters.
HYPERPARAM_CUE = re.compile(
    r"\b(?:learning[\s-]?rate|lr|dropout|momentum|weight[\s-]?decay|decay|"
    r"temperature|label[\s-]?smoothing|warm[\s-]?up|step[\s-]?size|epsilon)\b"
    r"\s*(?:of|=|:|to|at|is|was)?\s*$", re.I)
BANNED_LATEX = re.compile(r"\\textbf|\\textit\{|\\documentclass|\\usepackage|\\begin\{document\}")
HEADING_NUM = re.compile(r"\\(?:sub)*section\*?\{\s*\d")

# --- AI-tell phrases that are CONTEXT-FREE and almost never wanted in CS-paper prose — a regex flags
# them with ~zero false positives, so they HARD-FAIL the build. Cohesion devices whose acceptability
# DEPENDS ON CONTEXT are deliberately NOT here: the em-dash, sentence-initial connectives
# (firstly/moreover/furthermore/additionally), and "not only … but also". A regex cannot tell a
# legitimate appositive em-dash ("a pipeline — retrieval, planning — in which …") from em-dash abuse,
# and banning the token outright pushed the model to a bare-comma "comma soup" that reads as fragmented
# sentences (the very "碎句子" defect this split fixes). Those context-dependent tells are handled by
# JUDGMENT in the refine de-AI pass (Claude keeps the good uses, removes the abuse). Distilled from
# PaperJury's de-ai prompt. ---
AI_TELLS = re.compile(
    r"\bit is worth (noting|mentioning|emphasi[sz]ing)\b"
    r"|\bit should be noted\b"
    r"|\bplays? a (crucial|key|vital|pivotal|critical|central|significant) role\b"
    r"|\ba testament to\b"
    r"|\b(rich|intricate)\s+tapestry\b|\btapestry of\b"
    r"|\bdelv(e|es|ing) into\b"
    r"|\b(in|within) the realm of\b"
    r"|\bever-(evolving|changing|growing)\b"
    r"|\bin today'?s (world|era|landscape)\b"
    r"|\bnavigat(e|es|ing) the (landscape|complexit|intricac)"
    r"|\bparadigm shift\b|\bgame[- ]chang(er|ing)\b"
    r"|\bin order to\b",                                 # near-always replaceable by "to"
    re.IGNORECASE)

# --- DATA-AWARE number-audit (only when results_mode == "data_aware") ---
# Ground truth = the real numbers Claude extracted from the user's data (ANY form: CSV/JSON/
# pasted table/prose) into a simple `results.facts.json` — a flat list/dict/nested blob of the
# real values. Schema-AGNOSTIC: we just harvest every number it contains. We audit only
# DECIMAL/PERCENT numbers in prose (the form real results take); bare integers are treated as
# design constants/counts and not audited, so method's "256 dimensions" is never false-flagged.
COMMON_NUMS = {"0","1","2","3","4","5","10","100"} | {str(y) for y in range(2018, 2027)}
RESULT_NUM = re.compile(r"(?<![\w.])\d+\.\d+%?|(?<![\w.])\d+%")   # 0.94 / 18.3% / 92%


def _nums_in_text(s: str):
    return RESULT_NUM.findall(s)


def _norm_num(tok: str):
    return tok.rstrip("%")


def load_results_ground_truth(wd: Path):
    """Harvest every number from results.facts.json (any JSON shape). None if absent."""
    p = wd / "results.facts.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    gt = set()
    def walk(node):
        if isinstance(node, dict):
            for v in node.values(): walk(v)
        elif isinstance(node, list):
            for v in node: walk(v)
        elif isinstance(node, (int, float)):
            gt.add(_norm_num(f"{node:g}")); gt.add(_norm_num(str(node)))
        elif isinstance(node, str):
            for t in re.findall(r"(?<![\w.])\d+(?:\.\d+)?%?", node):
                gt.add(_norm_num(t))
    walk(data)
    return gt | COMMON_NUMS


def load_spec(wd: Path) -> dict:
    p = wd / "template.json"
    if p.exists():
        return json.loads(p.read_text())
    bundled = TEMPLATES_ROOT / "ts_iieta" / "template.json"
    return json.loads(bundled.read_text()) if bundled.exists() else {}


def strip_math_and_envs(s: str) -> str:
    s = re.sub(r"\$[^$]*\$", " ", s)
    s = re.sub(r"\\begin\{(table\*?|tabular[x*]?|minipage|equation|align|algorithm|figure\*?)\}.*?\\end\{\1\}", " ", s, flags=re.S)
    s = re.sub(r"\\rule\{[^}]*\}\{[^}]*\}", " ", s)
    s = re.sub(r"\d*\.?\d+\s*\\(?:column|text|line|page)width", " ", s)
    s = re.sub(r"\d*\.?\d+\s*(?:pt|cm|mm|em|ex|in|bp)\b", " ", s)
    s = re.sub(r"--", " ", s)
    return s


def word_count(s: str) -> int:
    s = strip_math_and_envs(s)
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", s)
    s = re.sub(r"[{}]", " ", s)
    return len([w for w in re.split(r"\s+", s) if re.search(r"[A-Za-z]", w)])


def add(out, f, rule, snip):
    out.append({"file": f, "rule": rule, "snippet": str(snip)[:80]})


# --- proposal-mode RESULT-TABLE cell audit (root-fix). The source product's renderer
# DETERMINISTICALLY emitted '--' for every proposal result cell (Story2Paper renderer
# _inject_placeholders), so a fabricated number in a result table was structurally impossible.
# The distillation hands table authoring to Claude, so code must keep the one irreducible
# invariant: in proposal mode every result-table DATA cell is blank. (strip_math_and_envs
# deletes table envs before the prose scan, so this scans the RAW body instead.) ---
def _strip_cell(cell: str) -> str:
    c = re.sub(r"\\(?:textbf|textit|mathbf|texttt|emph|multicolumn\{[^}]*\}\{[^}]*\})\b", "", cell)
    c = re.sub(r"[{}$]", "", c)
    for d in ("---", "--", "—", "–"):
        c = c.replace(d, "")
    return c.strip()


def _cell_has_number(cell: str) -> bool:
    return bool(re.search(r"\d", _strip_cell(cell)))


def result_table_cells(body: str, want_labels: set):
    """Yield (label, cell) for each NON-header, NON-row-label cell of every table/tabular env
    carrying a \\label{tab:<id>} in want_labels. Header = rows above the first \\midrule/\\hline;
    row-label = the first column (text, exactly as the source treats cols[0])."""
    for m in re.finditer(r"\\begin\{(table\*?|tabular[x*]?)\}.*?\\end\{\1\}", body, flags=re.S):
        env = m.group(0)
        labels = set(re.findall(r"\\label\{(tab:[^}]*)\}", env))
        hit = labels & want_labels
        if not hit:
            continue
        label = next(iter(hit))
        tab = re.search(r"\\begin\{tabular[x*]?\}(?:\{[^{}]*\}|\[[^\]]*\]|\s)*(.*?)\\end\{tabular[x*]?\}", env, flags=re.S)
        inner = tab.group(1) if tab else env
        parts = re.split(r"\\midrule|\\hline", inner, maxsplit=1)
        if len(parts) > 1:
            data = re.split(r"\\bottomrule", parts[1])[0]        # header is above the rule -> dropped
        else:
            # no \midrule/\hline separator: drop the FIRST row as the header rather than
            # auditing it as data (a header like "F1 (95% CI)" must not be flagged).
            rows0 = re.split(r"\\\\", re.split(r"\\bottomrule", inner)[0])
            data = "\\\\".join(rows0[1:])
        for row in re.split(r"\\\\", data):
            if not row.strip() or re.fullmatch(r"(?:\\(?:mid|top|bottom)rule|\\hline|\s)*", row):
                continue
            for cell in re.split(r"(?<!\\)&", row)[1:]:   # skip the row-label (first) column
                if cell.strip():
                    yield label, cell.strip()


# --- notation-completeness (root-fix, new ts-paper need): a fix that adds a symbol to an
# equation must define it (notation table or inline). Conservative GREEK-only scope: Greek
# commands appear only in math and almost always denote a notation entry; biasing to UNDER-flag
# (operators/constants excluded) means a benign macro never blocks the build. Catches the
# \psi-class orphan that draft_lint + the review verifier both missed. ---
_GREEK = set(("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda "
              "mu nu xi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega "
              "Gamma Delta Theta Lambda Xi Sigma Upsilon Phi Psi Omega").split())
_GREEK_OPS = {"pi", "Pi", "Delta", "nabla", "partial"}   # constants/operators, not notation symbols
_GREEK_SYMS = _GREEK - _GREEK_OPS


def _greek_bases(text: str) -> set:
    out = set()
    for m in re.finditer(r"\\([a-zA-Z]+)", text):
        if m.group(1) in _GREEK_SYMS and text[m.end():m.end() + 1] != "(":  # exclude \sigma( ... (function use)
            out.add(m.group(1))
    return out


_DISPLAY_ENV = r"(?:equation|align|gather|multline|eqnarray|displaymath)\*?"


def _display_math(body: str) -> str:
    chunks = re.findall(r"\\begin\{" + _DISPLAY_ENV + r"\}(.*?)\\end\{" + _DISPLAY_ENV + r"\}", body, flags=re.S)
    chunks += re.findall(r"\\\[(.*?)\\\]", body, flags=re.S)
    return "\n".join(chunks)


def _inline_math_prose(body: str) -> str:
    """Inline $...$ that sits in prose (a symbol MENTION/definition), i.e. not inside a display env."""
    nodisp = re.sub(r"\\begin\{" + _DISPLAY_ENV + r"\}.*?\\end\{" + _DISPLAY_ENV + r"\}", " ", body, flags=re.S)
    nodisp = re.sub(r"\\\[.*?\\\]", " ", nodisp, flags=re.S)
    return " ".join(re.findall(r"\$[^$]*\$", nodisp))


def notation_orphans(body: str) -> list:
    """A Greek symbol is an orphan if it is USED in a display equation but DEFINED nowhere.
    "Defined" = it appears in an INLINE `$...$` (a mention/definition in prose OR a notation-table
    cell — those cells are inline math too), e.g. 'the weights $\\Theta$' or a `$\\beta_Q,\\beta_E$ &`
    table row. Using inline-$ as the whole 'defined' set (rather than a fragile Notation-subsection
    regex) makes the check LAYOUT-INDEPENDENT: a symbol's appearance inside a DISPLAY equation is always
    a USE, never a definition, even if that equation sits inside the Notation subsection. Bias to
    under-flag, so only a truly-undefined symbol like a fix-introduced \\psi is caught."""
    used = _greek_bases(_display_math(body))
    defined = _greek_bases(_inline_math_prose(body))
    return sorted(used - defined)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: draft_lint.py <workdir>"})); sys.exit(2)
    wd = Path(sys.argv[1]).resolve()
    spec = load_spec(wd)
    sec = wd / "sections"
    sections_spec = {s["id"]: s for s in (spec.get("sections") or [])}
    abstract_spec = spec.get("abstract") or {"words": [120, 180], "single_paragraph": True}

    # results_mode gates ALL data-aware behavior; proposal mode is byte-for-byte unchanged.
    results_mode = spec.get("results_mode", "proposal")
    ground_truth = load_results_ground_truth(wd) if results_mode == "data_aware" else None

    # word bands: the TEMPLATE spec is authoritative (changing the template changes the
    # bands without editing each blueprint); the blueprint only fills sections absent from spec.
    bands = {sid: s.get("words") for sid, s in sections_spec.items() if s.get("words")}
    if (wd / "blueprint.json").exists():
        bp = json.loads((wd / "blueprint.json").read_text())
        for sid, s in (bp.get("sections") or {}).items():
            tw = s.get("target_words")
            if sid not in bands and isinstance(tw, (list, tuple)) and len(tw) == 2:
                bands[sid] = tw

    out = []
    if results_mode == "data_aware" and ground_truth is None:
        add(out, "(paper)", "missing_results_facts",
            "data_aware mode needs results.facts.json (the real-number set Claude extracted from the user's data)")
    files = {f.stem: f for f in sec.glob("*.tex") if not f.name.endswith(".proc.tex")} if sec.is_dir() else {}

    # ---- INVARIANT per-file checks (every template) ----
    for sid, f in files.items():
        raw = f.read_text()
        prose = strip_math_and_envs(raw)
        if results_mode == "data_aware":
            # data-aware: real result numbers are EXPECTED; flag only decimal/percent numbers in
            # prose that aren't in the real-number set (bare integer design-constants aren't audited).
            gt = ground_truth or COMMON_NUMS
            for tok in _nums_in_text(prose):
                if _norm_num(tok) not in gt:
                    add(out, f.name, "suspicious_number", f"{tok} not in results.facts.json")
            for m in re.finditer(r"\[\s*[XY]\s*\]|\bXX\.X\b|\[TBD\]", prose):
                add(out, f.name, "placeholder_token", m.group(0))
        else:
            # proposal mode: ban any result number in prose. Exempt design-constant
            # decimals (hyperparameters like "learning rate 0.001") — not fabricated results.
            for pat, rule in NUM_PATTERNS:
                for m in re.finditer(pat, prose):
                    if rule == "decimal_in_prose" and HYPERPARAM_CUE.search(prose[max(0, m.start() - 30):m.start()]):
                        continue
                    add(out, f.name, rule, m.group(0))
        for m in re.finditer(r"[^\x00-\x7f]", prose):
            add(out, f.name, "non_ascii_outside_math", m.group(0))
        for m in BANNED_LATEX.finditer(prose):
            add(out, f.name, "banned_latex_in_prose", m.group(0))
        for m in HEADING_NUM.finditer(raw):
            add(out, f.name, "number_in_heading", m.group(0))
        if re.search(r"```", raw):
            add(out, f.name, "markdown_fence", "```")
        for m in AI_TELLS.finditer(prose):
            add(out, f.name, "ai_tell", m.group(0))   # de-AI: high-precision tell phrase
        # word band (abstract has a dedicated check below; everything else uses its band)
        b = bands.get(sid)
        if sid != "abstract" and isinstance(b, (list, tuple)) and len(b) == 2:
            wc = word_count(raw); lo, hi = b
            if wc < lo or wc > hi:
                add(out, f.name, "word_band", f"{wc} words (want {lo}-{hi})")

    def body(sid):
        return files[sid].read_text() if sid in files else ""

    # ---- abstract (dedicated, from spec) ----
    if "abstract" in files:
        aw = abstract_spec.get("words", [120, 180])
        lo, hi = (aw + [120, 180])[:2]
        wc = word_count(body("abstract"))
        if not (lo - 10 <= wc <= hi + 20):
            add(out, "abstract.tex", "abstract_wordcount", f"{wc} (want {lo}-{hi})")
        if abstract_spec.get("single_paragraph", True) and "\n\n" in body("abstract").strip():
            add(out, "abstract.tex", "abstract_multi_paragraph", "must be one paragraph")

    # ---- TEMPLATE-DRIVEN per-section recipe checks ----
    for sid, sspec in sections_spec.items():
        if sid not in files:
            continue
        b = body(sid); fn = f"{sid}.tex"
        recipe = sspec.get("recipe") or {}

        ci = recipe.get("contrib_items")
        if isinstance(ci, int) and ci > 0:
            n = len(re.findall(r"\\item\b", b))
            if n != ci:
                add(out, fn, "contrib_items", f"{n} \\item (want exactly {ci})")

        ns_target = recipe.get("subsections", recipe.get("theme_subsections"))
        if isinstance(ns_target, int) and ns_target > 0:
            ns = len(re.findall(r"\\subsection\b", b))
            if ns != ns_target:
                add(out, fn, "subsection_count", f"{ns} \\subsection (want exactly {ns_target})")

        rtabs = recipe.get("result_tables")
        if isinstance(rtabs, list) and rtabs:
            # Claude writes the result tables itself, in order, each with \label{tab:<id>}.
            # Proposal mode -> every DATA cell must be blank '--' (the result_table_cells audit below
            # machine-enforces it, restoring the source renderer's structural guarantee). Data-aware
            # -> real numbers are expected in cells; they are NOT cell-audited here (a known gap — the
            # prose number-audit above only sees prose, since strip_math_and_envs removes tables).
            want = [f"tab:{t}" for t in rtabs]
            got = re.findall(r"\\label\{(tab:[^}]*)\}", b)
            if got != want:
                add(out, fn, "result_table_order", f"{got} (want {want})")
            if results_mode != "data_aware":
                for label, cell in result_table_cells(b, set(want)):
                    if _cell_has_number(cell):
                        add(out, fn, "fabricated_number_in_result_table", f"{label}: {cell}")

        if recipe.get("display_math") is False:
            if re.search(r"\\begin\{(equation|align|gather|multline)\}|\\\[|\$\$", b):
                add(out, fn, "display_math_not_allowed", f"no display math allowed in {sid}")

        if recipe.get("require_notation_table"):
            if not re.search(r"\\subsection\{\s*Notation", b):
                add(out, fn, "method_notation_subsection", "missing \\subsection{Notation}")
            if "tab:notation" not in b:
                add(out, fn, "method_notation_table", "missing tab:notation reference/label")
            # every Greek symbol used in an equation must be defined (notation table or inline) —
            # catches a fix that adds a symbol to an equation without defining it (the \psi orphan).
            for sym in notation_orphans(b):
                add(out, fn, "notation_incomplete",
                    f"\\{sym} used in an equation but not defined in the notation table or inline")

        if recipe.get("paragraphs") == 1 and "\n\n" in b.strip():
            add(out, fn, "must_be_single_paragraph", f"{sid} must be one paragraph")
        if recipe.get("lists") is False and re.search(r"\\begin\{(itemize|enumerate)\}|\\item\b", b):
            add(out, fn, "no_lists", f"no lists in {sid}")

    # global figure floor: the whole paper must carry >= template figures.min figure environments
    fig_min = (spec.get("figures") or {}).get("min", 0)
    if fig_min:
        total_figs = sum(len(re.findall(r"\\begin\{figure\*?\}", body(sid))) for sid in files)
        if total_figs < fig_min:
            add(out, "(paper)", "figure_floor",
                f"{total_figs} figures < template minimum {fig_min} (add schematic/conceptual figures)")

    print(json.dumps({"ok": not out, "template": spec.get("name", "ts_iieta"),
                      "n": len(out), "violations": out}, indent=2))
    sys.exit(0 if not out else 1)


if __name__ == "__main__":
    main()
