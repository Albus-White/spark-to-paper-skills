---
name: ts-paper
description: >
  Generate a complete, publication-format journal/conference paper (LaTeX → compiled PDF) from
  whatever the user drops — a one-line idea, a proposal, or a proposal WITH real results. It ROUTES
  the input (idea→idea2story; proposal→proposal mode; results-present→data-aware mode), then runs
  plan→cite→write→refine→review→figure→latex using Claude's native abilities (reasoning, WebSearch, vision,
  file I/O, running Python) instead of a heavyweight per-call pipeline. Template-agnostic (ts_iieta +
  neurips bundled). Use for "write the paper", "proposal to paper", "turn this idea/report into a paper".
  Integrity is absolute: in proposal mode never fabricate numbers; in data-aware mode every number must
  trace to the user's real data.
---

# ts-paper — Traitement du Signal paper generator (orchestrator)

You produce a publication-format paper (in whatever **template** the user picks) from a dropped input
by first **routing it** (Stage 0) and then orchestrating seven focused sub-skills (the figure stage
delegates its editable-vector output to a helper sub-skill, **ts-paper-vector** — so the suite is 12
skills across a 7-stage chain, not 8 stages).

## Priority: QUALITY FIRST, cost second
The goal is a paper that reads like a real, well-written TS journal article with real, complete,
correctly-matched citations. **Never trade quality for cost.** Do every quality step — verify each
citation, self-review the draft, run the linters, right-size and polish, fix every compile error.
Cost is kept reasonable as a *by-product* of Claude doing more per turn (one holistic pass instead of
hundreds of micro-calls) — **not** by skipping reviews, shortening sections, or accepting a weaker
draft. If a quality step needs another pass, take it.

## The full suite (idea → figured paper) — where this orchestrator sits
This skill is the **story2paper == proposal2paper** spine. Two NEW upstream blocks are optional:
```
[corpus.jsonl] ─▶ ts-kg-build  (NEW, optional) ─▶ kg/         build a research-pattern KG (best-effort)
[raw idea]     ─▶ ts-idea2story (NEW)           ─▶ story_proposal.md + retrieved_papers.json
                                                  (uses kg/ if present; searches the web)
[story_proposal.md  OR  a user's own proposal] ─▶ ts-paper (THIS) ─▶ plan→cite→write→refine→review→figure→latex ─▶ main.pdf
                                                                       ( review = adversarial hardening, runs by default; user may opt out for a quick draft )
                                                                       ( figure ends every figure as an editable VECTOR PDF — matplotlib born-vector; image-model raster → ts-paper-vector reconstruction )
```
- If the user hands you a **raw idea**, run **ts-idea2story** first → it writes `story_proposal.md`
  (feed it here as the proposal) **and** `retrieved_papers.json` (the cite stage reuses it, so its
  search is much lighter — verify-the-seed + fill-the-gaps instead of a cold sweep).
- If the user hands you a **proposal**, start here directly (skip the upstream blocks).
- **ts-kg-build** only matters if you want KG-grounded recall in idea2story; it needs a user-supplied
  embedding endpoint and is honestly best-effort (TS already ships a built KG).

## Inputs
- A **proposal** (markdown/text): problem, gap, proposed method/solution, evaluation plan, claimed contributions.
- Optional **references** the user already has (BibTeX, DOIs, or a `references.json` with title/authors/year/venue/doi).
- An optional **template name** (default `ts_iieta`). The suite is **template-agnostic** — see below.
- Optional **`retrieved_papers.json`** (the citation seed produced by `ts-idea2story`, if the upstream idea→story stage ran) — the cite stage reuses it.
- **Integrity (mode-dependent, overrides everything).** In **proposal** mode there is no real data: **never invent results/metrics/percentages**; result tables stay blank (`--`); prose is forward-looking ("we evaluate… we expect…"). In **data-aware** mode (the router found real results) the opposite holds: report the real numbers in past tense, and **every number must trace to the user's data** (machine-checked by the number-audit) — still never invent or round a number that wasn't measured.

