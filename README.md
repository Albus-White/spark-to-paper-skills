# Auto-Research-PaperGenSkill

A [Claude Code](https://docs.claude.com/en/docs/claude-code) **skill suite** that turns whatever you
drop in — a one-line research idea, a full proposal, or a proposal **with real experimental results** —
into a publication-format paper (LaTeX → compiled PDF). Template-agnostic.

The model does the reasoning, writing, literature search, vision-based figure critique, and self-review;
small Python scripts do only the irreducible parts (deterministic linters, LaTeX assembly, image
generation, embeddings/clustering, matplotlib plotting).

## Install
Copy the skill folders into a Claude Code skills directory:
- **Per-project:** `cp -r */ <your-project>/.claude/skills/`
- **Global:** `cp -r */ ~/.claude/skills/`

Then ask Claude to run **`ts-paper`** with your input.

## Skills
| skill | role |
|---|---|
| `ts-paper` | orchestrator + input router (idea / proposal / proposal+data) |
| `ts-idea2story` | raw idea → structured research story / proposal |
| `ts-kg-build` | (optional) build a research-pattern knowledge graph for recall |
| `ts-paper-plan` | proposal → structured blueprint |
| `ts-paper-cite` | build a real, complete bibliography (WebSearch + Crossref) |
| `ts-paper-write` | draft all sections as LaTeX |
| `ts-paper-refine` | holistic right-sizing + de-AI + logic self-check |
| `ts-paper-review` | optional adversarial peer-review hardening pass |
| `ts-paper-figure` | figure routing: matplotlib (precise) / image model (free-form) + vision critique |
| `ts-paper-data` | data-aware mode: real results → filled tables + plots |
| `ts-paper-vector` | ⛔ **DISABLED** (retired figure vectorizer; superseded by `ts-figure-optimize`) |
| `ts-paper-latex` | assemble + compile the final PDF |
| `ts-figure-optimize` | **sole figure vectorizer**: image-model raster → editable SVG/PDF (+PPTX) via the **full DrawAI engine** (SAM3+OCR+Codex) + measured loop; also provides the editable-vector **gate** `check_vector_pdf.py` |

## Downstream handoff — experiments + repair (Stage 8, separate project)
After the suite produces a complete first-draft paper (proposal mode, no real results), an **optional
Stage 8** hands the draft to **AutoPaperFactory** (`/mnt/data0/LX_Bench/CS/AutoPaperFactory`, or
`$AUTOPAPERFACTORY_ROOT`) — its **`sci-paper-repair`** skill refines the article, **runs feasible
experiments** (real data/code only, never fabricated), rewrites the experiment section, and fills the
result tables. Run `python ts-paper/scripts/handoff_to_experiments.py --workdir <ts_paper_run>` after
Stage 7, then invoke `sci-paper-repair` inside the factory. (The main schematic is vectorized at Stage 6,
before experiments; results plots added in Stage 8 are matplotlib born-vector.)

## Templates
Bundled venues live under `ts-paper/templates/` (e.g. `ts_iieta`, `neurips`). Add your own by dropping a
`templates/<name>/` dir — no code changes; every script reads `template.json`.

## Integrity (machine-checked)
Proposal mode never fabricates numbers; data-aware mode requires every number to trace to your real data;
citations must be real and complete. Linters **fail the build** on a violation.
