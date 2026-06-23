---
name: ts-figure-optimize
description: >
  The suite's SOLE figure vectorizer: turn ONE raster scientific figure (a PNG/JPG, e.g. a
  gpt-image-2 schematic) into an editable, publication-ready figure via DrawAI's **key-free HYBRID** —
  local perception (SAM3 region detection + PaddleOCR + Box-IR layout, no account) then a deterministic
  hybrid build that keeps the approved render **pixel-exact** (a whole-canvas raster) and lays an
  **editable <text> overlay** on top (~0.91 SSIM), exported as a self-contained SVG + vector PDF + an
  editable PPTX. The render's full richness is preserved EXACTLY (it IS the approved image) while every
  label becomes editable. The original raster is always kept. Hybrid is the ONLY mode used: there is no
  Codex full-vector redraw (legacy/off — it needs an account, and a redraw of a dense figure loses
  fidelity) and no Claude-redraw fallback. If this runtime cannot be provisioned, the caller keeps the
  approved PNG as-is — never a lossy redraw. Independent of the paper pipeline — give it any figure image.
---

# ts-figure-optimize — raster figure → editable HYBRID, the key-free DrawAI path

This is the suite's **only** figure vectorizer, and it runs DrawAI's **key-free HYBRID**: SAM3 segments
the layout and PaddleOCR reads the text **locally** (on a GPU box, no Claude/Codex account), then a
deterministic build keeps the approved render **pixel-exact** and lays an **editable `<text>` overlay**
on top — exported as a self-contained SVG + vector PDF + editable PPTX (~0.91 SSIM; ~63 editable text
boxes on the test figure). The figure's richness is preserved EXACTLY (the graphics ARE the approved
render) while every label becomes editable.

**Hybrid is the ONLY mode used.** The engine also contains a legacy Codex full-vector redraw
(`run_reconstruction.py`) — it is **off**: it needs an LLM account, and a full redraw of a dense figure
measurably loses fidelity vs the exact render (~0.67 vs 0.91 SSIM). So the suite rule is **HYBRID, or
else keep the approved PNG — never redraw.**

It does NOT just embed the bitmap into a slide: it reads every label and re-lays it as editable text
over the exact render. The genuinely complex graphics stay as the render raster (that is the point —
pixel-exact richness), not a lossy trace.

## When to use
You have a single raster figure (e.g. an approved gpt-image schematic) and want it editable without
losing any richness. Input: a PNG/JPG path. If the DrawAI runtime can't be provisioned, the caller
keeps the approved PNG as-is — there is no lightweight redraw fallback.

## Absorbed dependency: DrawAI is VENDORED here (manual updates)
The DrawAI **source (~5 MB, includes the MPS guard fix)** is vendored inside this skill at
**`engine/`** — so the skill is self-contained for code and needs no separate DrawAI checkout. The
heavy **runtime is NOT vendored**: ~4 GB model weights (SAM3/PaddleOCR/RMBG) + a runtime venv are
provisioned on deploy by `scripts/setup_drawai.py` (below). The orchestrator points at `engine/` by
default (override with `--drawai-repo`/`DRAWAI_REPO`). **Updates are manual** — re-vendor `engine/`
from upstream DrawAI yourself when you want a newer version (see `references/drawai_adapter.md`; the
vendored commit is recorded in `engine/ENGINE_VERSION.txt`).

## Deploy the runtime (once per machine): `scripts/setup_drawai.py`
The model runtime (SAM3 / PaddleOCR / RMBG weights + venv, ~8 GB) is deployed **inside this skill** at
`ts-figure-optimize/engine/.local/drawai_runtime/` (gitignored — code is in git, the multi-GB weights are
provisioned on disk under the skill, never committed). It is **self-contained under spark-to-paper-skills**,
not borrowed from any outer checkout. **`run_hybrid.py` AUTO-DEPLOYS it before running** if it's missing,
so you normally don't call setup manually — but you can:
```
python scripts/setup_drawai.py --device cpu            # download ~4GB models + build the runtime venv (under the skill)
python scripts/setup_drawai.py --check-only            # verify the runtime is ready (drawai doctor)
python scripts/setup_drawai.py --reuse-runtime <path>  # reuse an existing .local/drawai_runtime (skip download)
```
It tries DrawAI's official `setup local` first, and falls back to the validated manual install (paddle
from PyPI, CPU torch, openai-codex via pypi.org/simple, editable engine + runtime deps, sam3, triton)
when the official bootstrap can't reach its indexes. (Codex auth is needed ONLY for the legacy pure-A
redraw — the **HYBRID path below is key-free**.)