## Working directory & handoff (files on disk = the contract between stages)
Create one working dir (default `./ts_paper_run/`, or a user-named one) holding:
```
proposal.md                 # input
references.{json,bib}        # input (optional)
blueprint.json              # ← stage 1 (plan)
refs.bib                    # ← stage 2 (cite): complete, real BibTeX only
template.json               # ← the active template spec (copied in by the plan stage)
sections/<id>.tex           # ← stage 3 (write): LaTeX body per section (+ abstract.tex)
figures/<label>.pdf         # ← stage 6 (figure): EMBEDDED editable vector (matplotlib born-vector;
                            #   image-model raster → ts-paper-vector); .png (kept original) + source alongside
main.tex, main.pdf          # ← stage 7 (assemble): compiled paper
<template assets>           # the template's .sty/.cls + masthead assets (copied by assemble)
```

## Template-agnostic (NOT locked to one venue)
The suite writes to whatever **template** the user picks; paper *content quality* is invariant.
A template is a directory `templates/<name>/` (under this skill) holding `template.json` (the
parametric spec: ordered section list + per-section recipes, word bands, citation style + floor,
title/keyword rules, caption positions, heading case, masthead) + its LaTeX `.sty`/`.cls` +
`main.tex.tmpl`. **Two are bundled:** `ts_iieta` (Traitement du Signal, two-column numeric — the
default) and `neurips` (single-column, author-year — proves de-templatization). To use one, pass
`template=<name>`; the plan stage validates it (`template_lint.py`) and copies it into the workdir,
and **every downstream script reads `template.json` from the workdir** — no script hardcodes TS.
A user adds a new venue by dropping a `templates/<name>/` dir; no code changes. Word bands, shape
contracts (item/subsection/table counts), citation style/floor, and the preamble all come from the
spec. What stays **invariant across templates** = the content-quality + integrity logic (no
fabricated results, claims-map gating, no stubs, terminology consistency, Method-First order,
LaTeX safety, the figure integrity rule).

## Stage 0 — route the dropped input (a Claude reasoning step, not a sub-skill)
The user drops **one** input and usually does **not** declare a pipeline or a mode. Before anything else,
**read the input (and any sidecar files) and classify it yourself** — a plain Claude judgement over the
content, with **no fixed schema** to match. Pick the entry stage and **set `results_mode`** in the
workdir's `template.json` — the one switch the whole downstream suite reads. Set/re-assert it **after**
the plan stage copies the template in (the `cp` resets it to the bundled `proposal` default), or as the
plan stage's first action — so the router's choice survives the copy.

