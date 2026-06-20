---
name: ts-figure-optimize
description: >
  Standalone figure-optimization skill: turn ONE raster scientific figure (a PNG/JPG, e.g. a
  gpt-image-2 schematic) into an editable native-shape PPTX + an editable SVG master + a
  publication vector PDF — driving the FULL DrawAI engine (SAM3 region detection + PaddleOCR +
  Box-IR layout + Codex/gpt-5.5 SVG authoring + native DrawingML export), then a strict, MEASURED,
  multi-round visual-similarity refinement loop with raster-background and audio-waveform quality
  gates and mandatory human approval. Simple elements become native vector shapes; only genuinely
  complex elements (skeletons, dense heatmaps, waveforms, photos, textures) stay as tight local
  raster crops. The original raster is always kept. This is the heavy, maximum-fidelity sibling of
  ts-paper-vector (which distills DrawAI into a pure-Claude loop with no external services): use
  ts-figure-optimize when you want DrawAI's real perception+generation stack and have its runtime
  + Codex auth available; use ts-paper-vector when you want a lightweight, services-free Claude pass.
  Independent of the paper pipeline — give it any figure image.
---

# ts-figure-optimize — raster figure → editable vector, the full DrawAI engine

ts-paper-vector distills DrawAI into a pure-Claude loop (Claude is SAM3+OCR+author+critic; one
cairosvg script is the only code). **This skill is the opposite trade-off: it runs the real DrawAI
pipeline** — SAM3 segments the layout, PaddleOCR reads the text, a Codex/gpt-5.5 brain authors the
SVG, DrawAI validates it and exports native PowerPoint DrawingML — and wraps it in a measured
render-and-compare refinement loop. Use it when you want DrawAI-grade fidelity (richer panels,
badges, icons, formula tspans, native PPTX) and can afford the runtime + Codex API.

It does NOT just embed the bitmap into a slide. It decomposes the figure and reconstructs editable
content; only genuinely complex regions remain as locally-cropped, high-resolution raster assets.

## When to use
You have a single raster figure and want an editable PPTX + editable SVG + vector PDF at maximum
fidelity, with measured quality gates. Input: a PNG/JPG path (optionally a target aspect/slide size).
For a lightweight, no-external-services pass, prefer `ts-paper-vector` instead.

## Absorbed dependency: DrawAI (pinned + updatable)
This skill drives DrawAI through a thin, stable surface (its CLI + a base config + on-disk outputs),
so DrawAI stays an independently-updatable dependency — see `references/drawai_adapter.md` for the
pinned commit, the required `local_runtime.py` MPS guard patch, and environment workarounds. Tell the
skill where DrawAI lives with `--drawai-repo <path>` or `DRAWAI_REPO=<path>` (it also searches upward
for `src/drawai`). Do NOT copy DrawAI's source or model caches into this skill.

## Prerequisites (verify first)
1. DrawAI runtime ready: `DRAWAI_REPO=<drawai> uv run --frozen drawai doctor local` → `status: ok`.
   If not: `uv run --frozen drawai setup local` (downloads SAM3/PaddleOCR/RMBG, ~4 GB). See
   `references/drawai_adapter.md`.
2. Codex/OpenAI auth present (`~/.codex/auth.json` or `OPENAI_API_KEY`) — DrawAI's SVG/run0 agent
   (gpt-5.5) needs it. (Measured comparison showed Codex/gpt-5.5 outperforms a Claude-CLI agent for
   this generation task, so Codex is the engine here.)
3. A real PPTX renderer (LibreOffice `soffice`) enables the PPTX render gate; if absent the PPTX
   render is `NOT_RUN` and the run cannot auto-PASS (still produces SVG/PPTX/PDF).

