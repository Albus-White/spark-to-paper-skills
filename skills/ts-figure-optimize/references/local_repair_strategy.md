# Local repair strategy

## The constraint
DrawAI generates the **whole figure** as one SVG (global generation; no region-scoped patch API). It has
a rich internal critic loop (template → visual-review → ir-refine, or a merged Codex thread that
self-refines several rounds), but there is no public way to ask it to "fix only region X" without
modifying DrawAI source. We do **not** modify DrawAI source for this.

## What this skill does instead (honest)
"Local repair" here = **diagnosis-guided global re-generation + measurement-gated best-of-round
selection + regression check**:

1. After each round, `compare_regions.py` ranks regions by SSIM and lists the worst 5 + failed critical
   regions, with a coarse diagnosis signal (low OCR recall → text; low edge IoU → geometry/connector;
   high color delta → color/asset; formula region → formula).
2. The orchestrator triggers a repair round: `drawai --config <case> --from-stage svg_generated
   --to-stage svg_to_ppt_exported`. DrawAI re-reads the existing Box IR / OCR / asset manifest from disk
   and re-generates the SVG (a fresh pass through its internal critic), then re-exports the PPTX.
3. The full figure is re-measured globally and per-region. The orchestrator **keeps the best-scoring
   round** (`final/` is snapshotted to the best combined score) and the iteration history records whether
   unrelated regions regressed.

## Why not literal per-region patching
True per-region patching would require either (a) compositing independently regenerated region SVGs into
the master — risky for connectors/overlaps and not supported by DrawAI's layout model — or (b) injecting
per-region feedback into DrawAI's generation prompt, which needs DrawAI source changes. Both are out of
scope for a non-invasive skill. Best-of-round selection is the honest, safe approximation and never makes
the figure worse than the best round seen.

## Future upgrade path (documented, not implemented)
- Add a region-feedback file consumed by DrawAI's SVG prompt (small upstream change) to bias the next
  generation toward the worst regions.
- Or post-edit `semantic.svg` directly for isolated text/color fixes (deterministic, region-scoped) and
  re-validate + re-export — feasible for text/color, unsafe for geometry/connectors.

## Visual-quality local repairs (deterministic, region-scoped)
Two repairs ARE genuinely local (they edit only the offending element's SVG group / asset, never unrelated
regions) and run every round on the case SVG before collection, with keep-if-not-regressed (SSIM):

1. **Raster background matching** (`fix_raster_backgrounds.py`): for each `<image>` (file or base64), detect a
   uniform crop background, compare its border color to the target panel fill / surrounding pixels via ΔE
   (CIE76 Lab); if a visible rectangle exists, rewrite ONLY that asset to a transparent RGBA crop (preferred)
   or a panel-fill-matched crop, preserving foreground + anti-aliased edges, and rewrite only that href. The
   PPTX is re-exported from the fixed SVG (`drawai --from-stage svg_to_ppt_exported`) only if the repair is
   kept. Note DrawAI already emits many transparent `_nobg.png` crops, so this mostly catches the residual
   opaque/mismatched cases.
2. **Audio waveform repair** (`verify_waveforms.py` + `waveform_primitive.py`): forbidden waveform-context
   elements (sine path / zigzag / long polyline / faint) are replaced by the bar-style primitive at the same
   bbox and stroke color. Only elements whose own attributes mention a waveform/audio hint are touched; if a
   waveform is expected (from OCR) but none is tagged, the gate is `REVIEW_REQUIRED` and nothing destructive
   happens. Output stays native (editable lines), never a screenshot.

Both are reverted automatically if they regress the figure's SSIM, so they can only help or no-op.

## Diagnosis → action map
| symptom (region metric) | likely cause | repair lever |
|---|---|---|
| low `ocr_recall` | wrong/missing text | re-gen (DrawAI re-reads OCR); supply `--critical-labels` |
| low `edge_iou`, ssim ok-ish | geometry/connector drift | re-gen; manual SVG connector edit |
| high `color_delta` | wrong fill / asset | re-gen; check asset_manifest crop vs vector decision |
| formula region low | formula glyphs | LaTeX fallback (`formulas/`), manual review |
| object-count mismatch | missing/duplicated panel/icon | re-gen; inspect Box IR boxes vs SVG element count |
