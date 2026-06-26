<p align="center">
  <img src="docs/framework.png" width="100%" alt="spark-to-paper-skills">
</p>

<h1 align="center">spark-to-paper-skills</h1>

<h3 align="center"><b><i>Drop a spark. Get a paper.</i></b></h3>

<p align="center">
  <b>The only <a href="https://docs.anthropic.com/en/docs/agents-and-tools/claude-code">Claude Code</a> plugin that goes fully end-to-end —<br>
  idea → literature → writing → experiments → editable vector figures → compiled PDF.<br>
  No app. No server. Just install the plugin and ask.</b>
</p>

<p align="center">
  <a href="https://github.com/Albus-White/spark-to-paper-skills/releases/latest"><img src="https://img.shields.io/github/v/release/Albus-White/spark-to-paper-skills?label=Latest%20Release&color=d97757" alt="Latest Release"></a>
  <img src="https://img.shields.io/badge/Claude_Code-Plugin-d97757?logo=anthropic&logoColor=white" alt="Claude Code Plugin">
  <img src="https://img.shields.io/badge/Skills-13-6f42c1" alt="13 skills">
  <img src="https://img.shields.io/badge/Figures-Editable_Vector-ff8c42" alt="Editable vector figures">
  <img src="https://img.shields.io/badge/Integrity-Machine--Checked-b31b1b" alt="Machine-checked integrity">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#-generated-paper-showcase">Paper Showcase</a> ·
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-the-pipeline">Pipeline</a> ·
  <a href="#-the-skills">Skills</a> ·
  <a href="#-the-figure-engine">Figure Engine</a>
</p>

---

<p align="center">
  <img src="docs/method.png" width="100%" alt="spark-to-paper-skills method overview">
</p>

---

## Generated Paper Showcase

<table>
<tr>
<td width="18%">
<a href="docs/showcase/SHOWCASE.md"><img src="docs/showcase/pm25_forecasting-01.png" width="140" alt="Sample Paper"/></a>
</td>
<td valign="middle">
<h3>4 papers across 4 domains</h3>
Environmental monitoring · Energy forecasting · Environmental AI · Computer vision — generated end-to-end by the skill suite, each with real citations, editable vector figures, and compiled PDF output.<br><br>
<a href="docs/showcase/SHOWCASE.md"><img src="https://img.shields.io/badge/View_Full_Showcase_%E2%86%92-4_Papers-d73a49?style=for-the-badge" alt="View Showcase"></a>
</td>
</tr>
</table>

---

## One Command

```bash
git clone https://github.com/Albus-White/spark-to-paper-skills.git ~/.claude/skills/spark-to-paper-skills
```

Then ask Claude:

```
Run ts-paper on this proposal.
```

Paste your idea, proposal, or data — the orchestrator auto-routes and runs the full chain.

---

## What Is This?

**You drop a spark. Claude writes the paper. Small scripts do only the irreducible parts.**

`spark-to-paper-skills` is a suite of **13 composable Claude Code skills** that turn any of three inputs — a one-line research idea, a full proposal, or a proposal with real experimental results — into a **publication-format paper**: drafted section-by-section as LaTeX, cited with real verified references, illustrated with editable vector figures, and compiled to a finished PDF.

Two integrity modes ensure honesty: **proposal mode** never fabricates numbers (result cells stay blank), while **data-aware mode** traces every number to your real data. Both are machine-checked — the build fails on violations.

---

## The Pipeline

One orchestrator (`ts-paper`) routes the input, then drives a **7-stage chain**:

