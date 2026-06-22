<h1 align="center">✨ spark-to-paper-skills</h1>

<h3 align="center"><b><i>Drop a spark. Get a paper.</i></b></h3>

<p align="center">
  <b>A <a href="https://docs.claude.com/en/docs/claude-code">Claude Code</a> skill suite that turns a one-line idea, a proposal, or a proposal&nbsp;+&nbsp;real&nbsp;results<br>into a compiled, journal-ready LaTeX paper — figures vectorized, citations real, numbers never faked.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-Skill_Suite-d97757?logo=anthropic&logoColor=white" alt="Claude Code Skill Suite">
  <img src="https://img.shields.io/badge/Skills-13_active-6f42c1" alt="13 skills">
  <img src="https://img.shields.io/badge/Pipeline-7_stages_+_experiments-2ea44f" alt="7 stages">
  <img src="https://img.shields.io/badge/Templates-Agnostic-0969da" alt="Template-agnostic">
  <img src="https://img.shields.io/badge/Integrity-Machine--checked-b31b1b" alt="Machine-checked integrity">
  <img src="https://img.shields.io/badge/Figures-Editable_Vector-ff8c42" alt="Editable vector figures">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
</p>

<p align="center">
  <a href="#-how-it-compares">🧭 Compare</a> ·
  <a href="#-quick-start">🚀 Quick Start</a> ·
  <a href="#-the-pipeline">🔬 Pipeline</a> ·
  <a href="#-the-skills">🧩 Skills</a> ·
  <a href="#%EF%B8%8F-the-figure-engine-drawai">🖼️ Figure Engine</a> ·
  <a href="#%EF%B8%8F-the-quality-stack">🛡️ Quality</a> ·
  <a href="#-integrity">🔒 Integrity</a> ·
  <a href="#-faq">🙋 FAQ</a>
</p>

---

<p align="center"><b><i>One spark in. One paper out.</i></b></p>

```text
You:  Run ts-paper on this.   ⟵ paste an idea, a proposal, or a proposal + real results

✨ ts-paper  → route → plan → cite → write → refine → review → figure → latex → 📄 main.pdf
              real citations · editable vector figures · zero fabricated numbers · machine-checked
```

---

## 🧭 How It Compares

The "AI-for-research" landscape splits into **three camps**, and the word *autonomous* hides the real differences:

- 🖋️ **Writers** — turn an idea/proposal into a *manuscript*: **✨ spark-to-paper-skills** · ARS · Idea2Paper
- 🔬 **Autonomous scientists** — also *run the experiments*: AutoResearchClaw · AI-Scientist · Kosmos
- ⚙️ **Substrates** — the *loop / orchestration machinery* the others build on: karpathy/autoresearch · auto_research

This suite is a **writer** — with a figure engine none of the others have (★ = a standout strength).

