---
name: ts-paper-data
description: >
  DATA-AWARE mode for the ts-paper suite. Activated by the orchestrator's router ONLY when the input
  ships REAL measured results (results_mode == "data_aware"); the proposal/no-numbers path is unchanged.
  Claude reads the user's data in ANY form (CSV / JSON / a pasted table / numbers in prose), judges it
  directly — there is NO fixed results schema — fills the result tables itself with real numbers in past
  tense, and writes the per-section text from the evidence. Two thin code backstops keep it honest:
  a schema-agnostic number-audit (draft_lint) and matplotlib results figures (plot_results.py). Use when
  a proposal/report comes with real experimental data.
---

# ts-paper-data — write the paper FROM real results (Claude judges the data)

The proposal path forbids numbers and writes forward-looking ("we expect…"). DATA-AWARE mode inverts
that: the experiments are done, so report **what was measured, in past tense, with the real numbers**.
Per the project philosophy, **Claude reads and judges the data itself — no rigid `results.json` schema,
no loader.** Code does only the two irreducible things: machine-check that no number is fabricated, and
plot precise results figures.

## When this runs
Only when the router set `template.results_mode == "data_aware"` (the input had real results — a
file, a pasted table, or measured numbers in the prose). Otherwise the suite stays in proposal mode and
this skill is not used.

## Step 1 — read the data and write `results.facts.json` (the one artifact)
Read whatever the user gave — a CSV, a JSON, a Markdown/LaTeX table, or numbers written in the proposal
prose. Understand it: which methods/variants, which datasets, which metrics, ablation deltas, runtime
costs, and any qualitative findings. Then write **`results.facts.json`** — simply the set of REAL numbers
you will use, in any convenient shape (a flat list, or `{"label": value}`, or nested). This is the
ground truth the number-audit checks against. Example:
```json
{"main": {"Ours": {"HOTA": 0.621, "IDF1": 0.704}, "ByteTrack": {"HOTA": 0.476}},
 "ablation": {"w/o formation prior": {"IDsw": 0.18}}, "runtime": {"fps": 27.3, "latency_ms": 36},
 "notes": ["FPR is 0.03 — non-zero, a real weakness"]}
```
Rules: every number must come from the user's data — **never invent or round-trip a number that wasn't
given.** A metric that was measured-but-unavailable is the sentinel `"TBD"`; a cell never run is `null`.

## Step 2 — fill the result tables yourself (real numbers, in order)
Write the experiment result tables directly in `sections/experiments.tex` (same LaTeX table pattern as
proposal mode, with `\label{tab:main_results}` / `secondary_results` / `ablation_results` in the spec
order) — but with the **real measured numbers** in the cells instead of `--`. `null` → `--`; `"TBD"` →
`TBD`. Keep cells consistent with `results.facts.json` (the audit cross-checks the prose, and you should
keep table and prose numbers identical). Do not write a metric the data doesn't contain.

## Step 3 — write the data-aware sections (past tense, real numbers)
For each result-bearing section the active template defines (abstract + experiments always; plus any
analysis / results / limitations section present in `template.sections`), swap the proposal-mode rules
for evidence-grounded ones:
- **abstract** — Part-4 (results) states 2–3 most impactful real numbers in definitive past tense
  ("achieves 0.62 HOTA, outperforming the strongest baseline by 0.15"); NO forward-looking/vague outcome.
- **experiments** — past tense throughout (achieved/outperformed); reference specific numbers; real
  ablation deltas between variants; NO "we expect", NO `--` in prose, NO vague outcomes.
- **analysis** — evidence-grounded: every quantitative claim cites a specific number; each ablation
  variant analysed with its actual measured delta; failure modes grounded in real data patterns
  (non-zero error, edge cases) — do NOT invent failure modes absent from the data. **Do not re-state the
  Experiments numbers**; cite the table, then explain the MECHANISM / WHY (Analysis's value-add is causal).
- **conclusion** — summarise contributions WITH the key real results, definitive past tense; no
  forward-looking language about results already obtained.
- **limitations** (only if the active template defines a limitations section) — quantify limitations with
  the real data (a non-zero error rate, a perf gap, a runtime cost from the data); honestly surface any
  data-revealed weakness with its actual value; never downplay a shown weakness, never invent one.
`method` / `related_work` / `introduction` are written normally (no results numbers).
**TBD rule:** a `TBD`/missing metric is unavailable evidence — stay silent about it; never guess it.

## Step 4 — the results-plot TOOLKIT (the figure stage renders; you provide data + toolkit)
The single owner of drawing figures is **`ts-paper-figure`** (its unified routing: code-precise →
matplotlib, free-form → image model). In data-aware mode it draws the **results plots** from CODE
(numerically exact, never the image model) using THIS skill's toolkit and the numbers in
`results.facts.json` / your filled tables. Your job in the data stage is to make sure `results.facts.json`
and the filled tables exist (Steps 1–2); the figure stage runs the plotter.

The toolkit it uses (kept here):
- `scripts/plot_results.py --script figures/<label>.plot.py --out figures/<label>.png` — runs a
  self-contained matplotlib script and saves PNG + a **vector PDF** (born-vector, even if the script
  self-saves). The figure stage embeds that `.pdf` via an extension-less `\includegraphics{figures/<label>}`,
  so matplotlib figures are **editable vectors with no extra step** (they skip the ts-paper-vector
  reconstruction loop, which is only for image-model rasters).
- `scripts/plot_style.py` — the figures4papers publication house style; `plot_results.py` applies the
  rcParams and **injects `PALETTE`, `SEMANTIC`, `style_axes`, `finalize`** into the plot script's namespace.
- **`references/plot-style.md`** — colour BY MEANING (`SEMANTIC["ours"]` blue / `["positive"]` green /
  `["contrast"]` red / `["baseline"]` grey) + per-chart encoding rules (bars: black edges, value labels,
  alpha-ablation, hatch for grayscale, tight y-limits; trends: 2–4 curves + `fill_between`; heatmap/radar;
  wide canvas + dedicated legend axis) + `finalize(fig, OUT)` (dpi 300, +PDF; 600 for dense bars).
A `null`/`TBD` value is a gap in the plot, never a fabricated point. (Math/geometry CONCEPT illustrations
use the same toolkit via the figure stage's routing, even in proposal mode — synthetic/illustrative
values, no metric claim.)

## Step 5 — the number-audit gate (machine-checked honesty)
Run the write-stage linter; in data-aware mode it flips from "ban all numbers" to "flag untraceable ones":
```
python3 ../ts-paper-write/scripts/draft_lint.py <workdir>
```
It flags `suspicious_number` for any decimal/percent in prose **not** present in `results.facts.json`
(bare integers are treated as design constants and not audited), and `missing_results_facts` if you
forgot to write the facts file. Drive it to zero by correcting the prose to the real numbers — never by
adding a fake number to the facts file; it must be `ok:true` before proceeding. `citations_lint` and the
rest of the suite are unchanged.

## Fusion (do it inline, not as a separate heavyweight stage)
If the input was an idea/proposal whose *claimed* outcomes don't match the real data, silently align the
claims to the data as you plan and write (a proposal that predicted "large gains" but the data shows a
small gain must say the small gain). This is just honest writing against the evidence — no separate
fusion artifact needed.

## Trace
Write `logs/data.io.md` — INPUT (the data form received + what you extracted), DECISIONS (table values,
per-section number choices, any TBD/weakness surfaced, the plot scripts), OUTPUT (results.facts.json
summary, draft_lint result). This is a conditional log (only when `results_mode == data_aware`); it is
linked from `logs/index.md` when this stage runs.
