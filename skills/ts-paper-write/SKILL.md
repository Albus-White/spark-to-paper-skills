---
name: ts-paper-write
description: >
  Stage 3 of the ts-paper suite. Draft every section of a Traitement du Signal paper as LaTeX body
  files (sections/<id>.tex + abstract.tex) from the blueprint and refs.bib, following strict
  per-section recipes, the no-fabricated-results rule, and IIETA citation style. Write ALL sections
  in one pass. Use when writing the body of a TS proposal paper.
---

# ts-paper-write — draft all sections (LaTeX body)

**Quality is the goal.** Write **all** sections in one holistic pass when you can (you hold the whole
paper in context, so terminology stays consistent and nothing is re-explained) — but a section that
isn't genuinely good gets rewritten until it is. Output one LaTeX **body** file per section into
`sections/<id>.tex`, plus `sections/abstract.tex`. Aim for prose a TS reviewer would accept: precise,
specific, well-argued — not filler that merely hits the word count.

## The one rule that overrides everything: no fabricated results
This is a **proposal — there are no real experiments.** Forbidden anywhere in a *sentence*: any
concrete metric/percentage/score/delta (`18.3%`, `0.72 F1`, `+0.05`, "beats SOTA by X points") and
stand-ins (`[X]%`, `XX.X`, `[TBD]`). Write **forward-looking**: "We evaluate X on three benchmarks
and report results in Table~\ref{tab:main_results}; we expect Y because Z." The only place `--` may
appear is inside a results **table cell**, never in prose.

**What the number-audit catches in code vs self-review:** in proposal mode `draft_lint` hard-fails these
prose number forms — percentages (`18.3%`), decimal scores (`0.72`, and any decimal `≥ 1` such as `1.8`),
signed deltas (`+0.05`), x-multipliers (`2.5x`), word-form magnitudes (`doubles`, `three times`,
`ninety percent`), and placeholder tokens (`[X]%`, `XX.X`, `[TBD]`). Bare integers are treated as design
constants/counts and are **not** audited (so "256 dimensions" / "Section 3.2" / a year never false-flags) —
so any *fabricated bare-integer result* is a judgment item you must self-review, the code will not catch it.

