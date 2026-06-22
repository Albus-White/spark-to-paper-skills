<h1 align="center">✨ spark-to-paper-skills</h1>

<h3 align="center"><b><i>Drop a spark — an idea, a proposal, or a proposal with real results — get a publication-format paper.</i></b></h3>

<p align="center">
  <b>A <a href="https://docs.claude.com/en/docs/claude-code">Claude Code</a> skill suite that turns whatever you drop in into a compiled, journal-ready LaTeX paper — figures vectorized, citations real, numbers never faked.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-Skill_Suite-d97757?logo=anthropic&logoColor=white" alt="Claude Code Skill Suite">
  <img src="https://img.shields.io/badge/Skills-13_active-6f42c1" alt="13 skills">
  <img src="https://img.shields.io/badge/Pipeline-7_stages_+_experiments-2ea44f" alt="7 stages">
  <img src="https://img.shields.io/badge/Templates-Template--agnostic-0969da" alt="Template-agnostic">
  <img src="https://img.shields.io/badge/Integrity-Machine--checked-b31b1b" alt="Machine-checked integrity">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
</p>

<p align="center">
  <a href="#-quick-start">🚀 Quick Start</a> ·
  <a href="#-the-pipeline">🔬 Pipeline</a> ·
  <a href="#-the-skills">🧩 Skills</a> ·
  <a href="#-the-figure-engine-drawai">🖼️ Figure Engine</a> ·
  <a href="#-the-quality-stack">🛡️ Quality Stack</a> ·
  <a href="#-integrity">🔒 Integrity</a>
</p>

---

## 💡 What Is This?

**You drop a spark. Claude writes the paper. Small scripts do only the irreducible parts.**

`spark-to-paper-skills` (a.k.a. **Auto-Research-PaperGenSkill**) is a suite of **13 composable Claude Code skills** that turn any of three inputs —

- 🧠 a **one-line research idea**,
- 📋 a **full proposal** (problem / method / evaluation / contributions), or
- 📊 a **proposal *with real experimental results*** (CSV / JSON / a pasted table / numbers in prose) —

into a **publication-format paper**: drafted section-by-section as LaTeX, cited with **real, verified** references, illustrated with **editable vector figures**, and compiled to a finished `main.pdf`.

The design philosophy is simple and deliberate:

> **The model does the thinking; code does only what must be deterministic.**
> Claude handles reasoning, writing, literature search, vision-based figure critique, and adversarial self-review. Tiny Python scripts do only the irreducible parts — deterministic linters, LaTeX assembly, image generation, embeddings/clustering, matplotlib plotting, and figure vectorization.

The result reads like a real journal article — not template-filler — and **every quality and integrity rule is machine-checked**: a red linter *fails the build*.

---

## 📦 What You Get

Run the suite inside a working dir (default `./ts_paper_run/`) and you end up with a self-contained, Overleaf-ready paper:

| | Artifact | What it is |
|---|---|---|
| 📐 | `main.tex` · `main.pdf` | Compiled paper in the chosen venue template |
| 📝 | `sections/*.tex` + `abstract.tex` | LaTeX body, one file per section |
| 🗂️ | `blueprint.json` | Structured plan: title, keywords, 3 contributions, notation, per-section word targets |
| 📚 | `refs.bib` + `claims_map.json` | **Real, fully-specified** BibTeX (≥40 refs) — every `\cite{}` justified |
| 🖼️ | `figures/<label>.pdf` (+ `.png` + source) | **Editable vector** figures — matplotlib born-vector, or rasters reconstructed by the DrawAI engine |
| 🔎 | `logs/<n>_<stage>.io.md` + `index.md` | Per-stage INPUT / DECISIONS / OUTPUT trace — fully inspectable |
| ✅ | green `run_gates.py` | Every deterministic gate passed (citations, draft, vectors, LaTeX) |

---

## 🚀 Quick Start

### 1 · Install the skills

Copy the skill folders into a Claude Code skills directory:

```bash
# Per-project
cp -r */ <your-project>/.claude/skills/

# …or globally
cp -r */ ~/.claude/skills/
```