| class | what was dropped | route / entry | results_mode |
|---|---|---|---|
| (a) **bare/short IDEA** | a one-line message or a thin note, no method/eval structure | run **ts-idea2story** first → then plan | `proposal` |
| (b) **structured PROPOSAL** | problem / method / eval / contributions, **no measured results** | plan (proposal) | `proposal` |
| (c) **PROPOSAL/REPORT + REAL RESULTS** | measured numbers/tables in the text, **or** an attached data file (CSV/JSON/**any** form) | plan → **ts-paper-data** (DATA-AWARE) | `data_aware` |
| (d) **existing `story.json`** | an 8-field story from a prior idea2story run | plan (skip idea2story) | `proposal` (a story.json from idea2story is forward-looking — no results); if the user also dropped real results alongside it, that is class (c)/`data_aware` by step 1 |

**How to judge (shape-agnostic — there is NO fixed results schema):**
1. **Is there real measured data?** Any attached data file (CSV/JSON/a pasted table), or **measured
   result numbers in the prose** ("achieved 0.62 HOTA", "outperforms by 3.2 points", a filled results
   table — as opposed to hyperparameters, dataset sizes, or years) → **CLASS (c), `data_aware`.** When
   real numbers exist, **never** route them down the no-numbers proposal path; hand the data to **ts-paper-data**.
2. Else, is it a **fleshed-out proposal** (problem + method + evaluation plan, all present)? → CLASS (b), `proposal`.
3. Else it's **just an idea** (a sentence, a sketch) → CLASS (a): run **ts-idea2story** first to grow it
   into `story_proposal.md` (+ `retrieved_papers.json`), then continue here.
4. A primary input that is itself an 8-field **story.json** → CLASS (d).

Sidecars don't change the route: `references.{json,bib}` and `retrieved_papers.json` are just citation
seeds for the cite stage. Then write `logs/0_route.io.md` (the input shape, the signals you saw, the
chosen class + why). In `proposal` mode the suite runs exactly as the proposal path always has; in
`data_aware` mode the data-flow below adds steps.

## DATA-AWARE data-flow (only when results_mode == "data_aware") — driven by **ts-paper-data**
Claude reads the data in ANY form and judges it directly (no rigid schema, no loader, no marker indirection):
```
route -> results_mode = data_aware
  -> ts-paper-data Step 1: read the data, write results.facts.json (the real-number set = audit ground truth);
                   align any over-stated proposal claims to the real data inline (honest writing, no extra artifact)
                   (Step 1 only reads the user's raw data + writes results.facts.json; it does NOT touch
                    <workdir>/template.json — so the durable results_mode write happens in plan Step 0, after the cp.)
  -> ts-paper-plan (data-aware): FIRST re-assert results_mode=data_aware in <workdir>/template.json (the cp reset it
                   to the bundled proposal default), then plan the result tables with the real metric/method keys + results figures
  -> ts-paper-cite (unchanged)
  -> ts-paper-write (data-aware): each result-bearing section the active template defines (abstract +
                    experiments always; plus any analysis / results / limitations section present in
                    template.sections) uses past-tense + real numbers; Claude FILLS the result tables
                    itself with the real numbers (no markers, no auto-filler)
  -> draft_lint.py (data-aware: flags any prose decimal/percent NOT in results.facts.json)
  -> ts-paper-refine (keep real numbers + past tense; cross-section number consistency)
  -> ts-paper-review (adversarial hardening; data-aware = full claims-vs-evidence scrutiny)
  -> ts-paper-figure (ONE owner of all figures): results plots drawn by matplotlib from results.facts.json
                     (figures4papers house style); free-form schematics by the image model; every figure
                     then vectorized to an embedded editable PDF (matplotlib born-vector; raster -> ts-paper-vector) -> ts-paper-latex
```
## Pipeline (run in order; each stage is a sub-skill you invoke or follow directly)
1. **ts-paper-plan** — proposal → `blueprint.json` (title, ≤6 keywords, 3 contributions, notation, terminology, experiment design, per-section plans with word targets). ONE reasoning pass.
2. **ts-paper-cite** — build `refs.bib` of **only real, fully-specified** papers: use the user's references first; use **WebSearch/WebFetch** broadly to reach a well-read **~40–50 real refs** (floor 40, enforced); read each candidate's **abstract** to triage relevance AND decide its section; **never** emit a title-only stub or off-topic filler.
3. **ts-paper-write** — draft every section as **LaTeX body** in `sections/<id>.tex` (+ `abstract.tex`), citing the real bibkeys, following the per-section recipes and the no-fabrication rule. Write ALL sections in one pass.
4. **ts-paper-refine** — one holistic pass: right-size each section to the template's word bands (do NOT over-compress), enforce term consistency, run the **de-AI pass** (scrub AI tells — these drafts are AI-written) + a **logic self-check**, fix the linter's findings.
5. **ts-paper-review** *(adversarial hardening — distilled from PaperJury; runs by default)* — argue the OTHER side before finalizing: N isolated reviewers critique the whole draft (verbatim-quote anti-skim) → adversarial-verify each issue → loop-until-dry → triage. Valid issues are fixed **back through `ts-paper-refine`** (each bound to its `close_criterion`) and re-linted; author-required ones are surfaced. Cost-tiered (lean / cheapest / thorough). **Engine-agnostic**: runs by default via the best available execution tier (Workflow → subagents → in-context); the algorithm and output are identical across tiers, so it is **never skipped merely because the Workflow tool is absent**. May be skipped ONLY when the user explicitly requests a quick/no-review draft — record that choice in `logs/0_route.io.md`.
6. **ts-paper-figure** — fill every figure placeholder via ONE routing: **code-precise** figures (results plots, and math/geometry concept illustrations) are drawn by **matplotlib** (`ts-paper-data`'s `plot_results.py` + the figures4papers house style); **free-form** schematics (architecture/pipeline/qualitative scenes) are drawn by the **image model** (`gen_image.py`) through the Claude **vision-critique loop** (≥2 polish rounds). Results plots need real data (data-aware only); a proposal has none. No placeholder left blank. **Then ALWAYS vectorize** so every figure embeds as an editable vector PDF (matplotlib is born-vector via `finalize`; an image-model raster is reconstructed to a faithful editable SVG→PDF — **PRIMARY engine `ts-figure-optimize`** (real DrawAI runtime + Codex, highest fidelity) when configured, else **FALLBACK `ts-paper-vector`** (pure-Claude redraw, no external services); the original PNG is kept). The main free-form schematic is results-independent, so vectorize it ONCE at this proposal/first-draft figure stage — never defer to a post-experiment re-run; later experiment-phase figures are matplotlib born-vector. `ts-paper-vector/scripts/svg_tools.py` stays the shared vector **gate**. Vectorization must NEVER reduce quality. Optional — skip the whole stage only if there are no figures or the image model is unconfigured.
7. **ts-paper-latex** — run the bundled `assemble_paper.py` to build `main.tex`, apply the deterministic **template-driven** post-processes (caption position, merge `\cite` for numeric styles, canonical headings from `template.json`, format keywords), copy the template's `.sty`/`.cls` + assets, and compile with `latexmk`. Fix real compile errors in a bounded loop (≤3 tries; abort if errors increase).

## Per-step traceability (so every stage's input/output is visible)
The original product logged every model call's exact input+output to `llm_calls/*.json`. This suite runs
inline, so instead **each stage writes a `logs/<n>_<stage>.io.md` artifact** with three labeled blocks —
**INPUT** (files/text it consumed, with paths), **DECISIONS** (the judgment calls it made), **OUTPUT**
(artifact path + a short excerpt). After the final stage, write `logs/index.md` linking them all. This is
*instructed* capture, not byte-exact API logging, but it gives a faithful, inspectable per-step trail:
```
logs/0_route.io.md  1_plan.io.md  2_cite.io.md  3_write.io.md  4_refine.io.md  5_review.io.md  6_figure.io.md  7_latex.io.md  index.md
```
(`5_review.io.md` is present whenever review ran — record an opt-out in `0_route.io.md` otherwise; `6_figure.io.md` only when the figure stage runs. Conditional/optional logs are appended to `index.md` when they run: `data.io.md` only when `results_mode == data_aware`, plus `idea2story.io.md`, `kg_build.io.md`, `novelty.io.md` for the upstream blocks.)
Each stage also leaves its hard artifact (blueprint.json, refs.bib + claims_map.json, sections/*.tex, main.tex/pdf), which IS that stage's output.

## The quality stack (one coherent system, four complementary layers)
Quality is not one check; it is layered, and each layer does what it is best at — **Claude does the
judgement, code is the deterministic backstop**:
1. **Deterministic gates (code) — fail the build, don't proceed past a red gate.** `template_lint` +
   `blueprint_lint` (plan); `citations_lint` + `claims_map.json` (cite/write — real, complete, justified
   refs); `draft_lint` (write/refine — section shape, word bands, no-fabrication / data-aware number-audit,
   figure floor, and the **`ai_tell`** AI-phrase gate); the latexmk `error_count` gate (latex). Upstream,
   `story_lint` (idea2story) and `kg_lint` (kg-build). "It looked fine" is not acceptance; a green linter is.
   Run these gates through `scripts/run_gates.py <workdir> <stage|all>` — the single place that consumes the
   linters' exit codes and **stops on the first red gate** (nonzero exit = a hard stop, do not proceed past it).
2. **Self-review (Claude, in-pass) — refine.** Right-size, term/coherence consistency, the **de-AI pass**
   (these drafts are AI-written, so scrub the tells the gate can't catch with taste) and a **logic
   self-check** after each edit.
3. **Adversarial review (Claude, default) — `ts-paper-review`.** The one thing self-review can't do:
   argue the *other* side. Isolated reviewers + verbatim-quote anti-skim + adversarial-verify + loop-until-dry;
   valid issues fixed back through refine. Runs by default before finalizing via the best available
   execution tier (Workflow → subagents → in-context — identical algorithm/output, never skipped for a
   missing Workflow tool); skip only when the user explicitly requests a no-review quick draft.
4. **Vision critique (Claude, figures) — `ts-paper-figure` (+ `ts-paper-vector`).** Claude `Read`s each
   rendered image-model figure and critiques it (faithfulness/conciseness/readability/aesthetics) before
   accepting; code-precise figures bypass this via deterministic matplotlib + the house style. The same
   layer then **vectorizes** every figure to an editable PDF — matplotlib born-vector; an image-model
   raster reconstructed by **ts-paper-vector** via a second Read-render-compare loop (≥ raster, or a
   raster-embed fallback) — so editability is a quality gain, never a loss.

Layers 1, 2, and 3 run by default; layer 3 (adversarial review) may be skipped only on explicit user request for a quick draft; layer 4 runs when there are free-form figures.

## Efficiency (a by-product, never a goal that hurts quality)
The original product made ~145 LLM calls largely for orchestration overhead; you can match its
quality in far fewer turns because you hold the whole paper in context (coherence, anti-repetition,
and term-consistency come for free). Typical shape: plan ≈1 turn, cite ≈1 pass + a few searches,
write ≈1 pass, refine ≈1 pass, figure ≈1 critique loop per figure (if any), assemble ≈1 script run + 0–2
fix turns — **but always add passes when quality needs them** (more citation searches, a second review,
another refine). Don't pad with busywork; don't cut a quality step to save a turn.

## Definition of done
`main.pdf` exists and is non-trivial, the log shows **zero LaTeX errors**, `main.bbl` resolved all citations, every `\cite{}` maps to a complete `refs.bib` entry (no stubs/orphans), and no fabricated numbers appear in any sentence. **Every figure is embedded as an editable vector PDF** (`figures/<label>.pdf`, with the original `.png` kept) — and every vector-type figure (architecture/pipeline/concept/…) is an actual **redraw** (editable `<text>` + primitives), NOT a whole-canvas raster wrapped in an SVG; only an explicit `type=photo|qualitative` figure may be a whole-canvas raster. The adversarial **review stage ran** (`logs/5_review.io.md` exists, recording which execution tier ran) with every surviving `blocker`/`major` issue either closed (re-linted) or surfaced to the user as author-required. Review absence is acceptable **only** via an explicit user opt-out recorded in `logs/0_route.io.md` — **never** because no Workflow/subagent tool was available (in that case the in-context tier runs).

Before reporting done, run **`python scripts/run_gates.py <workdir> all`** (see the quality stack): it re-runs `citations_lint.py` and `draft_lint.py` against the final `sections/*.tex`, asserts **every figure has its embedded vector `.pdf` AND that every vector-type figure's `.svg` is a real redraw (not a whole-canvas raster)** (the `ts-paper-vector` check, manifest-driven), and asserts the latex verdict (`error_count == 0` / `main.bbl` resolved). A nonzero exit means **NOT done** — fix and re-run; do not emit the done report on a nonzero exit. Report: page count, section list, reference count (all complete), the review outcome (issues found / closed / author-required, plus the tier used), the figures (all editable vector PDFs), and the rough turn/token cost.
