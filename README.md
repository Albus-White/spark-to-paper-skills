<p align="center">
  <img src="docs/framework.png" width="100%" alt="spark-to-paper-skills framework">
</p>

<h1 align="center">✨ spark-to-paper-skills</h1>

<h3 align="center"><b><i>Drop a spark. Get a paper.</i></b></h3>

<p align="center">
  <b>The only <a href="https://docs.claude.com/en/docs/claude-code">Claude Code</a> <i>skill suite</i> that goes fully end-to-end —<br>
  literature → writing → experiments → figure generation → <i>editable vector</i> figures → compiled PDF.<br>
  No app. No server. No setup. Just drop the skills in and ask.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-Pure_Skill_Suite-d97757?logo=anthropic&logoColor=white" alt="Pure Claude Code skill suite">
  <img src="https://img.shields.io/badge/Scope-End--to--End-2ea44f" alt="End to end">
  <img src="https://img.shields.io/badge/Skills-13_active-6f42c1" alt="13 skills">
  <img src="https://img.shields.io/badge/Figures-Editable_Vector-ff8c42" alt="Editable vector figures">
  <img src="https://img.shields.io/badge/Integrity-Machine--checked-b31b1b" alt="Machine-checked integrity">
  <img src="https://img.shields.io/badge/Templates-Agnostic-0969da" alt="Template agnostic">
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

<p align="center">
  <img src="docs/method.png" width="100%" alt="spark-to-paper-skills framework">
</p>


---

## 🧭 How It Compares

The "AI-for-research" landscape has many tools, but they cover **different capabilities**. Here's the honest matrix — what each one actually does:

<p align="center">
  <img src="docs/comparison.svg" width="100%" alt="Capability comparison matrix across AI-research tools">
</p>

<p align="center"><sub><b>✓</b> full&nbsp;&nbsp;·&nbsp;&nbsp;<b>●</b> partial&nbsp;&nbsp;·&nbsp;&nbsp;<b>–</b> none&nbsp;&nbsp;|&nbsp;&nbsp;sources: <a href="https://github.com/Imbad0202/academic-research-skills">ARS</a> · <a href="https://github.com/AgentAlphaAGI/Idea2Paper">Idea2Paper</a> · <a href="https://github.com/aiming-lab/AutoResearchClaw">AutoResearchClaw</a> · <a href="https://github.com/SakanaAI/AI-Scientist">AI-Scientist</a> · <a href="https://github.com/jimmc414/Kosmos">Kosmos</a> · <a href="https://github.com/karpathy/autoresearch">karpathy/autoresearch</a> · <a href="https://victorchen96.github.io/auto_research/framework.html">auto_research</a></sub></p>

