---
name: ts-paper-vector
description: >
  Stage 6's vectorization engine — distilled from DrawAI into a Claude-native loop. Turns an
  APPROVED raster paper figure (the image-model schematic that already passed ts-paper-figure's
  vision-critique) into a faithful, EDITABLE vector: Claude looks at the PNG, authors an SVG
  (every label a real <text>, boxes/arrows/curves as vector primitives), a tiny script renders
  SVG→PNG so Claude can visually diff it against the original, Claude refines over ≥2 rounds,
  then the script exports SVG→PDF for the paper. Claude is the brain (no external API — it
  replaces DrawAI's SAM3+OCR+Codex); cairosvg is the only irreducible code. Invoked BY
  ts-paper-figure for image-model figures; matplotlib figures are already born-vector and skip
  this. Absolute rule: the vector must be visually ≥ the approved raster — vectorization must
  NEVER reduce quality. The original PNG is always kept.
---

# ts-paper-vector — make a figure editable, the DrawAI way, distilled into Claude

> **Role since the figure-engine split:** this is now the **FALLBACK** vectorizer (pure-Claude redraw,
> no external services), used when the heavy **`ts-figure-optimize`** engine (real DrawAI runtime +
> Codex) is NOT configured. `ts-paper-figure` step 5b prefers `ts-figure-optimize` for higher fidelity
> and falls back here. **Keep this skill regardless of the split:** `scripts/svg_tools.py` is also the
> suite's shared editable-vector **gate** tool (`run_gates.py` → `svg_tools.py check/lint`), so both the
> primary and fallback paths lint through it.

DrawAI turned a bitmap into an editable SVG with a team of services: **SAM3** segmented the
layout, **PaddleOCR** read the text, and a **Codex/agent "brain"** authored an SVG, which was
rendered and **visually compared to the original**, then edited over a few rounds. Every step
except *rasterising* and *PDF-converting* the SVG is vision + reasoning — which **Claude does
natively**. So the whole system distills to: **Claude is the perception layer (SAM3 + OCR) AND
the SVG author AND the critic; one tiny script (`scripts/svg_tools.py`) is the renderer.**

This skill is **a sub-skill of stage 6 (figure)** — not a new pipeline stage. `ts-paper-figure`
stays the one owner of all figures and **calls this** for each image-model raster figure, after
that figure's PNG has already been approved by the vision-critique loop.

## The only code: `scripts/svg_tools.py`
Claude cannot turn vector markup into pixels or a PDF, so one stdlib+cairosvg script does exactly
that, plus a structural lint (it judges *safety/editability*, never *quality* — quality is your
vision's job):
```
svg_tools.py render --svg X.svg --png-out X.recon.png --width <approved-PNG width>   # SVG→PNG (compare)
svg_tools.py topdf  --svg X.svg --pdf-out X.pdf                                       # SVG→PDF (embed)
svg_tools.py lint   --svg X.svg --canvas WxH --type <FIGURE-SPEC type> [--render-check]  # structural+vector gate
svg_tools.py sample --png X.png --points "x1,y1;x2,y2"                                # hex at points (palette aid)
svg_tools.py crop   --png X.png --box "x,y,w,h" --out crop.png                        # SUB-region raster crop
```
**Always pass `--type`** (the figure's FIGURE-SPEC type, handed down by ts-paper-figure). For a
**vector type** (`architecture, pipeline, framework, concept, schematic, overview, flow, diagram`) the
lint makes a **whole-canvas raster** and a **zero-`<text>` SVG HARD ERRORS** — i.e. you cannot pass the
gate by wrapping the PNG; you must actually redraw. Only `type=photo|qualitative` may use a whole-canvas
raster. (This restores DrawAI's `whole_slide_image`/no-editable-text *violations*, which an earlier
draft had weakened to warnings.)
cairosvg is pure-python (no system Inkscape). If it's missing the script fails loud with a
`pip install cairosvg` hint — it **never** silently degrades to a lossy rasteriser (that would
break the no-quality-loss rule). Everything else — decomposing the PNG, authoring the SVG,
judging fidelity — is **you**, no config.

## When this runs / when it does NOT
- **Runs for image-model (free-form) figures** — architecture / pipeline / framework / qualitative
  schematics that ts-paper-figure rendered with the image model. Input = the **approved**
  `figures/<label>.png`.
- **Skipped for matplotlib (code-precise) figures** — results plots and math/geometry concepts are
  already **born vector**: `plot_style.finalize` writes `figures/<label>.pdf` directly. Re-tracing
  them would only risk quality loss. ts-paper-figure embeds that PDF as-is.

## The loop — decompose → author → render → compare → refine → export
For the approved `figures/<label>.png` (known pixel size `W×H`):

1. **Decompose (you are SAM3 + OCR).** `Read` the approved PNG and write down, in coordinates
   relative to `W×H`:
   - every **region/panel** with an approximate bbox;
   - **every text string, verbatim** (the paper's exact terms) with its position, font weight/style,
     colour, and orientation — missing or paraphrasing a label is the #1 fidelity failure;
   - every **arrow/connector**: endpoints, direction, bend, arrowhead, stroke weight, z-order;
   - the **colour palette** — sample with `svg_tools.py sample` at a few points per region if you
     are unsure of a hex (eyeballed colour drifts);
   - fills / gradients / corner radii.
2. **Author the SVG** (`figures/<label>.svg`): a complete `<svg viewBox="0 0 W H" width="W"
   height="H">` on a **pure-white** background. Follow the **editable-SVG profile** in
   `references/svg-discipline.md`:
   - **Every label is a real `<text>`/`<tspan>`** — never outlined paths, never rasterised text.
     Use Unicode for math, `baseline-shift` for sub/superscripts, `rotate()` for vertical text.
     (Vectorised text is *sharper* than the source pixels — this is a genuine quality **gain**.)
   - Boxes/lines/curves/arrowheads as `rect/line/polyline/polygon/path` (+ `linear/radialGradient`).
     **Arrowheads are explicit polygons.**
   - **Forbidden** (breaks editability and/or makes the render diverge from the PDF): `<script>`,
     `<style>`, `filter`, `mask`, `clipPath`, `foreignObject`, `textPath`, `pattern`, an `<image>` with
     an external/absolute/relative-file href, `<!DOCTYPE>`/`<!ENTITY>`. **The ONLY allowed raster is the
     `data:` base64 `<image>` escape hatch** (see the quality-gate section) — prefer pure vector; reach
     for it only for a genuinely un-vectorisable region.
   - Name fonts cairosvg actually has (`DejaVu Sans` for sans, `DejaVu Serif` for serif) so what
     you compare equals what the PDF shows.
3. **Render** `svg_tools.py render --svg figures/<label>.svg --png-out figures/<label>.recon.png
   --width W`.
4. **Compare — the quality core.** `Read` **both** the approved `figures/<label>.png` and your
   `figures/<label>.recon.png`. Walk the **faithfulness checklist** (`references/svg-discipline.md`)
   and list every concrete drift (layout, connectors, text, colour, z-order). **Cardinal law
   (DrawAI's "the image wins"): the approved PNG is the only source of truth — your decomposition
   notes yield to the pixels; never invent a module/arrow/label/grid-line that isn't there, never
   omit one that is.**
5. **Refine.** Edit the SVG to close every named drift; carry the SVG forward as the editable base.
   **Run ≥2 rounds (cap 3** — DrawAI's `max_critic_rounds`): round 1 focus = **layout** (region
   geometry, connector routing/arrowheads, alignment, z-order); round 2 = **text/style** (content,
   font, weight, colour, size, baselines, legends). Keep going while material drift remains (capped).
   "No drift I can name" — not "round 1 looked fine" — is the bar.
6. **Lint gate.** `svg_tools.py lint --svg figures/<label>.svg --canvas WxH --type <type> --render-check`
   must return `ok:true`. For a vector type this is where "you actually redrew it" is enforced — a
   whole-canvas raster or a zero-`<text>` SVG is a HARD error, not a warning. Fix every error.
7. **Export.** `svg_tools.py topdf --svg figures/<label>.svg --pdf-out figures/<label>.pdf`.

## The non-negotiable quality gate (and the SUB-REGION escape hatch)
After exporting, judge: **is the vector visually ≥ the approved raster?** **Redraw is mandatory for
every vector-type figure — you may NOT "vectorise" by wrapping the whole PNG in an `<image>`** (the lint
rejects that for vector types, and so does the DoD gate). The escape hatch is for a **genuinely
un-vectorisable SUB-region only** (a photo inset, fine continuous shading) — never the whole canvas:
embed just that crop as a **`data:` base64 `<image>`** (run `svg_tools.py crop --png figures/<label>.png
--box "x,y,w,h" --out figures/<label>.crop.png`, which prints a ready-to-paste `image_element`), keep the
rest vector, then **re-run `lint --type <type>` then `topdf`**. (A `data:` URI is the **only** `<image>`
form the renderer draws under `unsafe=False`; a relative/file href renders **blank**.) The ONLY case a
whole-canvas raster is allowed is a figure whose FIGURE-SPEC `type` is **`photo`/`qualitative`** (a real
photograph) — there is no schematic that "can't be redrawn". **Never ship a vector worse than the raster;
never delete the `.png`.**

## Output & handoff back to ts-paper-figure
- `figures/<label>.svg` — the editable vector source.
- `figures/<label>.pdf` — the embedded vector (this is what LaTeX includes; ts-paper-figure inserts
  it **extension-less**, `\includegraphics{figures/<label>}`, so pdflatex prefers the `.pdf`).
- `figures/<label>.png` — the **kept** original raster (also the graphics fallback).
ts-paper-figure records the per-figure reconstruction outcome in `logs/6_figure.io.md` (round count +
a one-line "≥ raster" verdict) and the figure's `type`/`engine` in `figures/figures.manifest.json`; the
`run_gates.py all` vector check (`svg_tools.py check`) asserts every figure has its `.pdf` **and** that
every vector-type figure's `.svg` is a real redraw (not a whole-canvas raster).

## What this deliberately does NOT do (kept lean, vs DrawAI)
No SAM3 segmentation service, no remote OCR, no Codex/agent SDK, no box-IR merge/dedup, no asset
manifest, no PPTX export, no Workbench. Those are DrawAI's machinery for arbitrary screenshots over
many services; for a paper schematic that **Claude already perceives**, the distilled loop
(decompose → author → render → compare → refine → export) is the whole thing — Claude's vision
replaces the entire perception stack, and one cairosvg script does the irreducible rasterise/convert.
