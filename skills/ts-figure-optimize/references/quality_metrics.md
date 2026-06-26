# Quality metrics & gates

## Global similarity (after every round)
Computed by `measure_similarity.py` between source / rendered-SVG (/ rendered-PPTX). Multiple metrics,
no single metric trusted:

| metric | meaning | lib |
|---|---|---|
| SSIM | windowed structural similarity | numpy (built in) |
| MS-SSIM | multi-scale SSIM (octaves) | numpy |
| LPIPS-sim | `1/(1+LPIPS)` perceptual | optional `torch`+`lpips`; skipped if absent |
| edge IoU | Sobel edge-map overlap | PIL |
| OCR F1 | source-OCR vs SVG-text token P/R | built in |
| color-hist | cosine of coarse RGB histograms | numpy |
| object-count | min/max of Box-IR vs SVG element counts | built in |
| layout IoU | panel-grid overlap (Box-IR content boxes vs SVG rects) | numpy |

**Combined global similarity** = weighted mean over the metrics actually measured (weights in
`_common.GLOBAL_WEIGHTS`, renormalized to those present). Range 0–1.

**Target:** `combined ≥ 0.99`. This is intentionally strict and frequently unreachable for dense
figures — that is expected. The score is always the real measured value.

LPIPS and MS-SSIM are best-effort: if the library is missing the metric is reported as `null` and
excluded from the combined score (the report states which metrics were used and the weight covered).

## Region similarity (after every round)
`compare_regions.py` splits the figure into Box-IR `content_box`/`grid` regions. Per region: SSIM,
edge IoU, dominant-color delta, local OCR recall, pass flag (`region SSIM ≥ region-threshold`, default
0.99). Critical regions include titles, formulas, main method modules, arrows/connectors, major icons,
labels, and result-bearing diagrams; here they are approximated by panel/grid regions. Worst 5 regions
are emitted to drive repair; per-region diff PNGs go to `comparisons/region_diffs/`.

## PASS / REVIEW_REQUIRED / FAILED
```
PASS  : combined ≥ target
        AND all critical regions ≥ region-threshold
        AND critical-label OCR recall == 1.0
        AND PPTX genuinely editable (native shapes + text, not screenshot)
        AND a REAL PPTX render exists (LibreOffice/PowerPoint)
        AND RASTER_BACKGROUND_MATCH != FAILED
        AND WAVEFORM_STYLE != FAILED
        (formulas always require human review; reported, not auto-blocking)
REVIEW_REQUIRED : max rounds reached without PASS  -> report true best score
FAILED          : invalid SVG/PPTX, missing critical content, unrecoverable failure
```

## PPTX editability gate (`verify_pptx_editability.py`)
Reuses DrawAI's `pptx_inspector` (or a self-contained zip/XML fallback). Fails if: single flattened
screenshot; one full-slide image with no native content; too few native shapes (`<10`); too few native
text runs (`<5`, i.e. text likely rasterized). Reports `shape_tag_count`, `text_run_count`,
`picture_tag_count`, `connector_tag_count`, `is_single_screenshot_like`.

## Raster background match gate (`fix_raster_backgrounds.py`) → `RASTER_BACKGROUND_MATCH`
A cropped local asset must not show a visible rectangular background that differs from its target panel.
For every `<image>` (file or base64 data-URI): detect a uniform/near-uniform crop background (border ring
std ≤ `--uniform-std`), find the target panel fill (smallest filled rect behind the image) and/or sample the
surrounding pixels from the render, and compute the boundary color difference **ΔE (CIE76 Lab)**. If a
uniform crop background mismatches the target beyond `--threshold` (default 12), it is a "visible rectangle".
Repair fixes ONLY that asset, in preference order:
`native vector → transparent raster crop → background-matched raster crop → original rectangle (last resort)`
— flood-filling only edge-connected background pixels (transparent RGBA preferred, else fill with the panel
color), preserving foreground strokes and anti-aliased edges (feathered alpha). Gate:
`PASS` (no visible rectangles, after repair) · `REVIEW_REQUIRED` (flagged but bg not uniform / no target
color to verify) · `FAILED` (a uniform-bg visible rectangle remains). `FAILED` blocks auto-PASS. Assets that
are already transparent at the border pass immediately.

## Audio waveform style gate (`verify_waveforms.py` + `waveform_primitive.py`) → `WAVEFORM_STYLE`
Audio waveforms must be **editable bar-style** vertical lines: repeated narrow bars symmetric above/below a
shared centerline, rounded caps, controlled irregular heights, consistent spacing, compact grouped segments
(`t₁,t₂,…` with equal width/spacing, shared centerline, centered time labels, editable `…` ellipsis), in the
panel accent color, emitted as native SVG `<line>`/PPTX shapes. Forbidden in a waveform/audio context: sine
curves, zigzag, square waves, continuous polylines, generic line-charts, faint placeholders. The classifier
inspects only elements explicitly in a waveform/audio context (so unrelated geometry is never touched). Gate:
`PASS` (bar-style present, no forbidden) · `REVIEW_REQUIRED` (waveform expected from OCR but no bar-style
present) · `FAILED` (forbidden style found). `FAILED` blocks auto-PASS. Repair replaces forbidden
waveform-context elements with the primitive at the same bbox/color (kept only if it does not regress SSIM).

## PPTX render gate (`render_pptx.py`)
A real office renderer is required. If none is found the render is `NOT_RUN`, the SVG preview is **not**
substituted permanently, and the run **cannot auto-PASS** (it can still be `REVIEW_REQUIRED`).

## Honesty contract
- Measure; never invent. Never round 0.94 to 0.99.
- Never hide local failures — worst regions and failed labels are always listed.
- Report the best achieved score; preserve all intermediate attempts (`drawai/`, `comparisons/`).
- Require manual review when the threshold is not reached.