> 🌟 **The one row that lights up everywhere.** spark-to-paper-skills is the **only *pure Claude Code skill*** that runs the *whole* arc — and the only tool of any kind that does **experiments + auto-writing + auto-figure-drawing + editable-vector figures** together with machine-checked integrity.
>
> The heavy autonomous scientists ([AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw), [AI-Scientist](https://github.com/SakanaAI/AI-Scientist), [Kosmos](https://github.com/jimmc414/Kosmos)) match the *breadth* — but ship as **standalone Python products** (Docker, Neo4j, tens of thousands of LOC). The other *skills* ([ARS](https://github.com/Imbad0202/academic-research-skills), [Idea2Story](https://github.com/AgentAlphaAGI/Idea2Paper)) don't run experiments or draw figures. **Nobody else gives you all of it as drop-in skills.**

---

## 💡 What Is This?

**You drop a spark. Claude writes the paper. Small scripts do only the irreducible parts.**

`spark-to-paper-skills` (a.k.a. **Auto-Research-PaperGenSkill**) is a suite of **13 composable Claude Code skills** that turn any of three inputs —

- 🧠 a **one-line research idea**,
- 📋 a **full proposal** (problem / method / evaluation / contributions), or
- 📊 a **proposal *with real experimental results*** (CSV / JSON / a pasted table / numbers in prose) —

into a **publication-format paper**: drafted section-by-section as LaTeX, cited with **real, verified** references, illustrated with **editable vector figures**, and compiled to a finished `main.pdf` — all without leaving Claude Code.

---

## 🎯 Design Philosophy

| Principle | What it means |
|---|---|
| 🧠 **Model reasons, code backstops** | Claude does the thinking — writing, literature search, vision figure critique, adversarial review. Tiny Python scripts do *only* the deterministic parts: linters, LaTeX assembly, image gen, embeddings, matplotlib, vectorization. |
| 🪶 **Pure skill, zero infra** | No standalone app, no server, no database, no Docker required for the core. `cp` the folders into `.claude/skills/` and go. |
| 🏆 **Quality first, cost second** | Verify every citation, self-review, run the linters, polish. Never trade a quality step for a saved turn. |
| 🔒 **Integrity is absolute** | Proposal mode never invents a number; data-aware mode traces every number to your data. A red linter **fails the build**. |

---

## 📦 What You Get

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

<details>
<summary><b>Stage 0 — Input routing (a Claude reasoning step, no fixed schema)</b></summary>

<br>

| Class | What was dropped | Route | `results_mode` |
|---|---|---|---|
| **(a) bare idea** | one line, no method/eval structure | `ts-idea2story` → then plan | `proposal` |
| **(b) proposal** | problem + method + eval, **no measured results** | plan (proposal) | `proposal` |
| **(c) proposal + REAL results** | measured numbers in prose, or any attached data file | plan → **`ts-paper-data`** | `data_aware` |
| **(d) existing `story.json`** | an 8-field story from a prior run | plan (skip idea2story) | `proposal` |

</details>

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

The capability **no other skill suite has**. AI image models produce **rasters** — but a paper needs **editable vector** figures. `ts-figure-optimize` is the suite's heavy, maximum-fidelity vectorizer, and it **vendors the full DrawAI engine** (~5 MB source, in `engine/`).

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

Quality is not one check — it's **four complementary layers**. Claude does the judgement; code is the deterministic backstop.

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

---

## 🔒 Integrity

LLM-written papers are notorious for two failure modes: **hallucinated citations** (real-looking references that don't support the claim, or don't exist) and **fabricated numbers** (plausible metrics that were never measured). This suite treats both as **build-breaking errors, not style issues** — every rule below is machine-checked.

- **Proposal mode never fabricates numbers.** Tables stay blank, prose is forward-looking. `draft_lint` fails on a stray decimal.
- **Data-aware mode traces every number** to `results.facts.json` (the real-number ground truth) — the number-audit flags any that don't.
- **Citations are real and complete.** Every `refs.bib` entry exists and was verified; no stubs, no filler, no orphan `\cite{}`. `citations_lint` enforces it.
- **Every figure is a true editable vector** — an actual *redraw* (editable `<text>` + primitives), not a raster wrapped in SVG. `check_vector_pdf.py` is the gate.

---

## 📐 Template-Agnostic

Write to **whatever venue you pick** — content quality is invariant. A template is a directory under `ts-paper/templates/<name>/` with `template.json` + its LaTeX `.sty`/`.cls` + `main.tex.tmpl`.

| Template | Venue | Style |
|---|---|---|
| `ts_iieta` *(default)* | Traitement du Signal | two-column, numeric citations |
| `neurips` | NeurIPS | single-column, author-year |

**Add a venue by dropping a `templates/<name>/` dir — no code changes.**

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
- ☁️ **Overleaf is OFF by default**; enable via `paper_config.yaml` + `.env`.

---

## ⚙️ Requirements

- **Claude Code** (the suite is a set of skills)
- **Python 3.10+** with figure deps: `pip install -r ts-figure-optimize/requirements.txt`
- **LaTeX** (`latexmk` + a TeX distribution) for the compile stage
- *Optional:* **LibreOffice** (PPTX gate) · **~4 GB + `HF_TOKEN`** (DrawAI) · an **image-model endpoint** (free-form figures) · **Codex/OpenAI auth** (DrawAI vector path + GPT vision)

---

## 🙋 FAQ

<details>
<summary><b>Will it invent results to make the paper look complete?</b></summary>

No. In proposal mode it physically cannot — `draft_lint` fails the build on any prose number not backed by data. In data-aware mode every number is audited against your real `results.facts.json`.
</details>

<details>
<summary><b>How is this different from AutoResearchClaw / AI-Scientist / Kosmos / ARS?</b></summary>

See <a href="#-how-it-compares">How It Compares</a>. Short version: the heavy autonomous scientists match the breadth but are standalone Python products (Docker/Neo4j/large codebases); the other skills don't run experiments or draw figures. This is the only **pure Claude Code skill** that does the whole arc — and the only tool with an **editable-vector figure engine**.
</details>

<details>
<summary><b>Do I need GPUs or the heavy DrawAI runtime?</b></summary>

Only for free-form raster figures. DrawAI runs on CPU; matplotlib figures are born-vector and skip the engine; a paper with no figures skips Stage 6 entirely.
</details>

<details>
<summary><b>Can I use a venue that isn't bundled?</b></summary>

Yes — drop a `templates/<name>/` directory with a `template.json` + LaTeX assets. No code changes.
</details>

---

## ✅ Definition of Done

`main.pdf` exists and is non-trivial · **zero LaTeX errors** · `main.bbl` resolved all citations · every `\cite{}` maps to a complete `refs.bib` entry · **no fabricated numbers** anywhere · **every figure embedded as an editable vector PDF** · the adversarial **review stage ran** · and `run_gates.py <workdir> all` **exits zero**.

---

## ⭐ Star History

<p align="center">
  <a href="https://star-history.com/#Albus-White/spark-to-paper-skills&Date">
    <img src="https://api.star-history.com/svg?repos=Albus-White/spark-to-paper-skills&type=Date" width="80%" alt="Star History Chart">
  </a>
</p>

---

<p align="center">
  <i>The model does the reasoning. The code keeps it honest. You get a paper.</i><br>
  <sub>Built on <a href="https://docs.claude.com/en/docs/claude-code">Claude Code</a> · figure engine vendored from DrawAI · template-agnostic by design</sub>
</p>