### 2 · (Optional) Configure secrets

Copy `.env.example` → `.env` (gitignored, auto-loaded by the scripts) and fill in only what you use:

```bash
cp .env.example .env
```

| Variable | Used by | When you need it |
|---|---|---|
| `TS_FIG_API_KEY` / `TS_FIG_BASE_URL` / `TS_FIG_MODEL` | `ts-paper-figure` | To render free-form schematics with an image model |
| `OPENAI_API_KEY` / `VISION_MODEL` | `ts-figure-optimize` | GPT vision text-correction + per-region defect diff (falls back to `~/.codex/auth.json`) |
| `TS_EMBED_*` | `ts-kg-build`, `ts-idea2story` | KG-grounded recall (optional — degrades gracefully without it) |
| `HF_TOKEN` | `setup_drawai.py` | **One-time** download of the gated SAM3 model weights |
| `OVERLEAF_GIT_URL` / `OVERLEAF_TOKEN` | `ts-paper-experiment` | Only if you turn Overleaf sync on (off by default) |

### 3 · Just ask Claude

Inside Claude Code:

```
Run ts-paper on this proposal.   ⟵ then paste / attach your idea, proposal, or proposal+data
```

The orchestrator **auto-routes** your input, picks the right mode, runs the full chain, and reports page count, section list, reference count, the review outcome, and the figures — all editable vector PDFs.

