# Workflow

```text
Input image (PNG/JPG)
  → normalize (DrawAI input_normalized)
  → DrawAI structural decomposition (SAM3: arrow/border/content_box/grid/icon/picture)
  → OCR + Box IR (PaddleOCR + box_ir merge + svg_template_ir)
  → classify elements (run0 LLM element analysis: svg_self_draw vs crop vs crop_nobg)
  → first SVG/PPTX reconstruction (DrawAI staged SVG gen + native DrawingML export)   [Round 0]
  → render SVG and PPTX
  → global similarity analysis (combined score)
  → region-level similarity analysis (Box IR panels)
  → identify worst regions + diagnose (text/geometry/connector/formula/color/raster)
  → targeted repair (guided global re-generation; best-of-round selection)             [Round 1..N]
  → rerender → recompute similarity → repeat until quality gate passes or budget hit
  → user review (mandatory)
  → final output
```

## Round plan
- **Round 0** — DrawAI first reconstruction (its own internal multi-round critic runs inside this).
- **Round 1** — global layout & missing-object repair.
- **Round 2** — text & formula repair.
- **Round 3** — connector & geometry repair.
- **Round 4+** — worst-region targeted repair.

Default max **10** rounds (`--max-rounds`). Each round records: global scores before/after, per-region
scores before/after, modified/repaired files, regressions, and the reason to continue or stop
(`comparisons/score_history.json`, `reports/ITERATION_HISTORY.md`).

Because DrawAI generates the whole figure at once, the orchestrator implements repair as guided
re-generation + measurement-gated best-of-round selection with a regression check, not literal
per-region patching (see `local_repair_strategy.md`).

## Output layout (`runs/<run_name>/`)
```text
source/source.png            preserved original
drawai/                      raw DrawAI run dir + copied reports
ir/box_ir.json, regions.json, ocr_boxes.json
svg/semantic.svg, rendered_svg.png
pptx/editable.pptx, rendered_pptx.png
pdf/publication_figure.pdf
formulas/formula_001.{tex,svg,json}
comparisons/global_diff.png, region_diffs/, score_history.json, *_round*.json
reports/RECONSTRUCTION_REPORT.md, TEXT_VERIFICATION_REPORT.md, FORMULA_VERIFICATION_REPORT.md,
        PPTX_EDITABILITY_REPORT.md, ITERATION_HISTORY.md
final/editable.pptx, semantic.svg, publication_figure.pdf
status.json
```