| Project | What it is | Produces | Runs experiments? | Literature & citations | ★ Standout strength | Best for |
|---|---|---|---|---|---|---|
| **✨ spark-to-paper-skills** <br>*(this repo)* | Claude Code **skill suite** (13 skills) | Compiled **LaTeX paper** (PDF) | Optional (Stage 8 — *feasible-only, never faked*) | Real refs, WebSearch + Crossref, machine-checked (≥40) | **Editable-vector figure engine** (DrawAI: SAM3 + OCR + Codex) | Idea/proposal → a **submission-ready paper with publication-grade editable figures** |
| [**academic-research-skills**](https://github.com/Imbad0202/academic-research-skills) (ARS) | Claude Code **plugin / skill suite** (large) | Sections, lit reviews, formatted citations (MD/DOCX/PDF) | ✗ | **Deep citation integrity** — claim-level audits, hallucination detection, PRISMA | *"Copilot, not pilot"* — strictest citation auditing | A researcher who **writes it themselves**, wanting grunt-work + integrity gating |
| [**Idea2Paper / Idea2Story**](https://github.com/AgentAlphaAGI/Idea2Paper) (AgentAlpha) | Python framework (MIT, arXiv) | Structured **research story / proposal** (`final_story.json`) | ✗ | KG recall over ICLR data + RAG novelty dedup | **Pre-computed ICLR knowledge graph** + anchored deterministic review | Turning a raw idea into a **novel, reviewable research story** (the front stage) |
| [**AutoResearchClaw**](https://github.com/aiming-lab/AutoResearchClaw) | Standalone **Python product** (~80k LOC, 23-stage) | Full paper + experiment code + charts + reviews | ★ **Yes** — Docker / SSH / Colab + domain agents | Real OpenAlex / Semantic Scholar / arXiv, 4-layer verify | Real experiments + **self-evolving** + model-agnostic | Fully autonomous **end-to-end research incl. experiments** |
| [**AI-Scientist**](https://github.com/SakanaAI/AI-Scientist) (Sakana AI) | The **seminal** autonomous AI-scientist (Python) | Full papers (exp + figs + LaTeX) + AI peer review | ★ **Yes** — code exec (NanoGPT / Diffusion / Grokking templates) | Semantic Scholar / OpenAlex + auto-cite + novelty check | **First** fully-autonomous end-to-end paper generation | Autonomous research in **templated ML domains** |
| [**Kosmos**](https://github.com/jimmc414/Kosmos) (jimmc414) | Open-source autonomous **"AI scientist"** (Python) | Research **reports** + knowledge graphs + notebooks/figures | ★ **Yes** — Docker sandboxes (Python/R), real **data analysis** (h5ad/Parquet) | ArXiv / PubMed / Semantic Scholar; 20:1 compression over ~1,500 papers/run | **116 domain skills** + Neo4j KG + ScholarEval 8-dim validation | Exploratory, **data-driven discovery** (esp. bio / data analysis) |
| [**karpathy/autoresearch**](https://github.com/karpathy/autoresearch) | Minimal repo (10 files) — a "research-org" skeleton | A better-trained **model** + experiment log *(not a paper)* | ★ **Yes** — but *only* the loop: edit `train.py`, 5-min train, keep/discard | ✗ | **Bare-bones experiment loop** — you program `program.md` | **Autonomous ML experimentation** / "research-org code" |
| [**auto_research**](https://victorchen96.github.io/auto_research/framework.html) (Deli_AutoResearch) | A **protocol / convention framework** (no executable code) | Long-horizon research → papers / surveys | ✓ handles long compute jobs (fabrication source stays the LLM) | Citation verification as a *mechanical step* | **Long-horizon stability** — 3-layer watchdog, fresh sessions, stall pivots | Orchestrating **multi-day/week** autonomous runs without context collapse |

> **TL;DR** — Writing a paper *from an idea/proposal*? → **this repo** (or ARS to drive it yourself; Idea2Story for the idea→story front, which this suite also bundles as `ts-idea2story`). Want it to *run the experiments too*? → AutoResearchClaw, AI-Scientist, or Kosmos. Building the *autonomous loop itself*? → karpathy/autoresearch or auto_research. They're **complementary, not competitors**: discover results with Kosmos/AI-Scientist, then bring the figures *here* to vectorize. **What's unique here: a finished, well-cited paper with truly editable vector figures — and never a fabricated number.**

---

## 💡 What Is This?

**You drop a spark. Claude writes the paper. Small scripts do only the irreducible parts.**

`spark-to-paper-skills` (a.k.a. **Auto-Research-PaperGenSkill**) is a suite of **13 composable Claude Code skills** that turn any of three inputs —

- 🧠 a **one-line research idea**,
- 📋 a **full proposal** (problem / method / evaluation / contributions), or
- 📊 a **proposal *with real experimental results*** (CSV / JSON / a pasted table / numbers in prose) —

into a **publication-format paper**: drafted section-by-section as LaTeX, cited with **real, verified** references, illustrated with **editable vector figures**, and compiled to a finished `main.pdf`.

---

## 🎯 Design Philosophy

Four principles, stated plainly — they explain every decision in this repo.

| Principle | What it means |
|---|---|
| 🧠 **Model reasons, code backstops** | Claude does the thinking — writing, literature search, vision figure critique, adversarial review. Tiny Python scripts do *only* the deterministic parts: linters, LaTeX assembly, image gen, embeddings, matplotlib, vectorization. |
| 🏆 **Quality first, cost second** | Never trade quality for a saved turn. Verify every citation, self-review, run the linters, polish. Cost stays low as a *by-product* of Claude doing more per turn — not by skipping a review. |
| 🔒 **Integrity is absolute** | Proposal mode never invents a number; data-aware mode traces every number to your data. Citations must be real and complete. A red linter **fails the build** — "it looked fine" is not acceptance. |
| 🧩 **Composable & template-agnostic** | 13 focused skills, one orchestrator. Any venue works by dropping a `template.json` — no code changes. |

---

## 📦 What You Get

Run the suite in a working dir (default `./ts_paper_run/`) and you end up with a self-contained, Overleaf-ready paper:

| | Artifact | What it is |
|---|---|---|
| 📐 | `main.tex` · `main.pdf` | Compiled paper in the chosen venue template |
| 📝 | `sections/*.tex` + `abstract.tex` | LaTeX body, one file per section |
| 🗂️ | `blueprint.json` | Structured plan: title, keywords, 3 contributions, notation, per-section word targets |
| 📚 | `refs.bib` + `claims_map.json` | **Real, fully-specified** BibTeX (≥40 refs) — every `\cite{}` justified |
| 🖼️ | `figures/<label>.pdf` (+ `.png` + source) | **Editable vector** figures — matplotlib born-vector, or rasters reconstructed by DrawAI |
| 🔎 | `logs/<n>_<stage>.io.md` + `index.md` | Per-stage INPUT / DECISIONS / OUTPUT trace — fully inspectable |
| ✅ | green `run_gates.py` | Every deterministic gate passed (citations, draft, vectors, LaTeX) |

---

## 🚀 Quick Start

### 1 · Install the skills

```bash
# Per-project
cp -r */ <your-project>/.claude/skills/

# …or globally
cp -r */ ~/.claude/skills/
```

### 2 · (Optional) Configure secrets

Copy `.env.example` → `.env` (gitignored, auto-loaded) and fill in only what you use:

| Variable | Used by | When you need it |
|---|---|---|
| `TS_FIG_API_KEY` / `TS_FIG_BASE_URL` / `TS_FIG_MODEL` | `ts-paper-figure` | To render free-form schematics with an image model |
| `OPENAI_API_KEY` / `VISION_MODEL` | `ts-figure-optimize` | GPT vision text-correction + per-region defect diff (falls back to `~/.codex/auth.json`) |
| `TS_EMBED_*` | `ts-kg-build`, `ts-idea2story` | KG-grounded recall (optional — degrades gracefully) |
| `HF_TOKEN` | `setup_drawai.py` | **One-time** download of the gated SAM3 weights |
| `OVERLEAF_GIT_URL` / `OVERLEAF_TOKEN` | `ts-paper-experiment` | Only if you turn Overleaf sync on (off by default) |

### 3 · Just ask Claude

```
Run ts-paper on this proposal.   ⟵ then paste / attach your idea, proposal, or proposal + data
```

The orchestrator **auto-routes** your input, picks the right mode, runs the full chain, and reports page count, sections, reference count, the review outcome, and the figures — all editable vector PDFs.

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
   1. ts-paper-plan ──▶ blueprint.json          (title · keywords · 3 contributions · notation · plan)
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

| Class | What was dropped | Route | `results_mode` |
|---|---|---|---|
| **(a) bare idea** | one line, no method/eval structure | `ts-idea2story` → then plan | `proposal` |
| **(b) proposal** | problem + method + eval, **no measured results** | plan (proposal) | `proposal` |
| **(c) proposal + REAL results** | measured numbers in prose, or any attached data file | plan → **`ts-paper-data`** | `data_aware` |
| **(d) existing `story.json`** | an 8-field story from a prior run | plan (skip idea2story) | `proposal` |

### Two modes, opposite integrity rules

| | **Proposal mode** | **Data-aware mode** |
|---|---|---|
| Numbers | ⛔ never invent — result cells stay blank (`--`) | ✅ report the real numbers, in past tense |
| Tense | forward-looking ("we evaluate… we expect…") | retrospective ("we measured…") |
| Guarantee | no metric ever fabricated | **every number must trace to your data** (machine-audited) |

---

## 🧩 The Skills

14 skill folders ship; **13 are active** (`ts-paper-vector` is retired, superseded by `ts-figure-optimize`).

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

The headline component, and what nothing else on the comparison table has. AI image models produce **rasters** — but a paper needs **editable vector** figures. `ts-figure-optimize` is the suite's heavy, maximum-fidelity vectorizer, and it **vendors the full DrawAI engine** (~5 MB source, in `engine/`).

It does **not** just embed a bitmap. It *decomposes and reconstructs* the figure:

```
raster figure (PNG/JPG)
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

> **Honest ceiling:** re-typed text can't beat the original's font/AA/sub-pixel rendering, so ~0.90 SSIM is the expected, *correct* outcome for a faithful editable redraw — not a failure. The suite **never fakes a similarity score** and always keeps the original.

Provision the runtime once (~4 GB SAM3 / PaddleOCR / RMBG weights + venv, auto-deployed on first run):

```bash
python ts-figure-optimize/scripts/setup_drawai.py --device cpu   # provision
python ts-figure-optimize/scripts/setup_drawai.py --check-only   # doctor: OK?
```

---

## 🛡️ The Quality Stack

Quality is not one check — it's **four complementary layers**, each doing what it's best at. Claude does the judgement; code is the deterministic backstop.

| Layer | Owner | What it catches |
|---|---|---|
| **1 · Deterministic gates** | code | section shape, word bands, no-fabrication / number-audit, citation completeness, AI-phrase tells, vector-PDF presence, `error_count == 0` — **a red gate is a hard stop** |
| **2 · Self-review** | Claude (in-pass) | right-sizing, term/coherence consistency, **de-AI scrub**, logic self-check |
| **3 · Adversarial review** | Claude (default) | the one thing self-review can't do — *argue the other side*: N isolated reviewers + verbatim-quote anti-skim + adversarial-verify + loop-until-dry |
| **4 · Vision critique** | Claude (figures) | `Read`s each rendered figure, critiques faithfulness/readability/aesthetics before accepting, then vectorizes |

All gates flow through one entry point — don't ship on a red one:

```bash
python ts-paper/scripts/run_gates.py <workdir> all     # nonzero exit = NOT done
```

> **Engine-agnostic review.** Adversarial review runs via the best available tier — Workflow tool → parallel subagents → fully in-context — with an *identical algorithm and output*. It is **never skipped merely because a Workflow tool is absent**; skip it only on an explicit request for a quick draft.

---

## 🔒 Integrity

LLM-written papers are notorious for two failure modes: **hallucinated citations** (real-looking references that don't support the claim, or don't exist) and **fabricated numbers** (plausible metrics that were never measured). This suite treats both as **build-breaking errors, not style issues** — every rule below is machine-checked.

- **Proposal mode never fabricates numbers.** No invented metrics or percentages; tables stay blank, prose is forward-looking. `draft_lint` fails on a stray decimal.
- **Data-aware mode traces every number.** Each decimal/percent must appear in `results.facts.json` (the real-number ground truth) — the number-audit flags any that don't.
- **Citations are real and complete.** Every `refs.bib` entry is a paper that exists and was verified; no title-only stubs, no off-topic filler, no orphan `\cite{}`. `citations_lint` enforces it.
- **Every figure is a true editable vector** — and every vector-type figure is an actual *redraw* (editable `<text>` + primitives), not a raster wrapped in SVG. `check_vector_pdf.py` is the gate.

---

## 📐 Template-Agnostic

The suite writes to **whatever venue you pick**; content quality is invariant. A template is a directory under `ts-paper/templates/<name>/` holding `template.json` (sections, word bands, citation style, caption rules, masthead) + its LaTeX `.sty`/`.cls` + `main.tex.tmpl`.

| Template | Venue | Style |
|---|---|---|
| `ts_iieta` *(default)* | Traitement du Signal | two-column, numeric citations |
| `neurips` | NeurIPS | single-column, author-year |

**Add a venue by dropping a `templates/<name>/` dir — no code changes.** Every downstream script reads `template.json`; nothing hardcodes a venue.

---

## 🧪 Stage 8 — Experiments + Repair (auto-run)

After Stages 0–7 produce a complete first-draft paper, **Stage 8 runs automatically** via the in-repo `ts-paper-experiment` skill — turning a no-results draft into a results-bearing manuscript:

```bash
python ts-paper/scripts/handoff_to_experiments.py --workdir <ts_paper_run>   # → experiments/
# ts-paper-experiment ingests input/draft/, diagnoses logic, runs only FEASIBLE
# experiments (real data/code only), fills tables, recompiles → flows back to the run
```

- ✅ Runs **only feasible experiments** on real data/code — and **never invents results**.
- 📄 No real data/code? It writes a **requirements report** and leaves tables in proposal form.
- ☁️ **Overleaf is OFF by default** (no account needed); enable via `paper_config.yaml` + `.env`.

---

## 📁 Working Directory — the Contract Between Stages

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
- **Python 3.10+** with figure deps: `pip install -r ts-figure-optimize/requirements.txt` (`numpy`, `Pillow`, `python-pptx`, `cairosvg` → needs system Cairo, `openai`)
- **LaTeX** (`latexmk` + a TeX distribution) for the compile stage
- *Optional:* **LibreOffice** (`soffice`) — enables the PPTX render gate · **~4 GB disk + `HF_TOKEN`** — only to provision DrawAI · an **image-model endpoint** — only for free-form schematics · **Codex/OpenAI auth** — for the DrawAI vector path + GPT vision steps

---

## 🙋 FAQ

<details>
<summary><b>Will it invent results to make the paper look complete?</b></summary>

No. In proposal mode it physically cannot — `draft_lint` fails the build on any prose number not backed by data. In data-aware mode every number is audited against your real `results.facts.json`.
</details>

<details>
<summary><b>How is this different from AutoResearchClaw / ARS / karpathy's autoresearch?</b></summary>

See <a href="#-how-it-compares">How It Compares</a>. Short version: AutoResearchClaw and karpathy/autoresearch *run experiments*; ARS is a *human-driven copilot with the strictest citation auditing*; this suite turns an idea/proposal into a *finished, well-cited paper with truly editable vector figures*. They're complementary.
</details>

<details>
<summary><b>Do I need GPUs or the heavy DrawAI runtime?</b></summary>

Only for free-form raster figures. DrawAI runs on CPU (`--device cpu`); matplotlib figures are born-vector and skip the engine; a paper with no figures skips Stage 6 entirely.
</details>

<details>
<summary><b>Can I use a venue that isn't bundled?</b></summary>

Yes — drop a `templates/<name>/` directory with a `template.json` + LaTeX assets. No code changes.
</details>

<details>
<summary><b>What if I just want a quick draft without the adversarial review?</b></summary>

Ask explicitly for a quick / no-review draft — the choice is recorded in `logs/0_route.io.md`. By default, review always runs.
</details>

---

## ✅ Definition of Done

`main.pdf` exists and is non-trivial · **zero LaTeX errors** · `main.bbl` resolved all citations · every `\cite{}` maps to a complete `refs.bib` entry · **no fabricated numbers** anywhere · **every figure embedded as an editable vector PDF** (original `.png` kept) · the adversarial **review stage ran** (`logs/5_review.io.md`) · and `python ts-paper/scripts/run_gates.py <workdir> all` **exits zero**.

---

<p align="center">
  <i>The model does the reasoning. The code keeps it honest. You get a paper.</i><br>
  <sub>Built on <a href="https://docs.claude.com/en/docs/claude-code">Claude Code</a> · figure engine vendored from DrawAI · template-agnostic by design</sub>
</p>