**✅ VERIFIED key-free GPU recipe — ModelScope, NO HF token (validated 2026-06-23 on a 6×A40 box).** The
HYBRID path needs **no LLM key at all**; models come from **ModelScope** (default `--source modelscope`,
which is NOT gated — this is why no HF_TOKEN is required):
1. `pip install uv` (any env), then `python scripts/setup_drawai.py --device gpu` → builds the runtime venv
   (Python 3.12, torch+cu12x, paddlepaddle CPU) and downloads `sam3.pt` (~3.3 GB) / RMBG-2.0 / PP-OCRv5 from
   ModelScope. **No HF_TOKEN, no Codex login for the hybrid.** (~13 GB on disk under `engine/.local/`.)
2. **Known fixes (now baked into the scripts; apply by hand only if you re-vendor an older engine):**
   - **PaddleOCR ModelScope download can be 0-byte** (`PaddlePaddle/PP-OCRv5_*` is empty on ModelScope). If
     `<runtime>/models/paddlex/official_models/PP-OCRv5_server_{det,rec}/inference.pdiparams` are missing,
     copy them from PaddleOCR's standard cache (it fetches them on first use):
     `cp -rn ~/.paddlex/official_models/PP-OCRv5_server_{det,rec} <runtime>/models/paddlex/official_models/`.
   - **Device:** the pinned paddle wheel is CPU-only — on a GPU box use `--device gpu`; `run_hybrid.py` now
     maps SAM3/RMBG→`cuda` and paddle→`cpu` automatically.
   - **Host build deps:** `pip install python-pptx cairosvg numpy Pillow` into the interpreter that runs
     `build_hybrid_pptx.py` (it uses the HOST python, not the runtime venv).
   - **`drawai doctor` flags Chrome + Codex auth missing — IGNORE for the hybrid** (those are only for the
     legacy pure-A redraw; the hybrid uses cairosvg + no LLM).
3. Run key-free: `python scripts/run_hybrid.py --image fig.png --run-name <n> --device gpu --no-text-gpt`
   (`--no-text-gpt` skips the only optional LLM step — GPT text-correction; have **Claude** do that
   per-region text correction instead if you want OCR subscript/case fixes, keeping the whole flow key-free).

## Prerequisites (verify first)
1. DrawAI runtime ready: `python scripts/setup_drawai.py --check-only` → `doctor: OK`.
   If not: `python scripts/setup_drawai.py --device cpu` (provisions the vendored `engine/`:
   downloads SAM3/PaddleOCR/RMBG ~4 GB + builds the runtime venv). The DrawAI source is already
   vendored at `engine/` (no separate checkout needed).
2. Codex/OpenAI auth present (`~/.codex/auth.json` or `OPENAI_API_KEY`) — DrawAI's SVG/run0 agent
   (gpt-5.5) needs it. (Measured comparison showed Codex/gpt-5.5 outperforms a Claude-CLI agent for
   this generation task, so Codex is the engine here.)
3. A real PPTX renderer (LibreOffice `soffice`) enables the PPTX render gate; if absent the PPTX
   render is `NOT_RUN` and the run cannot auto-PASS (still produces SVG/PPTX/PDF).

