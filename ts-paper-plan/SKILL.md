---
name: ts-paper-plan
description: >
  Stage 1 of the ts-paper suite. Turn a research proposal into a single structured blueprint.json
  (title, ≤6 keywords, exactly 3 contributions, notation table, terminology glossary, experiment
  design, and per-section plans with word targets) for a Traitement du Signal proposal paper.
  Use when planning the structure of a TS paper before writing. ONE reasoning pass — no real results.
---

# ts-paper-plan — proposal → blueprint.json

Produce the **entire blueprint in ONE reasoning pass** (the original split this into 3 calls; you
don't need to). Write it to `blueprint.json` in the working dir. This is a **proposal** — design the
experiments but commit to **placeholder results only**; never plan a fabricated number.

## Step 0 — load the template (the suite is template-agnostic)
Before planning, pick the **template** (default `ts_iieta`; or the user's `template=<name>`). Templates
live in `../ts-paper/templates/<name>/`. Validate and copy it into the workdir:
```
python scripts/template_lint.py ../ts-paper/templates/<name>/      # must be ok:true
cp ../ts-paper/templates/<name>/*  <workdir>/                       # template.json + .sty/.cls + main.tex.tmpl + assets
```
**Set `results_mode` now if the router classified this run as data_aware.** The `cp` just overwrote
`<workdir>/template.json` with the bundled template, which ships `"results_mode": "proposal"` — so any
mode the router set earlier is gone. If the router classified this as data_aware (class c, or class d
with real results), edit `<workdir>/template.json` to set `"results_mode": "data_aware"` (the cp reset
it to the bundled `proposal` default). Leave it as `proposal` otherwise. `template.json` is the single
source of truth every downstream reader keys on; record the chosen mode in `logs/1_plan.io.md`.

Then **read `<workdir>/template.json`** and let it drive the blueprint: the **section list + ids +
titles**, the **per-section word bands** (`sections[].words`), the **contributions count**
(`contributions.count` — may be 0 = not enforced, e.g. NeurIPS), the **result-table set**
(`experiments.recipe.result_tables`), the **title/keyword limits**, and the **citation types/floor**
all come from the spec. The TS values below are the *default template's* values; for another template,
use that template's sections/recipes instead. Everything downstream (`draft_lint`, `assemble`,
`citations_lint`) reads the same `template.json`.

## blueprint.json schema
```json
{
  "paper_title": "8–14 word technical title, no filler, ≤1 colon",
  "keywords": "4–6 lowercase comma-separated index terms (proper nouns/acronyms keep case)",
  "contributions": ["C1: ...", "C2: ...", "C3: ..."],
  "terminology": {"method_name":"X","component_1":"...","dataset_1":"...","baseline_1":"..."},
  "notation": {"x_s":"input skeleton sequence","T":"number of frames"},
  "experiment_design": {
    "datasets":[{"name":"","description":""}],
    "baselines":[{"name":"","description":""}],
    "metrics":[{"name":"","description":""}],
    "main_table":{"columns":["Method","..."],"rows":["Baseline A","...","<Method> (Ours)"]},
    "ablation_table":{"columns":["Variant","..."],"rows":["Full","w/o <component>"]}
  },
  "section_order": ["introduction","related_work","method","experiments","analysis","conclusion"],
  "sections": {
    "<id>": {"title":"","target_words":[min,max],"key_arguments":[".."],
             "citation_types":["CORE","CONTEXT"],
             "paragraph_outline":[{"para":1,"topic":"","key_points":[".."],"citations":"2-3","sentences":4}],
             "figures":[{"id":"system_overview","type":"architecture","caption":"","label":"fig:.."}],
             "tables":[]}
  }
}
```

## Canonical sections, default word targets (min,max), dependencies — `ts_iieta` default
(For another template, use **its** `sections`/`words` from `template.json` instead of this table.)
| id | title | target_words | depends_on |
|---|---|---|---|
| method | Methodology | (2000,3000) | — |
| related_work | Related Works (3 themes) | (800,1200) | method |
| introduction | Introduction | (800,1200) | method, related_work |
| experiments | Experimental Results | (1000,1500) | method |
| analysis | Discussion and Analysis | (900,1400) | experiments |
| conclusion | Conclusion | (200,280) | intro, method, experiments |
| abstract | (front matter, not numbered) | (150,220) | all |

(These ts_iieta bands target a substantial **~10–12 page** two-column journal article. Copy them into
`blueprint.json` `target_words` as-is unless the template differs; the band is reached by real
substance, never padding.)

(Optional `limitations` (200,400) only if the user wants it; TS samples usually omit it.) You may shift a section's `target_words` to match how much source content it has, but keep `[min,max]` pairs.

## Rules
- **Title**: technical, specific, 8–14 words; avoid filler ("comprehensive/framework/study/toward/universal"); key terms should overlap the method/problem terms.
- **Keywords**: 4–6, lowercase, comma-separated; specific topical terms (task, method, signal/data type, key technique); no connectors ("and/of/based").
- **Contributions**: exactly `template.contributions.count` (TS=3; `C1:/C2:/C3:`), each a concrete technical statement from the proposal's innovation claims; the last may describe the *planned* evaluation (never a result number). If the count is 0 (e.g. NeurIPS), contributions are optional/free-form.
- **Terminology glossary**: fix the exact canonical names (method, components, datasets, baselines) that EVERY section must reuse — prevents drift.
- **Tables live ONLY in experiments**, exactly the set in `template.experiments.recipe.result_tables` (TS: `main_results`, `secondary_results`, `ablation_results`; NeurIPS: `main_results`, `ablation_results`). Every other section has `"tables":[]`. **Quantitative results belong in tables, NEVER in figures.**
- **Figures: plan at least `template.figures.min` (TS = 5)**, distributed across **method / experiments / analysis** (the architect's rule). These are **schematic / conceptual / qualitative** diagrams that depict the *method or an idea*, each standing on its own merit (not padding): e.g. (1) the **architecture/pipeline overview** (method); (2) a **component-detail** diagram (e.g. how the trajectory descriptors are computed) (method); (3) a **concept** diagram (e.g. formation-graph construction + its Laplacian-spectrum signal) (method/analysis); (4) a **qualitative scenario** (e.g. a crossing event where appearance fails but the formation prior disambiguates — illustrative, NO numbers) (experiments/analysis); (5) a **protocol/diagnostic concept** (e.g. how the stratification by occlusion/density is defined) (experiments). Each gets `{id, type, caption, label}` with `type` in the drawable set `{architecture, pipeline, framework, concept, schematic, overview, qualitative, diagram, flow}`.
  - **Results figures depend on `template.results_mode`:** in **`proposal`** mode (no real data) **do NOT plan any results figure** — there is nothing to plot; numbers live only in the (blank `--`) tables. Do not invent a stand-in figure for the missing results. In **`data_aware`** mode (the proposal ships real, validated results) **DO plan results figures** (metric curves/bars/comparison plots) drawn from that data, in addition to the schematic ones.
- **citation_types**: only `CORE, CONTEXT, BASELINE, METRIC, DEFINITION`; don't request more CORE cites than real papers will exist. Abstract & conclusion carry no citations.
- **paragraph_outline**: 3–6 paragraphs/section (2–4 for abstract/conclusion), each specific to THIS paper, never a generic template.
- **Writing order** is Method-First (`method → related_work → introduction → experiments → analysis → conclusion → abstract`); `section_order` above is the *reading* order for the PDF.
- **Honesty**: results are blank placeholders; contributions/abstract use proposal language ("we evaluate", "expected to improve"), never achieved numbers.

## DATA-AWARE branch (only when `template.results_mode == "data_aware"`)
When the router set `results_mode == "data_aware"` (real results present — see **ts-paper-data**, which
read the data), plan against the **real data**, not a generic shape:
- **Plan the result tables with the REAL keys** Claude read from the data: each table's rows = the actual
  method/variant names, columns = the actual metric names (not invented placeholders). Plan the table
  *ids* (`main_results`, `secondary_results`, `ablation_results`) and honor the `tables.min` floor; the
  write stage fills the cells itself with the real numbers (no markers, no auto-filler).
- **Force `experiment_complexity="full"`** (real data warrants the full experimental treatment).
- **Enable the `analysis` section** and **plan results figures** (metric bar/curve/comparison plots) drawn
  from the data, in addition to the schematic figures — these are rendered later via matplotlib
  (`ts-paper-data` / `plot_results.py`).
- Everything else (title, keywords, contributions, notation, terminology, per-section outlines) is
  planned exactly as in proposal mode. `blueprint_lint` accepts the exact-key data-aware table plan and
  only enforces `tables.min` (it does not force the proposal table count).

## Validate (enforced) + log
Run `python scripts/blueprint_lint.py <workdir> --fix`, then re-run without `--fix` until `ok=true`. It is now **template-driven** (reads `template.json` from the workdir): `citation_types` must be a subset of the template's `citations.types` (remaps aliases — `DATASET→METRIC`, `METHOD→CORE`, …), all of the template's sections present (self-heal with the template's titles/word-targets), every `target_words` a 2-tuple, the template's result-table count in experiments (mode-dependent: in **proposal** mode the experiments section plans either **0 or exactly** `template.experiments.recipe.result_tables` result tables — 0 is allowed because a proposal has no measured results to tabulate; in **data_aware** mode it must plan at least `tables.min` filled tables), title within the template's `title` limits, contributions == the template's `contributions.count` (skipped when 0). Do not proceed on a failing blueprint.

Then write **`logs/1_plan.io.md`** — three blocks: INPUT (the proposal text/path), DECISIONS (why this title / these word targets / these keywords), OUTPUT (blueprint.json one-line summary). Hand off to **ts-paper-cite**.