```
                         ┌──────────────── optional upstream ────────────────┐
 [corpus.jsonl] ─▶ ts-kg-build ─▶ kg/         (research-pattern KG)
 [raw idea]     ─▶ ts-idea2story ─▶ story + citation seed
                         └──────────────────────────────────────────────────┘
                                                │
 [proposal  OR  proposal + real results]  ─────▶ ts-paper  (Stage 0: ROUTE)
                                                │
   1. ts-paper-plan ──▶ blueprint.json          title · keywords · contributions
   2. ts-paper-cite ──▶ refs.bib                ≥40 REAL refs via WebSearch + Crossref
   3. ts-paper-write ─▶ sections/*.tex          all sections in one holistic pass
   4. ts-paper-refine ▶ right-size + de-AI      scrub + logic self-check
   5. ts-paper-review ▶ adversarial review      multi-reviewer hardening
   6. ts-paper-figure ▶ figures + vectorize     image-model → DrawAI hybrid → editable PDF
   7. ts-paper-latex ─▶ main.pdf                assemble + compile
                                                │
   8. ts-paper-experiment (AUTO) ─▶ run feasible experiments, fill tables, recompile
```

---

## The Skills

| Skill | Stage | Role |
|---|---|---|
| `ts-paper` | orchestrator | Routes input and drives the 7-stage chain |
| `ts-idea2story` | upstream | Raw idea → structured research story + citation seed |
| `ts-kg-build` | upstream (opt.) | Corpus → research-pattern knowledge graph for recall |
| `ts-paper-plan` | 1 | Proposal → `blueprint.json` (one reasoning pass) |
| `ts-paper-cite` | 2 | Real, complete bibliography (WebSearch + Crossref, floor 40) |
| `ts-paper-write` | 3 | Draft all sections as LaTeX in one holistic pass |
| `ts-paper-refine` | 4 | Right-size to word bands + de-AI scrub + logic self-check |
| `ts-paper-review` | 5 | Adversarial peer-review hardening |
| `ts-paper-figure` | 6 | Figure routing: matplotlib (data) / image model (schematics) |
| `ts-paper-data` | 6 (data) | Data-aware mode: real results → filled tables + plots |
| `ts-figure-optimize` | 6 (vector) | Raster → editable SVG/PDF/PPTX via DrawAI hybrid |
| `ts-paper-latex` | 7 | Assemble + compile the final PDF |
| `ts-paper-experiment` | 8 | Run feasible experiments, fill tables, recompile |

---

## What Makes It Different

| Capability | How It Works |
|---|---|
| **End-to-End** | Idea → literature → writing → experiments → figures → compiled PDF — all inside Claude Code |
| **Editable Vector Figures** | AI-generated rasters reconstructed as editable SVG/PDF/PPTX via DrawAI hybrid (~0.91 SSIM) |
| **Machine-Checked Integrity** | No fabricated numbers, every citation verified, deterministic gates fail the build on violations |
| **Two Integrity Modes** | Proposal mode (forward-looking, no numbers) and data-aware mode (every number traced to real data) |
| **Template-Agnostic** | NeurIPS and IIETA templates bundled; add any venue by dropping a template directory |
| **Adversarial Review** | Multi-reviewer hardening with verbatim-quote anti-skim — argues the other side of your claims |
| **Auto-Experiments** | Stage 8 runs feasible experiments on real data, fills result tables, and recompiles |

---

## The Figure Engine

`ts-figure-optimize` is the suite's heavy vectorizer, vendoring the full **DrawAI engine**. It does not embed a bitmap — it decomposes and reconstructs:

```
raster figure (PNG/JPG)
   ├─ SAM3            → segment regions        (local, GPU, no account)
   ├─ PaddleOCR       → read every text run    (local, GPU, no account)
   ├─ Box-IR          → structured layout IR
   └─ HYBRID build    → pixel-exact render + editable <text> overlay
   │
   └─▶ editable SVG · vector PDF · editable PPTX
```

**~0.91 SSIM** — the graphics stay pixel-exact (they ARE the approved render) and only the re-typed labels differ from the original. Key-free, no account needed.

---

## Quick Start

### 1 · Install

**Option A — Install as a Claude Code plugin (recommended)**

```bash
git clone https://github.com/Albus-White/spark-to-paper-skills.git ~/.claude/skills/spark-to-paper-skills
```

Auto-loads on next session. Skills available as `/spark-to-paper:ts-paper`, etc.