## The orchestration (DEFAULT): `scripts/run_hybrid.py` — Codex-free preprocessing + HYBRID export
This is the production path. It was validated head-to-head against pure-A on the same fresh run:
**HYBRID ≈ 0.91 SSIM vs pure-A ≈ 0.67**, and it is **much cheaper** because it SKIPS the Codex vector
redraw entirely. One figure:
```bash
python scripts/run_hybrid.py --image <figure.png> --run-name <name> [--runs-root runs] [--device cpu] \
    [--runtime-root .local/drawai_runtime] [--no-text-gpt]
```
Flow:
1. DrawAI **dry-run** scaffold (config + run dir, no models).
2. **Codex-FREE IR** stages in the runtime venv (`run_preprocess_ir.py`: prepare → SAM3 → OCR → Box-IR).
3. **GPT per-region text correction** (`verify_text_gpt.py`) — fixes OCR-dropped subscripts/case.
4. **HYBRID build** (`build_hybrid_pptx.py`): pixel-exact graphics raster + editable text boxes (real
   sub/superscripts) → `final/editable_hybrid.{pptx,pdf,svg}`.
5. Editability verification.
Output under `runs/<name>/`: `source/source.png`, `ir/` (box_ir + ocr), `final/editable_hybrid.*`,
`comparisons/` (corrected_texts.json, hybrid_report.json, pptx_hybrid.json).
- **Honest ceiling:** only TEXT is editable; graphics stay raster. ~0.90 SSIM (re-typed text can't beat
  font/AA/sub-pixel). For a fully-vector-editable figure instead, use the LEGACY pure-A flow below.

## LEGACY (isolated, NOT default): pure-A vector redraw — `scripts/run_reconstruction.py`
Kept for the rare case where you need **every element (incl. graphics) as editable vector**, accepting the
lower fidelity (~0.67–0.8) and the Codex cost. It runs the full DrawAI Codex redraw + measured loop. **Do
NOT use it as the default** — the hybrid flow above is better and cheaper.
```bash
python scripts/run_reconstruction.py --image <fig.png> --run-name <name> --device cpu --max-rounds 10 [--no-repair]
```
It drives DrawAI's full pipeline (normalize → SAM3 → OCR → Box-IR → classify → **Codex SVG** → validate →
native PPTX), then a measured best-of-rounds loop (SSIM/region/OCR/formula + RASTER_BACKGROUND_MATCH /
WAVEFORM_STYLE gates). Output: `svg/semantic.svg`, `pptx/editable.pptx`, `pdf/publication_figure.pdf`.

## Stage R — structural-defect refinement (精修, model-judged, iterate a few rounds)
After the base reconstruction, run a targeted refinement loop whose goal is **structural/logical
correctness**, NOT pixel-identity. **Fonts, anti-aliasing, and exact colours MAY differ** (that gap is
accepted and unfixable for an editable redraw). What MUST be fixed: **wrong/missing/extra arrows or
reversed data-flow, misalignment, wrong relative positions of panels/icons/pictures, inconsistent /
wrong / missing / duplicated icons, and any incoherence vs the original.**

