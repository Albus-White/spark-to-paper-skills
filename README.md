<p align="center">
  <img src="docs/framework.png" width="100%" alt="spark-to-paper-skills">
</p>

<h1 align="center">spark-to-paper-skills</h1>

<h3 align="center"><b><i>Drop a spark. Get a paper.</i></b></h3>

<p align="center">
  <i>Every citation verified. Every figure editable. Every number traced to source.</i>
</p>

<p align="center">
  14 composable skills for <b>Claude Code and Codex</b> turn a one-line idea into a compiled PDF —<br>
  real references, editable vector figures, and machine-checked integrity included.<br>
  No app. No server. No setup.
</p>

<p align="center">
  <a href="https://github.com/Albus-White/spark-to-paper-skills/releases/latest"><img src="https://img.shields.io/github/v/release/Albus-White/spark-to-paper-skills?label=Release&color=d97757" alt="Latest Release"></a>
  <a href="https://github.com/Albus-White/spark-to-paper-skills"><img src="https://img.shields.io/github/stars/Albus-White/spark-to-paper-skills?style=flat&color=f5c542" alt="Stars"></a>
  <img src="https://img.shields.io/badge/Claude_Code-Plugin-d97757?logo=anthropic&logoColor=white" alt="Claude Code Plugin">
  <img src="https://img.shields.io/badge/Codex-Plugin-111827?logo=openai&logoColor=white" alt="Codex Plugin">
  <img src="https://img.shields.io/badge/Skills-14_Active-6f42c1" alt="14 skills">
  <img src="https://img.shields.io/badge/Figures-Editable_Vector-ff8c42" alt="Editable vector figures">
  <img src="https://img.shields.io/badge/Integrity-Machine--Checked-b31b1b" alt="Machine-checked integrity">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#-generated-paper-showcase">🏆 Showcase</a> &middot;
  <a href="#-what-makes-it-different">✨ Features</a> &middot;
  <a href="#-how-it-compares">🧭 Compare</a> &middot;
  <a href="#-the-figure-engine">🖼️ Figure Engine</a> &middot;
  <a href="#-the-pipeline">🔬 Pipeline</a> &middot;
  <a href="#-quick-start">🚀 Quick Start</a>
</p>

---

## 🏆 Generated Paper Showcase

<table>
<tr>
<td width="18%">
<a href="docs/showcase/SHOWCASE.md"><img src="docs/showcase/pm25_forecasting-01.png" width="140" alt="Sample Paper"/></a>
</td>
<td valign="middle">
<b>7 papers across 6 domains</b> — environmental monitoring, energy forecasting, environmental AI, computer vision, clinical AI, and bearing fault diagnosis — generated fully end-to-end with real citations, editable vector figures, and compiled PDF output.<br><br>
<a href="docs/showcase/SHOWCASE.md"><img src="https://img.shields.io/badge/View_Full_Showcase_%E2%86%92-555555?style=for-the-badge" alt="View Showcase"></a>&nbsp;
<a href="docs/showcase/SHOWCASE.md"><img src="https://img.shields.io/badge/All_7_Papers-d73a49?style=for-the-badge" alt="All 7 Papers"></a>
</td>
</tr>
</table>

---

## 🔥 What's New

- **`v3.0.0` model-first research lifecycle** — one versioned Idea/claim/contract/evidence graph from
  grounding through release; profile-specific gates; measured feasibility probes; benchmark and
  repository locks; bounded experiment iteration; mechanism diagnosis; Idea revision; canonical
  result provenance; and independent confirmation for consequential high-risk decisions.
- **Adaptive quality controls** — semantic correctness is judged from source evidence by the model;
  scripts enforce only exact facts such as hashes, schemas, citation keys, result bindings, vectors,
  and LaTeX compilation. Figure candidates, reviewers, sections, citations, and verification tests are
  selected from the actual task instead of fixed quotas.
- **User-owned resource and venue design** — the user supplies deadline, compute/server access, cost,
  and priorities; the model measures feasibility and allocates that envelope. Paper structure and
  artifact breadth are grounded in official venue guidance and representative accepted work.

See the implemented architecture in
[`docs/research-closed-loop-architecture.md`](docs/research-closed-loop-architecture.md).

- **Dual-platform distribution** — quality-equivalent source trees under `codex/` and `claude/` keep
  platform adapters separate while sharing the same research contracts.

---

## ⚡ One Command. One Paper.

```bash
# Install — auto-loads on next Claude Code session
git clone https://github.com/Albus-White/spark-to-paper-skills.git
claude --plugin-dir ./spark-to-paper-skills/claude
```

