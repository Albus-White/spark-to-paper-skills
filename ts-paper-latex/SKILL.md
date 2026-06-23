---
name: ts-paper-latex
description: >
  Stage 7 (final assemble + compile) of the ts-paper suite. Assemble drafted LaTeX section bodies +
  refs.bib + blueprint into a compilable paper in the active TEMPLATE and compile it to PDF. Copies the
  template's .sty/.cls + assets, runs the deterministic template-driven post-processes (caption position,
  merge adjacent \cite for numeric styles, canonical headings from the spec, keyword formatting), and
  compiles once per call; the agent drives a bounded error-fix loop around it. Use to build/compile the final PDF.
---

# ts-paper-latex — assemble & compile the paper PDF (template-driven)

Turn the finished `sections/<id>.tex` + `refs.bib` + `blueprint.json` into a compiled
`main.pdf`. **This stage never authors or alters content** — no renaming methods/datasets, no
filling result numbers (proposal = blank cells stay blank). It is format + assembly + compile only.

**Template-driven:** `assemble_paper.py` reads `template.json` from the workdir and threads it
through everything — section order + headings, table/figure **caption position**, keyword **cap**,
whether to **merge `\cite`** (numeric templates only), and the **preamble** (the template's own
`main.tex.tmpl`, filled by safe `@@token@@` substitution) + which **`.sty`/`.cls` + assets** to copy.
The default template is `ts_iieta` (two-column IIETA); `neurips` (single-column author-year) is also
bundled and compiles through the *same* script — nothing here is hardcoded to TS. If no `template.json`
is in the workdir it falls back to bundled `ts_iieta` (backward-compatible).

## What's bundled (clean, copyright-safe assets you own)
- `assets/ts_iieta.sty` — our own two-column IIETA style (masthead with logo + blue band, 10pt Times, ALL-CAPS numbered sections, `Figure N.`/`Table N.` captions, numeric `[n]` cites with `sort&compress`).
- `assets/iieta_logo.png` — the masthead logo (compiles fine if absent via `\IfFileExists`).
- `scripts/assemble_paper.py` — the deterministic backbone.

## Run it
```bash
python scripts/assemble_paper.py <workdir>
```
The script: reads `blueprint.json` (title, keywords, abstract, `section_order`, optional authors/doi/dates/journal); for each `sections/<id>.tex` applies the post-processes and prepends the canonical ALL-CAPS heading; builds `main.tex` from the TS template; copies `ts_iieta.sty` + `iieta_logo.png` into the workdir; runs `latexmk -pdf`. It prints a JSON status `{ok, compiled, exit, error_count, error_tail, sections, order, assets, template, workdir}`.

### Deterministic post-processes it applies (no LLM)
- **Table captions ABOVE** the tabular (IIETA convention) — both inline minipage and floating `table`/`table*`.
- **Merge adjacent `\cite`** runs into one (`\cite{a} \cite{b}` → `\cite{a,b}`) so they render as `[1, 2]` / `[3-5]` with the style's `sort&compress`.
- **Canonical section headings** — strips any heading the writer added and forces `Introduction / Related Works / Methodology / Experimental Results / Discussion and Analysis / Conclusion`, which the style renders as `1. INTRODUCTION` …
- **Strip heading numbers** (`\subsection{3.1 Foo}` → `Foo`), **table-width safety net** (wraps a bare `\begin{tabular}` in `\adjustbox`), **single-paragraph abstract** merge.
- **Keyword formatting** — dedup, cap 6, comma-join into the `\tsSetKeywords` macro (empty → the line is omitted).
- The bundled `ts_iieta.sty` also loads `inputenc[utf8]` as a Unicode compile-net.

## Compile + fix loop (quality gate — do not skip)
- The **agent owns the ≤3-try fix loop**; the script compiles once per call and only **renders the verdict** (no script-side loop). The script reports `compiled` (PDF exists AND `error_count == 0` — it already **trusts the log, not the exit code**) and a structured `error_count`. Success also requires `main.bbl` resolved (no `[?]` citations). Treat `error_count > 0` as a **red gate that blocks done**.
- Run with `--backup` on the **FIRST attempt only** so `sections/` is snapshotted to `sections.bak/` (rollback if a fix makes it worse) — do not re-pass `--backup` on later attempts or you overwrite the good baseline.
- If `compiled:false` or `error_count > 0`, read `error_tail`, then **edit the offending `sections/*.tex` with minimal, syntax-only fixes** (close unbalanced `$`/environments, escape stray `& % # _` in text, fix mispaired `\begin/\end`, `1-10`→`1--10`). **Never** change content, math semantics, citations, labels, or `--` placeholders.
- Re-run. **Bounded at ~3 attempts; if `error_count` goes UP, restore from `sections.bak/` and report** rather than thrash.
- One figure-specific error class: a `File \`figures/<label>' not found` or a bad-bounding-box error is **not** a content bug — fix it by **re-running the figure stage** (regenerate the missing `.pdf`/`.png`), never by editing section prose.
- Finally write **`logs/7_latex.io.md`** (INPUT: section files + refs.bib; DECISIONS: each compile error + the minimal fix; OUTPUT: main.pdf page count, error_count=0), and `logs/index.md` linking every stage's log.

## Figures embed as vector PDF (no extra wiring)
Figures are referenced **extension-less** — `\includegraphics{figures/<label>}` — and the figure stage
ships `figures/<label>.pdf` (editable vector) beside the kept `figures/<label>.png`. Both bundled `.sty`
already `\RequirePackage{graphicx}`, so under pdflatex/latexmk the `.pdf` is embedded (its extension is
preferred over `.png`) with **no change to `assemble_paper.py`** (it never parses `\includegraphics` or
figure extensions). The vector is pre-rendered by cairosvg (in `ts-figure-optimize`'s hybrid export), so there is **no
`\includesvg`/Inkscape/`--shell-escape` dependency**. The `run_gates.py all` vector check confirms every
figure has its `.pdf` sibling — a raster-only figure is a red gate.

## Front matter / metadata
Authors/affiliation/email/DOI/dates default to clearly-marked placeholders (`[AUTHORS TBD]`, `10.18280/ts.XXXXXX`) for a proposal — that is correct; fill real values only if the user provides them in `blueprint.json` (`authors`, `doi`, `dates`, `journal`).

## Done check
Report: page count, sections included, that captions are above tables, cites merged, keywords present, and that the citation linter (`ts-paper-cite/scripts/citations_lint.py`) passes with zero stubs/orphans.