Loop (Claude is the judge+editor; the scripts are guides — edits are on the SVG master = the PPTX
shapes 1:1, then the PPTX is re-exported):
```
1. render the current SVG  (scripts/render_svg.py)
2. PER-REGION VISION COMPARE (the core — metrics CANNOT see semantic defects):
   AUTOMATED: scripts/vision_region_diff.py sends each region's [SOURCE | RENDER] pair (upscaled) to a
   vision model (gpt-5.5; OpenAI-compatible, key from ~/.codex/auth.json) and writes a structured
   comparisons/vision_defects.json with the defect categories below. Use a GRID (`--grid 3/4`) so cells
   span ADJACENT elements (inter-element overlaps like matrix-vs-colourbar are only visible across a
   boundary; tight per-element Box-IR crops miss them). Do NOT pass temperature (gpt-5.5 rejects it).
   MANUAL fallback: scripts/region_crops.py emits the same pairs for the skill executor (Claude) to READ
   and emit the same JSON by hand. Either way, judge each region against this SEMANTIC checklist
   (ignore font/AA/colour-shade):
     - text OVERFLOWING / spilling outside its box or panel
     - any element OVERLAPPING/colliding with another (arrow over a figure; matrix over its colourbar)
     - WRONG ICON semantics (a cycle/loop ↻ drawn as a straight arrow; ↔ drawn as →; garbled icon)
     - MISALIGNED / unevenly-sized repeated shapes (encoder bars, rows, badges)
     - MISSING / DUPLICATED / wrongly-POSITIONED elements vs source
   (scripts/diff_overlay.py heatmap + scripts/compare_regions.py SSIM only say WHERE to look first.)
3. Build the defect list from the per-region vision pass (NOT from SSIM — SSIM misses all of the above).
4. FIX — two strategies per defect:
   (a) VECTOR surgical edit (preferred, stays editable): redirect/add/remove an arrow, add a marker-end
       arrowhead, move/resize a box so text fits, shift the colourbar/label off the matrix, align the bars.
   (b) RASTER-CROP-EMBED fallback (when a shape/icon is too complex to redraw faithfully — e.g. an
       intricate loop ↻ glyph, a detailed sub-figure): `scripts/crop_region.py --source <orig> --bbox …
       --out asset.png --nobg` crops that ONE element from the ORIGINAL image and removes its background,
       then embed it as a coordinated sub-region `<image>` at the right position. It MUST pass
       `RASTER_BACKGROUND_MATCH` (transparent / panel-matched, no visible rectangle) so it blends. Use for
       SUB-regions only, never the whole canvas.
   Do not regenerate the whole figure.
5. re-render; re-view that region's pair: defect gone AND no new overlap/overflow introduced AND untouched
   regions unchanged. Keep the edit only if its region's defect list shrank with no regression.
6. repeat per region / per round until the per-region semantic-defect list is EMPTY (or budget).
```
**Acceptance = the per-region semantic-defect checklist is empty** (report any remaining as author-review),
NOT a pixel-SSIM threshold — SSIM does not move for these fixes (a hat, a redirected arrow, a separated
colourbar barely change pixels), which is exactly why the vision pass is mandatory. Pixel SSIM is only a coarse "where to look" guide — a faithful redraw tops out
around ~0.8x vs the original raster because of accepted font/AA/colour differences. Re-export the PPTX
from the refined SVG when done (`drawai --from-stage svg_to_ppt_exported`).

## High-fidelity HYBRID export (`scripts/build_hybrid_pptx.py`) — when visual fidelity matters most
An alternative to the LLM redraw that reaches **~0.90 SSIM** (the editable-redraw ceiling) **cheaply and
deterministically (no Codex)**: keep the source figure's GRAPHICS as a **pixel-exact raster with the text
removed**, and re-create every OCR'd text run as a **genuinely editable PPTX text box** (and selectable
PDF/SVG text). For "faithful + editable text" this beats the full vector redraw (~0.67–0.8) at near-zero
cost and with **zero text doubling/offset**.
```
python scripts/build_hybrid_pptx.py --source <run>/source/source.png \
    --ocr <run>/ir/ocr_boxes.json --box-ir <run>/ir/box_ir.json \
    --out-pptx <run>/final/editable_hybrid.pptx --out-pdf <run>/final/editable_hybrid.pdf \
    --out-svg <run>/final/editable_hybrid.svg --report <run>/comparisons/hybrid_report.json
```
- **Resolution-adaptive:** OCR/box bboxes are scaled from the box_ir CANVAS space to the actual SOURCE
  pixel space at runtime (`sx=W_src/canvas.width, sy=H_src/canvas.height`). **This scale is mandatory** —
  skipping it shifts/oversizes the text and is exactly what causes duplication/offset. Works at any input
  resolution as long as `ocr_boxes.json` + `box_ir.json` come from the same DrawAI run.
- **How:** ink-mask erase (`ink = lum<bg_lum-22 OR colour-dist>60`) repaints text pixels with the local
  bg; text colour from the box's CENTRAL vertical band (0.22–0.78, darkest 30%); horizontal position from
  the actual ink start, size fitted to the ink WIDTH (capped by box height) so loose OCR boxes don't
  oversize small labels; sub/superscripts are rendered as real baseline-shifted runs (font-independent,
  truly editable, no missing-glyph "tofu").