## Output format (LaTeX body files)
- Each `sections/<id>.tex` contains **body content only** — NO `\documentclass`/`\usepackage`/`\begin{document}`/`\title`, and **NO top-level `\section{}`** (the assemble stage adds the canonical ALL-CAPS heading). Use `\subsection{...}` / `\subsubsection{...}` for structure; never put a number in a heading (LaTeX auto-numbers); never `\label` a heading.
- **One physical line per paragraph.** Write each paragraph (and each `\item`/`\caption`) as a SINGLE line — do NOT hard-wrap prose mid-sentence at ~80/100 columns. Separate paragraphs with one blank line. A single newline is just a space in LaTeX, so wrapping is invisible in the PDF, but a hard-wrapped `.tex` reads as choppy "broken" writing to a human browsing the source. (The assemble stage also runs `reflow_tex.py` as a net, but write it clean from the start.)
- **No bold in running prose** (TS house style). Emphasis only in captions. No `\textbf`/`\begin{itemize}` mid-paragraph except the intro contribution list.
- Math: inline `$...$`; display as numbered `\begin{equation}...\end{equation}` (no `\[...\]`, no starred envs). Always use LaTeX commands for symbols (`$\Delta$`, `$\alpha$`, `$\leq$`) — **never raw Unicode** (the #1 compile-killer). Split display lines >~60 chars with `align`/`split` (two columns are narrow).
- Citations: emit `\cite{bibkey}` immediately after the supported claim's sentence; group adjacent ones as `\cite{k1,k2}`. Only cite real bibkeys present in `refs.bib`. Claims about *your own* method get no citation. No citations in abstract or headings. Cross-domain ban: cite only same-task / nearest-technical lineage.
- Write substantive, **flowing** full paragraphs — connected prose, NOT a comma-separated list of clauses. Punctuate an appositive/enumeration with a **colon or em-dash**, never a bare comma: write "a pipeline: retrieval, planning, drafting" or "a pipeline — retrieval, planning, drafting — in which …", NOT "a pipeline, retrieval, planning, drafting, in which …" (that bare-comma *comma soup* is exactly what reads as fragmented "碎句子"). Vary sentence length, use real transitions, keep terminology consistent (use the blueprint's `terminology` names exactly). **Write human from the start — avoid AI tells.** `draft_lint` **hard-fails (`ai_tell`)** only the CONTEXT-FREE canned phrases *in code*: "it is worth noting", "plays a crucial role", "a testament to", "tapestry", "delve into", "realm of", "paradigm shift", "navigating the landscape", "ever-evolving", … plus `in order to`. The CONTEXT-DEPENDENT cohesion tells — **em-dashes, sentence-initial `firstly/moreover/furthermore/additionally,`, `not only … but also`, rule-of-three triplets, `leverage`/`utilize`** — are **judgment-only** (deliberately NOT code-caught: a regex can't tell a legitimate appositive em-dash from abuse, and banning the token outright produced the comma soup). You and `ts-paper-refine`'s de-AI pass keep the good uses and remove the abuse by taste. Banned filler: "In this section we", "As mentioned above", "Recall that".

## Per-section recipes
**abstract** (`sections/abstract.tex`) — one unbroken paragraph, **150–220 words** (ts_iieta band), no heading, no citations, no math, all acronyms spelled out. Four beats: (1) problem + why it matters, (2) precise technical gap, (3) method + the specific mechanism/insight, (4) evaluation scope + hedged outcome. Qualitative outcome claims only ("consistently improves") — never a number.

**introduction** — exactly **5 paragraphs**: (1) background + real-world stakes, ≥2 cites; (2) gap/attack on prior methods, ≥4 cites each followed by a *concrete* limitation ("X cannot handle…"); (3) our method + key insight, 0 cites/0 numbers; (4) validation scope, hedged, no numbers, may reference Table~1/Section~4; (5) a lead-in sentence then a 3-item contribution list (`\begin{itemize}` with exactly 3 `\item`, no heading), each naming a specific component + 1–2 competing methods (cited) + the concrete difference. ≥8 cites total; ~800–1200 words (ts_iieta band) — substantive paragraphs, not terse.

**related_work** — by **theme, never chronology**. Use the template's `theme_subsections` count of theme `\subsection{}`s (ts_iieta = **EXACTLY 3**: Theme A = task/benchmark lineage, Theme B + Theme C = two technical-mechanism / adjacent lineages) — followed by a **plain closing paragraph with NO `\subsection` heading** (`draft_lint` enforces exactly that many `\subsection`s — no more, no fewer; the closing paragraph itself is a recipe requirement you satisfy, not a code check). Each theme: per representative paper, one technique sentence + one contrast/limitation tied to your setting; end each theme with an explicit technical gap ("However, these do not address…, which we resolve by…"). **5–9 cites/theme (≈15–27 total)** — this section carries the bulk of the well-read 40–50 reference set; the closing paragraph contrasts the single nearest paper and bridges to Method.

**method** — `\subsection{Problem Formulation}` → `\subsection{Notation}` (render a small notation table as an inline minipage `tabularx`, see table pattern below; one intro sentence) → one `\subsection{}` per component → `\subsection{Training Objective}`. Every subsection opens with prose before any equation. Define every symbol before use; fully specify each learned module (write the actual MLP, not "Enc(C)"); name the differentiable approximation if discrete selection is used. For **each** component give a Design Rationale (the obvious alternative, why rejected, what your choice enables). Include **≥1 pseudocode block** for the main procedure — write it as an `algorithm`+`algpseudocode` (algorithmicx) environment placed right after the paragraph that first references `Algorithm~\ref{...}`; use the **mixed-case** macros `\State`/`\For`/`\While`/`\If`/`\Require`/`\Ensure` (NOT uppercase `\STATE` — the `.sty` loads `algpseudocode`, not `algorithmic`); keep identifiers short. **This is the longest section — target ~2000–3000 words (ts_iieta band):** give each component its own `\subsection{}` with full formalization, the design rationale, and complexity/where-it-helps discussion. Add depth (more real detail), never filler, to reach the band.

**experiments** — exactly 3 `\subsection{}`: `Implementation Details` (1 paragraph: hardware, framework, optimizer, LR, batch, epochs, preprocessing; no equations), `Experimental Design` (1 paragraph: datasets name/size/domain/why, metrics + what higher means, baselines + why; no equations), `Results` (place the 3 result tables in order — `main_results`, `secondary_results`, `ablation_results` — each immediately before its discussion; results prose ~600–900 words **grouped by outcome pattern**, all forward-looking, no numbers). The section targets ~1000–1500 words total (ts_iieta band). Cells are `--`.

**analysis** — separate from experiments, **no math**. ~900–1400 words (ts_iieta band): 2–3 analysis `\subsection{}`s (Ablation Study, Component Analysis, Sensitivity/When-it-helps) **plus** a **required** Failure Mode Analysis (scenario, why it struggles, mitigation). Every comparative observation must reference a specific Table/Figure ("As shown in Table~\ref{tab:ablation_results}, …"). Directional predictions allowed if framed as predictions.

**conclusion** — exactly one paragraph, no lists/numbers/math, ~200–280 words: summary, key takeaway, one limitation, forward direction. **Hedged only** ("demonstrates potential", "suggests"); banned: "proves", "guarantees", "revolutionary". Don't copy the intro's contribution wording.

## Table & figure LaTeX patterns
Results table (≤5 cols → `table`; >5 cols → `table*`), caption goes ABOVE (assemble enforces this), cells `--`:
```latex
\begin{table}[htb]\centering\normalsize\setlength{\tabcolsep}{3pt}
\caption{Main results on <task> across the reported metrics.}\label{tab:main_results}
\adjustbox{max width=\columnwidth}{%
\begin{tabular}{lccc}\toprule
Method & M1 & M2 & M3 \\ \midrule
Baseline A & -- & -- & -- \\
<Method> (Ours) & -- & -- & -- \\
\bottomrule\end{tabular}}
\end{table}
```
Notation table (inline, in method): `\par\noindent\begin{minipage}{\columnwidth}\centering ... \begin{tabularx}{\columnwidth}{@{}l X@{}}\toprule Symbol & Meaning \\ \midrule $x$ & ... \\ \bottomrule\end{tabularx}\captionsetup{type=table}\captionof{table}{Notation.}\label{tab:notation}\end{minipage}\par`
Figure (placeholder, caption BELOW). Emit a machine-readable **FIGURE-SPEC** comment so the later
`ts-paper-figure` stage knows what to draw (or to skip). `type` is renderable
`{architecture, pipeline, framework, concept, schematic, overview, qualitative, diagram, flow}` for a
true depiction of the method, or skip-it `{results, plot, curve, bar, chart}` for a quantitative
results figure (which stays a placeholder — a proposal has no real data to plot):
```latex
\begin{figure}[htb]\centering
%% FIGURE-SPEC type=architecture
%% DESC: one concise line — the exact boxes, arrows, and data flow to draw, in the paper's own terms
\fbox{\rule{0pt}{3cm}\rule{0.9\columnwidth}{0pt}}
\caption{...}\label{fig:...}\end{figure}
```
**Emit at least `template.figures.min` (TS = 5) figure placeholders, distributed across method /
experiments / analysis** (per the blueprint). These are **DRAWABLE schematic / conceptual / qualitative
diagrams** (architecture overview, a component-detail diagram, the formation-graph concept, a qualitative
crossing-event scenario with NO numbers, the stratification-protocol concept, …) — each one a real
contribution to understanding, not padding. **Results figures follow `template.results_mode`:** in
**`proposal`** mode (no data) emit **NO `type=results` figure at all** — quantitative results go in the
experiment TABLES (blank `--`); there is nothing to plot, so don't place or substitute a results figure.
In **`data_aware`** mode emit results figures too, drawn from the real data. Use an **extension-less**
`\includegraphics{figures/<label>}` directly only if a real image already exists. The `ts-paper-figure`
stage replaces each `\fbox{...}` with the figure and ends it as an **editable vector PDF** (extension-less
so pdflatex embeds `figures/<label>.pdf`, the original `.png` kept). `draft_lint` fails the build if fewer
than `figures.min` figures are present.

## DATA-AWARE MODE (only when `template.results_mode == "data_aware"`)
When the router set data-aware (real results present), the no-fabrication rule **inverts** for each
result-bearing section the active template defines — **abstract + experiments always**, plus any
`analysis` / `results` / `limitations` section present in `template.sections` (e.g. ts_iieta also has
`analysis`; neurips has neither `analysis` nor `limitations`): **require real numbers in definitive past
tense.** `method` / `related_work` / `introduction` carry no results numbers. All proposal-mode rules above stay in force in `proposal` mode.
**ts-paper-data owns the data handling** (reading the data in any form, the `results.facts.json` real-number
set, the plot helper) — this section is just the writing rules.

**Global data-aware rules:**
- **Past tense, real numbers** ("achieved 0.62 HOTA, outperforming the 0.47 baseline") — never "we expect".
- **Forward-looking language FORBIDDEN** for obtained results; the experiments are done, report what happened.
- **Every number you write must be in `results.facts.json`** (the real-number set extracted in ts-paper-data
  Step 1). `draft_lint` (data-aware) flags any prose decimal/percent not in it as `suspicious_number`
  (build-failing). Keep table and prose numbers identical.
- **TBD = stay silent** (withheld evidence — make no claim about that metric); a `null` cell → `--`.
- **Cross-section consistency:** a metric is formatted identically everywhere; abstract/conclusion
  headline numbers equal the table values.

**Per-section (data-aware):**
- **abstract** — beat 4 states the 2–3 most impactful real numbers in past tense; no vague outcomes.
- **experiments** — Implementation Details + Experimental Design unchanged. **Results** prose uses real
  numbers in past tense (no `--` in prose, no forward-looking). **Write the result tables YOURSELF** — the
  same `\begin{tabular}` pattern as proposal mode, `\label{tab:<id>}` in the recipe order, but with the
  **real measured numbers** in the cells (`null`→`--`, `"TBD"`→`TBD`). State the actual ablation delta per
  variant + the mechanism. (No markers, no auto-filler — Claude fills it.)
- **analysis** — evidence-grounded, past tense; **do NOT restate the Experiments numbers** — cite the
  table and explain the **mechanism/why**; every ablation variant with its actual delta; failure modes
  grounded in **actual** data patterns (inventing un-observed ones is forbidden).
- **conclusion** — summarise contributions WITH the key real results; definitive past tense; no forward-looking.
- **limitations** (only if the template defines a limitations section) — quantify each weakness with its
  real value; surface any data-revealed weakness honestly; never invent or downplay one.

**Results figures (data-aware):** for each planned results plot, write a small **self-contained**
matplotlib script (embedding the real numbers) and render it —
`python3 ../ts-paper-data/scripts/plot_results.py --script figures/<label>.plot.py --out figures/<label>.png`
— precise, never the image model. Then run `draft_lint.py` (auto-detects data-aware from `template.json`
and applies the number-audit). Full details: **ts-paper-data**.

## Template-driven (de-templatized)
The per-section **recipes and word bands are read from `template.json`** in the workdir — the
counts below (5 intro paragraphs, exactly 3 `\item`, exactly 3 related_work themes, 3 result tables,
notation table, etc.) are the **`ts_iieta` defaults**; treat `template.json` (not these numbers) as
the source of truth. For another template, follow **its** section
ids + `recipe` + `words` (e.g. NeurIPS: section `approach` not `method`, no fixed contribution-item
count, 2 result tables, author-year citations). What is **invariant** (every template): no fabricated
results, hedged forward-looking tone, design rationales, terminology consistency, no bold in prose.
**Citation style:** if `template.citations.style == "author_year"`, write `\citep{key}` / `\citet{key}`
(not bare `\cite`); for `numeric` (TS) `\cite{key}` is fine.

## After drafting (enforced, do not skip)
Run `python scripts/draft_lint.py <workdir>` and fix **every** reported violation in one edit pass.
Re-run until `draft_lint.py` exits 0 (`ok:true`); do not hand off to refine on a nonzero exit. It is
**template-driven** and enforces, **in code**, exactly: the INVARIANT honesty/safety checks (fabricated
numbers, any non-ASCII outside math, bold-in-prose, numbered headings, markdown fences) on every
template, plus the **template's** per-section recipe shape contracts — `contrib_items`, the theme/section
`subsections` (`theme_subsections`) count, `result_tables` order + labels, the `display_math` ban,
`require_notation_table`, and the single-paragraph (`paragraphs:1`) / no-list (`lists:false`) rules — the
figure floor (`figures.min`), and the **per-section word bands read from `template.json`**. For the
`ts_iieta` default that means: abstract = 1 paragraph / 150–220 w; introduction = exactly 3 `\item`;
related_work = exactly 3 theme `\subsection`s; experiments = 3 ordered subsections + the 3 result-table
labels in order + no display math; method = a `\subsection{Notation}` referencing `tab:notation`;
conclusion = 1 paragraph, no lists, 200–280 w. If a section is under/over its word band, that is a real
finding for refine — do not ignore it. **NOT code-enforced (judgment-only — you must satisfy these
without a code backstop):** `min_cites`, `cites_per_theme`, `closing_paragraph`, `min_pseudocode`,
`design_rationale`, `require_failure_mode`, and `tables.min`.

Then do a single holistic self-review as a strict reviewer for the judgment items the linter can't check (citation-claim match, design rationales present, hedging tone, term consistency, **and prose flow — read each paragraph as connected prose, fixing any bare-comma "comma soup" into colon/em-dash/separate sentences**) and fix. Run **`python scripts/reflow_tex.py <workdir>`** to normalize every `sections/*.tex` to one logical line per paragraph (idempotent, PDF-neutral — the source must not be hard-wrapped mid-sentence). Also emit **`claims_map.json`** (see ts-paper-cite) so the citation linter can verify every `\cite`. Finally write **`logs/3_write.io.md`** (INPUT: blueprint + refs.bib; DECISIONS: self-review findings + fixes; OUTPUT: the section files + word counts). Hand off to **ts-paper-refine**.
