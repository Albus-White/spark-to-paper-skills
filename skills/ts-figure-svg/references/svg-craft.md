# SVG craft — the defect catalogue

Every entry is a defect that actually shipped in the recorded PaperBanana→SVG runs, its root cause, and
the fix. Read this before round 1, not after round 4. `audit_svg.py`'s error codes map onto it.

## The one rule that generates all the others

**The PNG is a style reference; the paper is the source of truth.** Borrow palette, hierarchy, spacing
and idiom from the render. Take every box, edge, symbol and number from the paper text. A generated
figure that implies two patches are sequential when the method applies them independently is a *wrong
figure*, however good it looks — reuse its look, rewire its logic.

## Geometry

| Defect | Root cause | Fix |
|---|---|---|
| `marker_scales_with_stroke` — arrowheads huge, colliding | default `markerUnits="strokeWidth"`; a 6-unit head on a 3px stroke rendered ~18px | `markerUnits="userSpaceOnUse"` and a fixed small head |
| `canvas_overflow` on a connector whose coordinates are inside | the **marker paints beyond the path endpoint** | grow the viewBox, or give edge connectors a marker-less class and draw the head as an explicit in-canvas `<path>` |
| `dangling_connector` — line stops in mid-air | endpoints typed by hand instead of derived from a card's port | compute each endpoint from the card's edge; target ≤2px from the declared port |
| `shape_over_text` — icon slices a label in half | icon/card drawn after the text, no reserved area | draw connectors **first**, nodes second, text last; give every icon a reserved slot ≥6px from text |
| `container_overflow` / `container_hug` | text placed by baseline without measuring its box | measure, then re-flow. Clearance ≥ `max(4px, 0.35 × font-size)` on all four sides; card interior padding ≥6px. Measured overruns in the record were 2.7 / 3 / 7.6 / 10 / 26px — **all invisible to a source-coordinate check** |
| `text_overlap` | two labels on one baseline band | re-wrap or move; never overlap-and-hope |
| `floating_text` | no shared alignment grid | snap every element to a column/row grid; anchor stray notes into a card or a footer band |
| `path_soup` | the figure was traced, not drawn | see below |

**Never fix an overflow by shrinking the font**, and never move an unrelated component to compensate for
an error elsewhere — edit the failing object's own coordinates. Grow the canvas, split the line, drop a
repeated word, re-lane the layout, or go two-column (`figure*`).

**Fixed repair order** — out-of-order repairs oscillate, because fixing text before its container moves
means redoing it after:

> 1 canvas/crop → 2 global regions and z-order → 3 node bounding boxes → 4 fills and strokes →
> 5 connectors and endpoints → 6 text (wording, family, weight, size, baseline) → 7 decorative detail.

## Canvas and type — chosen by target column, not by taste

| Target | Canvas | Body floor |
|---|---|---|
| ACL/IIETA **single column** | 900 × H (H 600–1465), portrait | 24px |
| **Two-column** `figure*`, full width | 1400–1520 × 640–840, landscape | 20–22px |

At 1400 wide placed at `0.98\textwidth`, 22px body text lands near **8pt** on the page. The floor was
escalated 20 → 22 → 24px during the batch, and the trigger was never a CSS reading — it was a 180dpi
render of the *compiled page* where secondary labels came out "barely readable".

Size scale as classes, not per-element attributes: `.section 27px/700 · .module 24px/700 · .body 22px ·
.small 20px`. Cards: 7–10px corner radius, 1.5–2px stroke. Connectors: 2–3.2px, `stroke-linecap: round`.

**After any global type change, re-run the full audit** — enlarging every class in one pass
re-introduced defects earlier rounds had already cleared.

## Fonts

- `font-family: "Times New Roman", "Nimbus Roman", serif` declared once on the bare `text` selector.
- The declared stack and the **embedded** font are different facts. On a box without Microsoft fonts
  `fc-match 'Times New Roman'` resolves to Nimbus Roman and that is what the PDF embeds. Report what
  `pdffonts` shows — never claim the PDF embeds Times New Roman because the SVG asked for it.