**Option B — Try before you install**

```bash
git clone https://github.com/Albus-White/spark-to-paper-skills.git
claude --plugin-dir ./spark-to-paper-skills
```

**Option C — Copy as standalone skills**

```bash
git clone https://github.com/Albus-White/spark-to-paper-skills.git
cp -r spark-to-paper-skills/skills/ts-* ~/.claude/skills/
```

**Option D — Git submodule**

```bash
git submodule add https://github.com/Albus-White/spark-to-paper-skills.git .claude/skills/spark-to-paper-skills
```

> The suite checks GitHub for newer versions on each run. To update: `git -C ~/.claude/skills/spark-to-paper-skills pull`

### 2 · (Optional) Configure secrets

| Secret | Variables | Used by | When needed |
|---|---|---|---|
| **Figure model** | `TS_FIG_API_KEY`, `TS_FIG_BASE_URL`, `TS_FIG_MODEL` | `ts-paper-figure` | Render schematics with an image model |
| **Vision QA** | `OPENAI_API_KEY`, `VISION_MODEL` | `ts-figure-optimize` | Correct figure text, compare per-region defects |
| **Embeddings** | `TS_EMBED_*` | `ts-kg-build`, `ts-idea2story` | KG-grounded recall (optional, graceful degradation) |
| **DrawAI weights** | `HF_TOKEN` | `setup_drawai.py` | Download gated SAM3 weights once |
| **Overleaf sync** | `OVERLEAF_GIT_URL`, `OVERLEAF_TOKEN` | `ts-paper-experiment` | Sync with Overleaf when enabled |

Copy `.env.example` → `.env` and fill in only what you use.

### 3 · Just ask Claude

```
Run ts-paper on this proposal.
```

Paste your idea, proposal, or proposal + data. The orchestrator auto-routes, runs the chain, and delivers a compiled paper.

---

## Requirements

- **Claude Code** (the suite is a plugin)
- **Python 3.10+** with `pip install -r skills/ts-figure-optimize/requirements.txt`
- **LaTeX** (`latexmk` + a TeX distribution) for the compile stage
- *Optional:* DrawAI runtime (~4 GB) · image-model endpoint · LibreOffice

---

## FAQ

<details>
<summary><b>Will it invent results?</b></summary>
<br>
No. In proposal mode, <code>draft_lint</code> fails the build on any prose number not backed by data. In data-aware mode, every number is audited against <code>results.facts.json</code>.
</details>

<details>
<summary><b>How is this different from AutoResearchClaw / AI-Scientist / Kosmos?</b></summary>
<br>
The heavy autonomous scientists match the breadth but are standalone Python products (Docker/Neo4j/large codebases). The other skills don't run experiments or draw figures. This is the only <b>pure Claude Code plugin</b> that does the whole arc — and the only tool with an editable-vector figure engine.
</details>

<details>
<summary><b>Do I need GPUs?</b></summary>
<br>
Only for DrawAI vectorization. matplotlib figures are born-vector and skip the engine. A paper with no figures skips Stage 6 entirely. DrawAI also runs on CPU.
</details>

<details>
<summary><b>Can I use a venue that isn't bundled?</b></summary>
<br>
Yes — drop a <code>templates/&lt;name&gt;/</code> directory with <code>template.json</code> + LaTeX assets. No code changes.
</details>

---

## Star History

<p align="center">
  <a href="https://star-history.com/#Albus-White/spark-to-paper-skills&Date">
    <img src="https://api.star-history.com/svg?repos=Albus-White/spark-to-paper-skills&type=Date" width="80%" alt="Star History Chart">
  </a>
</p>

---

<p align="center">
  <i>The model does the reasoning. The code keeps it honest. You get a paper.</i><br>
  <sub>Built on <a href="https://docs.anthropic.com/en/docs/agents-and-tools/claude-code">Claude Code</a> · Figure engine vendored from DrawAI · <a href="LICENSE">MIT License</a></sub>
</p>
