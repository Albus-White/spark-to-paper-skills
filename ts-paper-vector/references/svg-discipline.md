# SVG discipline — the editable-vector profile + the faithfulness checklist

Distilled from DrawAI's two validators (`svg_validation.py`, `scientific_svg_profile.py`) and its
faithfulness prompt. Two jobs: keep the SVG **editable + safe + render-stable** (the profile, gated
by `svg_tools.py lint`), and keep it **faithful to the approved raster** (the checklist, judged by
your vision each round). Quality is your vision's call; the lint only enforces structure.

## 1. The editable-SVG profile (author within this; the lint enforces it)

**Required**
- Root `<svg viewBox="0 0 W H" width="W" height="H">` where `W×H` is the approved PNG's pixel size.
  The `viewBox` aspect must equal the PNG aspect (the lint hard-fails a mismatch — it scales/crops
  the figure in LaTeX otherwise).
- **Every visible label is a real `<text>`/`<tspan>`** — the whole point of "editable". Never
  outline text to `<path>`, never rasterise a label into an `<image>`. (≥1 `<text>` is a hard lint
  rule; the lint also *warns* when there are many `<path>` and almost no `<text>` — a tell that text
  was outlined.)

**Allowed elements**
`svg, defs, g, rect, circle, ellipse, line, polyline, polygon, path, text, tspan, marker,
linearGradient, radialGradient, stop, title, desc`.

**Forbidden** (break editability and/or make the cairosvg render diverge from the final PDF — the
lint errors on these)
`script, style (the CSS element), filter, mask, clipPath, foreignObject, textPath, pattern`;
external/absolute/relative-file `href`/`xlink:href`/`src` (incl. on `<image>`), `url(http…/file…)`,
`@import`, `<!DOCTYPE>`, `<!ENTITY>`. (Internal `url(#id)` refs to your own gradients/markers are fine.
The **inline `style="…"` attribute is allowed**; only the `<style>` *element* is forbidden.)

**The `<image>` escape hatch (allowed, self-contained).** A raster is allowed ONLY as the escape hatch
for an un-vectorizable region, and ONLY as a **`data:` base64 URI** `<image>` — that is the one form the
safe renderer (`unsafe=False`) actually draws (a relative/file/external href renders **blank** with no
error, and the lint hard-errors it as `image_href_not_data`/`external_href`). Use `svg_tools.py crop`,
which emits a ready-to-paste `<image href="data:image/png;base64,…" …>`. Keep raster regions **minimal**:
the lint *warns* on any `<image>` (`has_image`) and warns harder when an `<image>` covers ≥85% of the
canvas (`whole_figure_raster` — acceptable only for a genuinely photographic figure, never for a schematic
you could redraw). A figure with NO `<text>` is a hard `no_text` error **unless** it legitimately contains
an escape-hatch `<image>` (then it is a warning), so a real photo-wrap figure can still pass.

**Text & fonts**
- Math: Unicode glyphs (α β θ ∑ ∇ ×), `baseline-shift="super"|"sub"` for sub/superscripts, `rotate()`
  (or `writing-mode`) for vertical axis text.
- Name a font cairosvg actually has so your compare-render equals the PDF: `font-family="DejaVu
  Sans"` (sans) or `"DejaVu Serif"` (serif). Don't chase a phantom delta from naming "Arial" when
  the renderer substitutes DejaVu.

**Arrows**: draw the line/curve as `line`/`path`, the head as an explicit `<polygon>` (don't rely on
`marker` rendering quirks; explicit polygons are unambiguous and editable).

**Colour**: solid fills or `linear/radialGradient`. Match the source palette; sample real hex with
`svg_tools.py sample` when eyeballing is uncertain (colour drift is a common, avoidable miss).

## 2. The faithfulness checklist (run every compare round; "the image wins")

The approved PNG is the **only** source of truth. Your decomposition notes are a fallback hint and
must yield to what the pixels show. Each round, `Read` the approved PNG and your render and confirm:

- **Canvas/aspect** — same proportions; nothing clipped or padded with dead space.
- **Regions/panels** — every box present, same relative position/size, aligned as in the original;
  **none invented, none dropped**.
- **Text** — every string present and **verbatim** (the paper's exact terms); correct font
  weight/style/size/colour/orientation; rendered as editable `<text>`, not traced.
- **Arrows/connectors** — every one present with the right direction, bend, endpoints, arrowhead,
  stroke weight, and **z-order** (over/under boxes as in the original); none invented.
- **Grids/tables** — exact row/column counts; **no invented lines**, none missing.
- **Palette** — fills/strokes/gradients match the sampled hex.
- **No hallucination, no omission** — if it isn't in the pixels, it isn't in the SVG; if it is in the
  pixels, it is in the SVG.

Stop when you cannot name a material drift (minimum 2 rounds, cap 3). If drift remains at the cap,
use the raster-embed escape hatch for the offending region rather than ship a worse figure.

## 3. Renderer backends (cairosvg is the hard dependency)

`svg_tools.py` uses **cairosvg** (pure-python, installed). Higher-fidelity CLIs exist as documented
fallbacks if you ever need them (neither is required here):
- `rsvg-convert -f png -o out.png in.svg` / `rsvg-convert -f pdf -o out.pdf in.svg`
- `inkscape in.svg --export-type=pdf --export-filename=out.pdf`
Because the profile forbids `filter`/`mask`/`clipPath`/CSS, cairosvg renders the SVG the same way the
PDF will — so the render you compare against the original is what ends up in the paper. If cairosvg is
absent, `svg_tools.py` fails loud (`pip install cairosvg`) rather than degrade.