- `glyph_fallback_risk`: `✓ ✗ → ⇒ ∈ ≥ τ Δ` and friends are outside a Times *text* font, so the exporter
  silently pulls in a second family for that one glyph. Draw ticks/arrows as `<path>`, or reword.
- Sub/superscripts are real tspans — `<tspan baseline-shift="sub" font-size="17">c</tspan>` at ~0.75–0.8×
  the parent — never Unicode subscript characters. They are legitimately allowed under the body floor.
- Multi-line text is stacked tspans with the **`x` repeated** on each line plus `dy`; omit the repeated
  `x` and the line break silently collapses.

## The CSS cascade trap (white text on colour)

A presentation attribute loses to **any** stylesheet rule. So a global `text { fill: #1a1a1a }` beats
`<text fill="#fff">`, and every white label on a coloured pill renders dark-on-dark — invisible at 1×,
obvious at 4×. Put it in a class: `.inverse{fill:#fff}`, then `class="small inverse"`.
`audit_svg.py` flags this as `presentation_attr_beaten`, because it resolves the cascade the way a
renderer does rather than the way the source reads.

## Structure

- Real objects only: `<rect> <path> <line> <circle> <text> <tspan> <marker> <g>`. No `<image>`, no data
  URIs, no external links, no scripts — and no auto-traced pixel paths.
- **`path_soup` is the machine-checkable form of "never trace".** Cleanliness =
  `(rect+circle+ellipse+line+polyline) / (that + path + polygon)`, floor 0.35. The recorded pixel trace
  of one figure: 10,394,701 bytes, 59,430 paths, 1 rect, no editable text — it scored a perfect pixel
  match and was worthless. A hand-drawn figure of the same content sits above 0.6 and under ~100 KB.
- Unique ids; every `url(#…)` resolves. A typo'd marker id renders as *nothing*, silently.
- Group semantically (`<g id="stage-2">`) so a later round can move a whole card.
- Root carries identity: `role="img" aria-labelledby="svg-title svg-desc"` with `<title>` and `<desc>`.
- Simplification is encouraged — textures, gradients, 3-D shading, ornament. Never simplify away a
  branch, a constraint, a symbol, or an evidence boundary.

## Iteration

Keep every round as its own file (`round_01.svg`, `round_02.svg` …) and **snapshot before you check, not
after**. Overwriting one `final.svg` destroys the failure→fix chain, and that chain is what stops round 5
from reintroducing round 2's defect.

**Every scanner hit gets a cropped 4× zoom and a human verdict.** A hit may be dismissed as a false
positive only with a written reason, and only two reasons are legitimate: a `<g>`'s inflated union
bounding box, and a shape fully covered by a later-painted opaque card. "Probably fine" is not one.

Four rounds is the floor, not the target. A round that finds problems means there is a round 5. The
audit passing does not end it either — the audit measures geometry, not whether the figure says
something true about the paper. The final figure must read at 100%, at 200%, and shrunk to column width.

## Acceptance layers — none substitutes for another

1. **Structure** — `audit_svg.py` (parses, ids unique, no forbidden elements, markers sane, not traced).
2. **Geometry** — same script (overflow, overlap, occlusion, clearance, dangling connectors).
3. **Vision** — render at full width *and* at real column width; look at both; zoom every flagged hit.
4. **Science** — re-read the method text against the figure: every edge, symbol, and label.
5. **Page** — the compiled PDF: `pdffonts`, `pdfimages -list` on the figure's page, `pdftotext`, and a
   rendered page image. Measure the smallest word, don't eyeball it (see SKILL.md stage 4).
6. **Fresh build** — copy the sources to a new directory, `cd` **into it**, build there.

Pixel similarity to the reference PNG is recorded as a diagnostic and **never** as a gate — it must not
outrank scientific correctness or readability, and deviating from the render is required wherever
matching it would preserve a typo or a wrong topology.

A green layer 1–2 with a broken layer 4 is the most expensive failure mode: it looks finished.
