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
| `ts-paper-vector` | **fallback** figure vectorizer (pure-Claude redraw, no services) + shared editable-vector **gate** (`svg_tools.py`); primary engine is `ts-figure-optimize` |
| `ts-paper-latex` | assemble + compile the final PDF |
| `ts-figure-optimize` | standalone: raster figure → editable PPTX + SVG + vector PDF via the **full DrawAI engine** (SAM3+OCR+Codex) + measured refinement loop; heavy/high-fidelity sibling of `ts-paper-vector` |

## Templates
Bundled venues live under `ts-paper/templates/` (e.g. `ts_iieta`, `neurips`). Add your own by dropping a
`templates/<name>/` dir — no code changes; every script reads `template.json`.

## Integrity (machine-checked)
Proposal mode never fabricates numbers; data-aware mode requires every number to trace to your real data;
citations must be real and complete. Linters **fail the build** on a violation.