- **GPT text correction (recommended pre-step):** PaddleOCR drops subscripts and mis-cases math tokens
  (`onset Ot`, `Za`, `Zsa`). Run `scripts/verify_text_gpt.py` FIRST — it sends each text region's source
  crop to a vision model and returns the exact text (case + Unicode sub/superscripts), written to
  `corrected_texts.json`; pass it to `build_hybrid_pptx.py --text-overrides corrected_texts.json`. This is
  TARGETED per-region transcription (reliable), unlike the stochastic whole-figure defect detector.
  ```
  python scripts/verify_text_gpt.py --source <run>/source/source.png --ocr <run>/ir/ocr_boxes.json \
      --box-ir <run>/ir/box_ir.json --out <run>/comparisons/corrected_texts.json
  ```
- **Trade-off (honest):** only TEXT is editable; graphics stay raster (not vector-editable). **0.95–0.99
  is NOT reachable with re-typed text** (font/AA/sub-pixel) — that requires keeping the original text
  pixels (then text is display-faithful but not freely editable). ~0.90 clean is the honest ceiling here.

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
**Orchestrators:** `run_hybrid.py` (DEFAULT — Codex-free IR + hybrid export) and `run_preprocess_ir.py`
(its Codex-free IR step, runs in the runtime venv); `run_reconstruction.py` is the LEGACY pure-A entry.
`render_svg.py` (SVG→PNG), `render_pptx.py` (LibreOffice→PNG or NOT_RUN), `measure_similarity.py`,
`compare_regions.py`, `verify_text_and_formulas.py`, `verify_pptx_editability.py`,
`fix_raster_backgrounds.py` (RASTER_BACKGROUND_MATCH), `verify_waveforms.py` + `waveform_primitive.py`
(WAVEFORM_STYLE), `diff_overlay.py` (Stage R heatmap/worst-cells), `region_crops.py` (Stage R region pairs), `vision_region_diff.py` (Stage R automated gpt-vision per-region defect detector),
`build_hybrid_pptx.py` (high-fidelity HYBRID export: exact graphics raster + editable text boxes w/ real sub/superscripts, ~0.90 SSIM, no Codex — see section above),
`verify_text_gpt.py` (GPT-vision per-region text correction: fixes OCR-dropped subscripts/case → corrected_texts.json for `build_hybrid_pptx.py --text-overrides`),
`build_report.py`, and `export_paper_figure.py` (map a finished run into the ts-paper
figure contract: self-contained `figures/<label>.svg` + `.pdf` + kept `.png`).

## Use inside the ts-paper suite (figure stage 6, step 5b)
`ts-paper-figure` calls this as the **sole** vectorizer for free-form image-model schematics: run the
**hybrid** on the approved PNG (`run_hybrid.py --no-text-gpt`), then `export_paper_figure.py` to drop the
self-contained `figures/<label>.svg` + `.pdf` (+ kept `.png`) into `figures/`, then lint via the shared
gate (`scripts/check_vector_pdf.py lint --type <type> --render-check`). If the DrawAI runtime can't be
provisioned, `ts-paper-figure` keeps the approved PNG as-is — there is **NO redraw fallback**. The main
method-overview schematic is results-independent → vectorize it ONCE at the proposal/first-draft figure
stage, never deferred to a post-experiment re-run.

## References
`references/workflow.md`, `references/quality_metrics.md`, `references/text_and_formula_rules.md`,
`references/local_repair_strategy.md`, `references/drawai_adapter.md`, `references/failure_handling.md`.

## Hard rules
- **Run the FULL measured multi-round repair by default** — do **not** reduce quality to save time. Use
  `run_reconstruction.py` with repair ON and the default `--max-rounds` (the measured best-of-rounds
  SSIM/region loop + Stage-R structural-defect pass); **never** pass `--no-repair` or `--max-rounds 1`
  to cut the loop short unless the user has explicitly opted into a fast/degraded pass. A single-pass
  redraw is acceptable only on explicit user request, and the degradation must be stated.
- Never rasterize ordinary text or keep AI-malformed text; reconstruct it as editable `<text>`.
- Raster assets are tight local crops only (no surrounding text/panel background); no visible
  rectangular boundary (RASTER_BACKGROUND_MATCH must not be FAILED).
- Audio waveforms must be editable bar-style lines, never sine/zigzag/square/polyline/faint placeholders.
- Never fake/round similarity; preserve all intermediate attempts; always keep the original raster.
- Require user approval before finalizing.