## The only orchestration: `scripts/run_reconstruction.py`
Claude invokes this; it drives DrawAI and the measured loop. One figure:
```bash
DRAWAI_REPO=/path/to/DrawAI python scripts/run_reconstruction.py \
  --image <figure.png> \
  --run-name <name> \
  --runs-root runs \
  --max-rounds 10 \
  --target 0.99 \
  --region-threshold 0.99 \
  --device cpu \
  --transcribe-formulas \
  --slide-size 16:9
```
Everything lands under `runs/<name>/` (layout in `references/workflow.md`): `source/` (original kept),
`ir/` (box_ir + ocr), `svg/semantic.svg` + `rendered_svg.png`, `pptx/editable.pptx`,
`pdf/publication_figure.pdf`, `comparisons/score_history.json`, `reports/*.md`, `final/`.

### Each round
0. DrawAI full reconstruction (normalize → SAM3 → OCR → Box IR → classify → SVG → validate → native PPTX).
1+. If a gate fails: guided global re-generation via `drawai --from-stage svg_generated`, keeping the
   best-scoring round (DrawAI generates the whole figure; "local repair" is selection-based — see
   `references/local_repair_strategy.md`).

After every round: render SVG + PPTX, measure global similarity (SSIM, MS-SSIM, LPIPS if available,
edge IoU, OCR F1, color-hist, object-count, layout IoU → normalized combined score), per-region
similarity from Box-IR panels, text/formula verification, PPTX editability, plus the
`RASTER_BACKGROUND_MATCH` and `WAVEFORM_STYLE` gates.

## Stop conditions (honest — never fake the score)
- **PASS** — combined ≥ target AND all critical regions ≥ region-threshold AND critical-label OCR
  recall == 1.0 AND PPTX genuinely editable AND a real PPTX render exists AND raster/waveform gates
  not FAILED.
- **REVIEW_REQUIRED** — budget exhausted; report the true best score (0.99 is often unreachable for
  dense figures — that is the expected, correct outcome).
- **FAILED** — invalid SVG/PPTX, missing critical content, or unrecoverable pipeline error.

## Mandatory human approval
Even at PASS, show: source, rendered SVG, rendered PPTX, combined score, lowest-scoring regions,
formula verification, remaining raster assets. Do not finalize without explicit approval.

## Helper scripts (Claude calls as needed)
`render_svg.py` (SVG→PNG), `render_pptx.py` (LibreOffice→PNG or NOT_RUN), `measure_similarity.py`,
`compare_regions.py`, `verify_text_and_formulas.py`, `verify_pptx_editability.py`,
`fix_raster_backgrounds.py` (RASTER_BACKGROUND_MATCH), `verify_waveforms.py` + `waveform_primitive.py`
(WAVEFORM_STYLE), `build_report.py`, and `export_paper_figure.py` (map a finished run into the ts-paper
figure contract: self-contained `figures/<label>.svg` + `.pdf` + kept `.png`).

## Use inside the ts-paper suite (figure stage 6, step 5b)
`ts-paper-figure` calls this as the PRIMARY vectorizer for free-form image-model schematics (fallback:
`ts-paper-vector`). Run the orchestrator on the approved PNG, then `export_paper_figure.py` to drop the
result into `figures/`, then lint via the shared gate (`ts-paper-vector/scripts/svg_tools.py lint
--render-check`). The main method-overview schematic is results-independent → vectorize it ONCE at the
proposal/first-draft figure stage, never deferred to a post-experiment re-run.

## References
`references/workflow.md`, `references/quality_metrics.md`, `references/text_and_formula_rules.md`,
`references/local_repair_strategy.md`, `references/drawai_adapter.md`, `references/failure_handling.md`.

## Hard rules
- Never rasterize ordinary text or keep AI-malformed text; reconstruct it as editable `<text>`.
- Raster assets are tight local crops only (no surrounding text/panel background); no visible
  rectangular boundary (RASTER_BACKGROUND_MATCH must not be FAILED).
- Audio waveforms must be editable bar-style lines, never sine/zigzag/square/polyline/faint placeholders.
- Never fake/round similarity; preserve all intermediate attempts; always keep the original raster.
- Require user approval before finalizing.