> 💡 **Template choice:** pass `template=neurips` (or any venue you've added) — default is `ts_iieta`.

---

## 🔬 The Pipeline

One orchestrator (**`ts-paper`**) routes the input, then drives a focused **7-stage chain** (plus an auto-run experiments stage):

```
                         ┌──────────────────── optional upstream ────────────────────┐
 [corpus.jsonl] ─▶ ts-kg-build ─▶ kg/         (research-pattern knowledge graph, best-effort)
 [raw idea]     ─▶ ts-idea2story ─▶ story_proposal.md + retrieved_papers.json
                         └────────────────────────────────────────────────────────────┘
                                                │
 [proposal  OR  proposal + real results]  ─────▶  ts-paper  (Stage 0: ROUTE + set results_mode)
                                                │
   1. ts-paper-plan ──▶ blueprint.json          (title · keywords · 3 contributions · notation · per-section plan)
   2. ts-paper-cite ──▶ refs.bib                (≥40 REAL refs via WebSearch + Crossref; read each abstract)
   3. ts-paper-write ─▶ sections/*.tex          (all sections in one holistic pass; no fabricated numbers)
   4. ts-paper-refine ▶ right-size + de-AI + logic self-check
   5. ts-paper-review ▶ adversarial peer-review hardening (runs by default)
   6. ts-paper-figure ▶ matplotlib (precise) / image-model (free-form) + vision critique
                       └▶ ts-figure-optimize: raster ──▶ editable vector SVG/PDF (+PPTX)
   7. ts-paper-latex ─▶ assemble + compile ──▶ main.pdf
                                                │
   8. ts-paper-experiment  (AUTO-RUN) ─▶ run FEASIBLE experiments, fill result tables, recompile
```

### Stage 0 — Input routing (a Claude reasoning step, no fixed schema)

The user drops **one** thing and usually doesn't declare a mode. Claude reads it and classifies:

| Class | What was dropped | Route | `results_mode` |
|---|---|---|---|
| **(a) bare idea** | one line, no method/eval structure | `ts-idea2story` → then plan | `proposal` |
| **(b) proposal** | problem + method + eval, **no measured results** | plan (proposal) | `proposal` |
| **(c) proposal + REAL results** | measured numbers in prose, or any attached data file | plan → **`ts-paper-data`** | `data_aware` |
| **(d) existing `story.json`** | an 8-field story from a prior run | plan (skip idea2story) | `proposal` |

`results_mode` is the **single switch** the whole downstream suite reads.

### Two modes, opposite integrity rules

| | **Proposal mode** | **Data-aware mode** |
|---|---|---|
| Numbers | ⛔ never invent — result cells stay blank (`--`) | ✅ report the real numbers, in past tense |
| Tense | forward-looking ("we evaluate… we expect…") | retrospective ("we measured…") |
| Guarantee | no metric ever fabricated | **every number must trace to your data** (machine-audited) |

---

## 🧩 The Skills

14 skill folders ship; **13 are active** (`ts-paper-vector` is retired/disabled, superseded by `ts-figure-optimize`).

| Skill | Stage | Role |
|---|---|---|
| **`ts-paper`** | orchestrator | Routes input (idea / proposal / proposal+data) and drives the chain |
| `ts-idea2story` | upstream | Raw idea → structured 8-field research story + citation seed |
| `ts-kg-build` | upstream (opt.) | Corpus → research-pattern knowledge graph for recall |
| `ts-paper-plan` | 1 | Proposal → `blueprint.json` (one reasoning pass) |
| `ts-paper-cite` | 2 | Build a **real, complete** bibliography (WebSearch + Crossref, floor 40) |
| `ts-paper-write` | 3 | Draft all sections as LaTeX in one holistic pass |
| `ts-paper-refine` | 4 | Right-size to word bands + de-AI scrub + logic self-check |
| `ts-paper-review` | 5 | Adversarial peer-review hardening (default on, engine-agnostic) |
| `ts-paper-figure` | 6 | Figure routing: matplotlib (precise) / image model (free-form) + vision critique |
| `ts-paper-data` | 6 (data) | Data-aware mode: real results → filled tables + plots |
| `ts-figure-optimize` | 6 (vector) | **Sole figure vectorizer** — raster → editable SVG/PDF/PPTX via the full DrawAI engine |
| `ts-paper-latex` | 7 | Assemble + compile the final PDF (template-driven) |
| `ts-paper-experiment` | 8 | Diagnose logic, **run feasible experiments**, fill tables, recompile |
| ~~`ts-paper-vector`~~ | — | ⛔ **DISABLED** (legacy Claude-only vectorizer) |

---

## 🖼️ The Figure Engine (DrawAI)

The headline component. AI image models produce **rasters** — but a paper needs **editable vector** figures. `ts-figure-optimize` is the suite's heavy, maximum-fidelity vectorizer, and it **vendors the full DrawAI engine** (~5 MB source, in `engine/`).

It does **not** just embed a bitmap into a slide. It *decomposes and reconstructs* the figure:

```
raster figure (PNG/JPG)
   │
   ├─ SAM3            → segment the layout into regions
   ├─ PaddleOCR       → read every text run
   ├─ Box-IR          → build a structured layout IR
   ├─ Codex/gpt-5.5   → author editable SVG (text as <text>, shapes as primitives)
   └─ DrawingML       → export native, editable PowerPoint
   │
   └─▶ measured, multi-round visual-similarity refinement loop
        (SSIM + per-region vision diff + raster-background + waveform gates)
   │
   └─▶ editable SVG master · vector PDF · native PPTX   (original raster always kept)
```

### Two export paths

| Path | Command | Fidelity | Editability | Cost |
|---|---|---|---|---|
| **HYBRID** *(default)* | `run_hybrid.py` | **~0.91 SSIM** | text editable, graphics pixel-exact raster | cheap (no Codex redraw) |
| **pure-A** *(legacy)* | `run_reconstruction.py` | ~0.67–0.80 | **everything** editable vector | Codex cost |

> **Honest ceiling:** re-typed text can't beat the original's font/AA/sub-pixel rendering, so ~0.90 SSIM is the expected, correct outcome for a faithful editable redraw — not a failure. The suite **never fakes a similarity score** and always preserves the original.

### Runtime (provisioned once per machine)

Code lives in git; the **~4 GB model weights** (SAM3 / PaddleOCR / RMBG) + a runtime venv are downloaded on demand under the skill:

```bash
python ts-figure-optimize/scripts/setup_drawai.py --device cpu   # provision (~4 GB)
python ts-figure-optimize/scripts/setup_drawai.py --check-only   # doctor: OK?
```

`run_hybrid.py` **auto-deploys** the runtime if it's missing, so you usually never call setup by hand.

---

## 🛡️ The Quality Stack

Quality is not one check — it's **four complementary layers**, each doing what it's best at. Claude does the judgement; code is the deterministic backstop.

| Layer | Owner | What it catches |
|---|---|---|
| **1 · Deterministic gates** | code | section shape, word bands, no-fabrication / number-audit, citation completeness, AI-phrase tells, vector-PDF presence, `error_count == 0` — **a red gate is a hard stop** |
| **2 · Self-review** | Claude (in-pass) | right-sizing, term/coherence consistency, **de-AI scrub**, logic self-check |
| **3 · Adversarial review** | Claude (default) | the one thing self-review can't do — *argue the other side*: N isolated reviewers + verbatim-quote anti-skim + adversarial-verify + loop-until-dry |
| **4 · Vision critique** | Claude (figures) | `Read`s each rendered figure and critiques faithfulness/readability/aesthetics before accepting, then vectorizes |

All gates flow through one entry point — and you must not ship on a red one:

```bash
python ts-paper/scripts/run_gates.py <workdir> all     # nonzero exit = NOT done
```

The gate scripts: `template_lint` · `blueprint_lint` · `citations_lint` · `draft_lint` · `check_vector_pdf` · the latexmk `error_count` gate (+ `story_lint` / `kg_lint` upstream).

> **Adversarial review is engine-agnostic.** It runs via the best available tier — Workflow tool → parallel subagents → fully in-context — with an *identical algorithm and output*. It is **never skipped merely because a Workflow tool is absent**; skip it only on an explicit user request for a quick draft (recorded in `logs/0_route.io.md`).

---

## 🔒 Integrity

Integrity is **absolute and machine-checked** — it overrides everything else.

- **Proposal mode never fabricates numbers.** No invented metrics, percentages, or results. Tables stay blank; prose is forward-looking. `draft_lint` fails the build on a stray decimal.
- **Data-aware mode traces every number.** Each decimal/percent in the prose must appear in `results.facts.json` (the real-number ground truth) — the number-audit flags any that don't.
- **Citations are real and complete.** Every entry in `refs.bib` is a paper that actually exists and was verified; no title-only stubs, no off-topic filler, no orphan `\cite{}`. `citations_lint` enforces it.
- **Every figure is a true editable vector** — and every vector-type figure is an actual *redraw* (editable `<text>` + primitives), not a whole-canvas raster wrapped in SVG. `check_vector_pdf.py` is the gate.

> If a quality step needs another pass, the suite takes it. **Quality first, cost second** — cost stays reasonable as a *by-product* of Claude doing more per turn, never by skipping a review.

---

## 📐 Template-Agnostic

The suite writes to **whatever venue template you pick**; content quality is invariant. A template is a directory under `ts-paper/templates/<name>/` holding:

- `template.json` — the parametric spec: ordered sections + per-section recipes, word bands, citation style + floor, title/keyword rules, caption positions, heading case, masthead
- the LaTeX `.sty` / `.cls` + `main.tex.tmpl` + masthead assets

**Two bundled:**

| Template | Venue | Style |
|---|---|---|
| `ts_iieta` *(default)* | Traitement du Signal | two-column, numeric citations |
| `neurips` | NeurIPS | single-column, author-year |

**Add a venue by dropping a `templates/<name>/` dir — no code changes.** Every downstream script reads `template.json` from the workdir; nothing hardcodes a venue.

---

## 🧪 Stage 8 — Experiments + Repair (auto-run)

After Stages 0–7 produce a complete first-draft paper, **Stage 8 runs automatically** via the in-repo `ts-paper-experiment` skill. It turns a no-results draft into a results-bearing manuscript:

```bash
# 1) stage the run into a clean experiment workspace
python ts-paper/scripts/handoff_to_experiments.py --workdir <ts_paper_run>   # → experiments/
# 2) ts-paper-experiment (Embedded Stage-8 mode) ingests input/draft/, diagnoses logic,
#    runs only FEASIBLE experiments (real data/code only), fills tables, recompiles
# 3) repaired sections/main + filled tables flow back into <ts_paper_run>; recompile
```

- ✅ Runs **only feasible experiments** on real data/code — and **never invents results**.
- 📄 If no real data/code is present, it writes a **requirements report** and leaves tables in proposal form.
- ☁️ **Overleaf is OFF by default** (no account needed); enable via `paper_config.yaml` + `.env`.

Stage 8 ships a rich rule library (`ts-paper-experiment/resources/`) — claim-evidence rules, anti-patterns, reproducible-artifact packaging, a final-submission checklist, and a self-evolving `memory/` of validated lessons.

---

## 📁 Working Directory — the Contract Between Stages

Files on disk *are* the handoff between stages:

```
ts_paper_run/
├── proposal.md                 # input
├── references.{json,bib}       # input (optional)
├── blueprint.json              # ← plan
├── refs.bib                    # ← cite (real BibTeX only)
├── template.json               # ← active template spec (carries results_mode)
├── sections/<id>.tex           # ← write (+ abstract.tex)
├── figures/<label>.pdf|png|svg # ← figure (editable vector + kept raster)
├── main.tex · main.pdf         # ← assemble (compiled)
└── logs/<n>_<stage>.io.md      # ← per-stage trace + index.md
```

---

## ⚙️ Requirements

- **Claude Code** (the suite is a set of skills)
- **Python 3.10+** with the figure-script deps: `pip install -r ts-figure-optimize/requirements.txt` (`numpy`, `Pillow`, `python-pptx`, `cairosvg` → needs system Cairo, `openai`)
- **LaTeX** (`latexmk` + a TeX distribution) for the compile stage
- **LibreOffice** (`soffice`) — optional, enables the PPTX render gate in `ts-figure-optimize`
- **~4 GB disk + HF token** — only when first provisioning the DrawAI runtime
- An **image-model endpoint** — only if you want free-form schematics
- **Codex / OpenAI auth** (`~/.codex/auth.json` or `OPENAI_API_KEY`) — for the DrawAI Codex vector path and GPT vision steps

---

## 🙋 FAQ

<details>
<summary><b>Will it invent results to make the paper look complete?</b></summary>

No. In proposal mode it physically cannot — `draft_lint` fails the build on any prose number not backed by data. In data-aware mode every number is audited against your real `results.facts.json`.
</details>

<details>
<summary><b>Do I need GPUs or the heavy DrawAI runtime?</b></summary>

Only if you have free-form raster figures to vectorize. The DrawAI runtime runs on CPU (`--device cpu`). matplotlib figures are born-vector and skip the engine entirely. A paper with no figures skips Stage 6 altogether.
</details>

<details>
<summary><b>Can I use a venue that isn't bundled?</b></summary>

Yes — drop a `templates/<name>/` directory with a `template.json` + the LaTeX assets. No code changes; every script reads the spec.
</details>

<details>
<summary><b>What if I just want a quick draft without the adversarial review?</b></summary>

Ask explicitly for a quick / no-review draft — the choice is recorded in `logs/0_route.io.md`. By default, review always runs (via whatever execution tier is available).
</details>

<details>
<summary><b>Does it really produce editable figures, or just embed an image?</b></summary>

Real editable vectors. `check_vector_pdf.py` gates that every vector-type figure is an actual redraw (editable `<text>` + primitives), not a whole-canvas raster wrapped in SVG. Only an explicit `type=photo|qualitative` figure may stay raster.
</details>

---

## ✅ Definition of Done

`main.pdf` exists and is non-trivial · **zero LaTeX errors** · `main.bbl` resolved all citations · every `\cite{}` maps to a complete `refs.bib` entry · **no fabricated numbers** anywhere · **every figure embedded as an editable vector PDF** (original `.png` kept) · the adversarial **review stage ran** (`logs/5_review.io.md`) · and `python ts-paper/scripts/run_gates.py <workdir> all` **exits zero**.

---

<p align="center">
  <i>The model does the reasoning. The code keeps it honest. You get a paper.</i>
</p>