```
Use $ts-paper on this proposal.   ← paste your idea, proposal, or data
```

The orchestrator auto-routes your input, picks the right mode, and runs the full chain.

---

## 📦 What You Get

<table>
<tr><td>📄</td><td><code>main.tex</code> · <code>main.pdf</code></td><td>Compiled paper in the selected venue template</td></tr>
<tr><td>📝</td><td><code>sections/*.tex</code></td><td>One LaTeX source file per section + abstract</td></tr>
<tr><td>🗺️</td><td><code>blueprint.json</code></td><td>Venue-grounded structure, claims, sections, tables, and figures</td></tr>
<tr><td>📚</td><td><code>refs.bib</code></td><td>Real BibTeX entries — every <code>\cite{}</code> verified via WebSearch + Crossref</td></tr>
<tr><td>🖼️</td><td><code>figures/*.pdf</code></td><td>Editable vector figures (SVG + PDF + PPTX), originals always kept</td></tr>
<tr><td>🧪</td><td><code>research/</code></td><td>Lifecycle state, repository/environment locks, run manifests, Idea lineage, and evidence provenance</td></tr>
<tr><td>📋</td><td><code>reports/</code></td><td>Scientific judgments, implementation review, verification, mechanism diagnosis, and gate reports</td></tr>
<tr><td>🚦</td><td><code>run_gates.py</code></td><td>All deterministic gates pass — citations, draft, vectors, LaTeX</td></tr>
</table>

---

## ✨ What Makes It Different

| | Capability | Description |
|:---:|---|---|
| 🖼️ | **Truthful Adaptive Figures** | The model selects a domain-appropriate renderer and candidate budget. Born-vector figures stay vector; approved rasters can be reconstructed as semantic SVG/PDF/PPTX with DrawAI. |
| 🔗 | **End-to-End** | Idea → literature → writing → experiments → figures → compiled PDF. A dual-platform Claude Code and Codex plugin that runs the entire arc. |
| 🔒 | **Machine-Checked Integrity** | No fabricated numbers — ever. Every citation verified. Deterministic gates fail the build on violations. Not a style suggestion — a hard stop. |
| 🔀 | **Two Integrity Modes** | *Proposal mode*: forward-looking, result cells stay blank. *Data-aware mode*: every number traced to your real data, in past tense. Machine-audited. |
| ⚔️ | **Risk-Proportional Review** | The main model reviews the complete evidence bundle. Fresh independent review scales with risk, uncertainty, and material disagreement; fixes close through focused delta review. |
| 🧪 | **Bounded Experiments** | The lifecycle locks code, environment, benchmarks, and protocol; runs pilots before full experiments; classifies failures; diagnoses mechanisms; and accepts negative evidence instead of optimizing for a desirable result. |
| 📐 | **Template-Agnostic** | NeurIPS and IIETA bundled. Add any venue — drop a `templates/<name>/` dir with `template.json` + LaTeX assets. No code changes. |

---

## 🧭 How It Compares

<p align="center">
  <img src="docs/comparison.svg" width="100%" alt="Capability comparison matrix across AI-research tools">
</p>

<p align="center"><sub><b>✓</b> full&nbsp;&nbsp;·&nbsp;&nbsp;<b>●</b> partial&nbsp;&nbsp;·&nbsp;&nbsp;<b>–</b> none&nbsp;&nbsp;|&nbsp;&nbsp;sources: <a href="https://github.com/Imbad0202/academic-research-skills">ARS</a> · <a href="https://github.com/AgentAlphaAGI/Idea2Paper">Idea2Paper</a> · <a href="https://github.com/aiming-lab/AutoResearchClaw">AutoResearchClaw</a> · <a href="https://github.com/SakanaAI/AI-Scientist">AI-Scientist</a> · <a href="https://github.com/jimmc414/Kosmos">Kosmos</a> · <a href="https://github.com/karpathy/autoresearch">karpathy/autoresearch</a> · <a href="https://victorchen96.github.io/auto_research/framework.html">auto_research</a></sub></p>

> The heavy autonomous scientists ([AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw), [AI-Scientist](https://github.com/SakanaAI/AI-Scientist)) match the *breadth* — but ship as **standalone Python products** (Docker, Neo4j, tens of thousands of LOC). The lighter *skills* ([ARS](https://github.com/Imbad0202/academic-research-skills), [Idea2Paper](https://github.com/AgentAlphaAGI/Idea2Paper)) don't run experiments or draw figures. **Nobody else gives you all of it as drop-in Claude Code skills with editable vector figures.**

---

## 🖼️ The Figure Engine

**The capability no other skill suite has.** AI image models produce rasters — but a paper needs editable vector figures.

The figure path chooses the representation that best preserves the source of truth. It does not force
every figure through an image model or a raster-to-vector conversion:

```
semantic contract + source evidence
   ├─ measured values       → reproducible scientific plotting
   ├─ exact structure       → Graphviz / TikZ / domain renderer
   ├─ real observations     → original media + reproducible annotation
   └─ illustrative concept  → bounded candidate search + actual-image review
          └─ approved raster, when needed → DrawAI semantic SVG · PDF · PPTX
```

| What | How | Result |
|---|---|---|
| **Generation** | One direct render or a justified bounded candidate search | Cost and scrutiny scale with uncertainty |
| **Semantics** | Contracted nodes/edges/variables plus actual-image trace checks | Wrong arrows and stale reviews are red gates |
| **Vectorization** | DrawAI full profile with external GPU perception | Editable SVG/PDF/PPTX without local large models |
| **Fallback** | Whole-canvas raster hybrid only after explicit approval | Trade-off is visible, never silent |

<details>
<summary>Connect an external DrawAI model server</summary>

```bash
# In .env on the Codex client:
DRAWAI_REMOTE_BASE_URL=https://drawai-models.example.org
DRAWAI_REMOTE_API_KEY=...  # optional gateway credential

python3 codex/skills/ts-figure-optimize/scripts/remote_runtime.py \
  --report /tmp/drawai-remote-preflight.json
```

SAM3, PaddleOCR, RMBG, CUDA, and their weights stay on the server. HTTPS, a private network, or a
loopback SSH tunnel is required; the raw unauthenticated DrawAI model port must not be public.
</details>

---

## 🧪 Remote-first Experiment Compute

Formal experiments select their backend before the environment lock. `remote_first` probes the SSH
server, snapshots its Python/CUDA/GPU/dependencies, and locks its target and fingerprint. Local compute
is selected only when that preflight fails and fallback is enabled. Once locked, the backend cannot
change silently; this prevents a remote failure from producing an untracked local duplicate.

```bash
# Fill TS_EXPERIMENT_REMOTE_* in .env, then:
python3 codex/skills/ts-research-lifecycle/scripts/execution_backend.py select \
  --out /path/to/research/environment/selected.environment.json
```

Workspace synchronization excludes credentials, Git metadata, virtual environments, and caches. Every
remote command has server-side and client-side timeouts, start/exit markers, bounded infrastructure
retry, and an explicit `remote_outcome_unknown` stop when duplicate execution cannot be ruled out.

---

<p align="center"><b><i>One spark in. One paper out.</i></b></p>

<p align="center">
  <img src="docs/method.png" width="100%" alt="spark-to-paper-skills method overview">
</p>

---

## 🔬 The Pipeline

One orchestrator (`ts-paper`) routes the input through one research lifecycle and one manuscript
pipeline. Empirical work happens before result-bearing prose, not as a post-writing repair stage:

```
                         ┌──────────────── optional upstream ────────────────┐
 [corpus.jsonl] ─▶ ts-kg-build ─▶ kg/         (research-pattern KG)
 [raw idea]     ─▶ ts-idea2story ─▶ story + citation seed
                         └──────────────────────────────────────────────────┘
                                                │
 [idea / proposal / proposal + real results] ─▶ ts-paper
                                                │
   ground Idea + related work + benchmark search
   freeze claims/contract after model review + measured feasibility probe
   proposal profile ────────────────────────────┐
   empirical profile ─▶ lock code/env           │
                       reproduce + verify       │
                       pilot + bounded runs     │
                       diagnose + evolve Idea   │
                       reconcile claims/facts  │
                                                │
   ts-paper-plan ─▶ cite ─▶ data binding ─▶ write ─▶ refine ─▶ review ─▶ figure ─▶ latex
```

<details>
<summary><b>Stage 0 — Input routing</b></summary>
<br>

| Class | What was dropped | Route | `results_mode` |
|---|---|---|---|
| **(a) bare idea** | one line, no method/eval structure | `ts-idea2story` → plan | `proposal` |
| **(b) proposal** | problem + method + eval, no measured results | plan (proposal) | `proposal` |
| **(c) proposal + REAL results** | measured numbers or attached data file | plan → `ts-paper-data` | `data_aware` |
| **(d) existing `story.json`** | 8-field story from a prior run | plan (skip idea2story) | `proposal` |

</details>

### Two modes, opposite integrity rules

| | **Proposal mode** | **Data-aware mode** |
|---|---|---|
| Findings | Never present unmeasured findings; protocol constants and cited facts remain valid | Report only canonical measured facts, in past tense |
| Guarantee | Claims remain prospective and limitations explicit | Every result binds to raw artifacts, runs, hashes, and aggregation code |

---

## 🎯 Design Philosophy

|     | Principle | Rule |
| :-: | :--- | :--- |
| 🧠 | **Model reasons** | Claude/Codex owns judgment-heavy work: writing, research, critique, review |
| 🛠 | **Code backstops** | Python handles deterministic tasks: linting, assembly, plotting, vectorization |
| 🪶 | **No control plane** | No mandatory app/database/Docker; optional GPU/model/experiment compute connects through explicit external-service or SSH contracts |
| 🏆 | **Quality first** | Verify citations, self-review, run linters, polish before delivery |
| 🔒 | **Integrity always** | Never invent numbers; trace every value to source data; red gates fail the build |

---

## 🛡️ Quality Stack

Four complementary layers — Claude handles judgment, code provides the deterministic backstop.

| # | Layer | What it checks |
|---:|---|---|
| **1** | **Scientific judgment** | Claim validity · protocol fit · implementation meaning · benchmark relevance · limitations |
| **2** | **Evidence provenance** | Idea/contract versions · repository/environment locks · run lineage · canonical result facts |
| **3** | **Exact gates** | Schemas · hashes · citation keys · result bindings · artifact identity · LaTeX compilation |
| **4** | **Risk-proportional review** | Whole-manuscript primary review · independent confirmation where consequential · delta closure |

```bash
python claude/skills/ts-paper/scripts/run_gates.py <workdir> all     # nonzero exit = NOT done
```

---

## 📐 Template-Agnostic

Write to **whatever venue you pick** — content quality is invariant.

| Template | Venue | Style |
|---|---|---|
| `ts_iieta` | Traitement du Signal | Two-column, numeric citations |
| `neurips` | NeurIPS (community) | Single-column, author-year |
| `neurips_official` | NeurIPS 2025 (official .sty) | Single-column, official formatting |

**Add a venue** by dropping a `templates/<name>/` dir with `template.json` + LaTeX assets — no code changes.

---

## 🧩 The Skills

14 skill folders; all active.

| Skill | Stage | Role |
|---|---|---|
| **`ts-paper`** | orchestrator | Routes input (idea / proposal / data) and drives the chain |
| `ts-idea2story` | upstream | Raw idea → structured research story + citation seed |
| `ts-kg-build` | upstream (opt.) | Corpus → research-pattern knowledge graph for recall |
| `ts-paper-plan` | 1 | Stable research state → venue-grounded `blueprint.json` |
| `ts-paper-cite` | 2 | Real bibliography sized by claim coverage, with metadata and cite-key verification |
| `ts-paper-write` | 3 | Draft evidence-bound LaTeX sections coherently |
| `ts-paper-refine` | 4 | Right-size + de-AI scrub + logic self-check |
| `ts-paper-review` | 5 | Adversarial peer-review hardening |
| `ts-paper-figure` | 6 | Truthful renderer routing, adaptive search, and actual-image review |
| `ts-paper-data` | 6 (data) | Data-aware mode: real results → filled tables + plots |
| `ts-figure-optimize` | 6 (vector) | Raster → semantic SVG/PDF/PPTX via DrawAI full-quality reconstruction |
| `ts-paper-latex` | 7 | Assemble + compile the final PDF |
| `ts-research-lifecycle` | Core | Versioned Ideas, claims, contracts, gates, provenance, invalidation, and revalidation |
| `ts-paper-experiment` | Empirical | Reproduce baselines, verify code/protocols, run bounded iterations, diagnose mechanisms |

---

## 🚀 Quick Start

### 1 · Install

The repository now ships **two parallel, quality-equivalent distributions**:

- Claude Code: `claude/.claude-plugin/` + `claude/skills/` tree (original implementation, moved intact).
- Codex: `codex/.codex-plugin/` + `codex/skills/` tree (Codex-native orchestration and UI metadata).

**Claude Code plugin**

```bash
git clone https://github.com/Albus-White/spark-to-paper-skills.git
claude --plugin-dir ./spark-to-paper-skills/claude
```

The Claude plugin root is `spark-to-paper-skills/claude`. Standalone install:

```bash
for skill in spark-to-paper-skills/claude/skills/ts-*; do
  rsync -a --delete "$skill/" "$HOME/.claude/skills/$(basename "$skill")/"
done
```

**Codex plugin / standalone skills**

Load the repository as a local Codex plugin from the `codex/` plugin root via `codex/.codex-plugin/plugin.json`, or replace existing
standalone skills with the Codex-native copies:

```bash
for skill in spark-to-paper-skills/codex/skills/ts-*; do
  rsync -a --delete "$skill/" "${CODEX_HOME:-$HOME/.codex}/skills/$(basename "$skill")/"
done
```

Restart the host or open a new session after installation. See `codex/README.md` for Codex details.

Pull the repository, then recopy the matching `claude/skills/` or `codex/skills/` tree when upgrading.

### 2 · (Optional) Configure secrets

| Secret | Variables | When needed |
|---|---|---|
| 🎨 **Figure model** | `TS_FIG_API_KEY`, `TS_FIG_BASE_URL`, `TS_FIG_MODEL` | Render schematics with an image model |
| 👁️ **Vision QA** | `OPENAI_API_KEY`, `VISION_MODEL` | Correct figure text, per-region defect comparison |
| 🧠 **Embeddings** | `TS_EMBED_*` | KG-grounded recall (optional, graceful degradation) |
| 📦 **DrawAI** | `HF_TOKEN` | Download gated SAM3 weights once |

Copy `.env.example` → `.env` and fill in only what you use.

### 3 · Ask Claude or Codex

```
Use $ts-paper on this proposal.
```

Paste your idea, proposal, or proposal + data. The orchestrator auto-routes, runs the chain, and delivers a compiled paper with page count, sections, references, review outcome, and editable vector figures.

---

## ⚙️ Requirements

- **Claude Code or Codex** (matching plugin distribution included)
- **Python 3.10+** with the matching distribution's `ts-figure-optimize/requirements.txt`
- **LaTeX** (`latexmk` + a TeX distribution) for compilation
- *Optional:* external DrawAI GPU services · image-model endpoint · LibreOffice

---

## 🙋 FAQ

<details>
<summary><b>Will it invent results to make the paper look complete?</b></summary>
<br>
No. Proposal mode may contain protocol constants and cited facts, but cannot present measured findings.
In data-aware mode, every reported result is bound to a canonical fact with raw sources, run IDs,
hashes, and aggregation code; semantic review then checks whether the number supports the claim.
</details>

<details>
<summary><b>How is this different from AutoResearchClaw / AI-Scientist / Kosmos?</b></summary>
<br>
The heavy autonomous scientists match the breadth but ship as standalone Python products (Docker, Neo4j, tens of thousands of LOC). This suite instead ships as parallel Claude Code and Codex skills with a shared evidence lifecycle and editable-vector figure capability.
</details>

<details>
<summary><b>Do I need GPUs or the heavy DrawAI runtime?</b></summary>
<br>
Only for raster reconstruction or free-form raster figures. Born-vector and domain-native figures skip
DrawAI; a paper with no necessary figures skips the figure stage entirely.
</details>

<details>
<summary><b>Can I use a venue that isn't bundled?</b></summary>
<br>
Yes — drop a <code>templates/&lt;name&gt;/</code> directory with <code>template.json</code> + LaTeX assets. No code changes.
</details>

---

## ✅ Definition of Done

The active profile reaches its legal release phase; scientific judgments and scoped approvals bind the
current evidence; every reported result traces to canonical facts; citations resolve; the selected
venue template compiles without LaTeX errors; each figure preserves its declared source of truth and
reviewed hash; limitations remain visible; and `run_gates.py <workdir> all` exits zero.

---

## 🙏 Acknowledgments

Inspired by:

- 🔬 [AI-Scientist](https://github.com/SakanaAI/AI-Scientist) (Sakana AI) — Automated research pioneer
- 🦞 [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw) (AIMING Lab) — 23-stage autonomous research pipeline
- 📚 [academic-research-skills](https://github.com/imbad0202/academic-research-skills) (Imbad0202) — Claude Code research skill suite
- 🧠 [autoresearch](https://github.com/karpathy/autoresearch) (Andrej Karpathy) — End-to-end research automation
- 🎨 [DrawAI](https://github.com/DrawAI) — Figure vectorization engine (vendored)

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
  <sub>Built on <a href="https://docs.anthropic.com/en/docs/agents-and-tools/claude-code">Claude Code</a> · Figure engine vendored from DrawAI · <a href="LICENSE">MIT License</a></sub>
</p>
