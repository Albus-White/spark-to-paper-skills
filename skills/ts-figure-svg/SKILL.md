---
name: ts-figure-svg
description: >
  PaperBanana+ — turn a paper's figure brief into a native, editable, publication-grade SVG. Stage 1 runs
  the OFFICIAL PaperBanana (dwzhu-pku/PaperBanana, pulled by `setup_paperbanana.py`, its own
  Retriever→Planner→Stylist→Visualizer→Critic pipeline) to produce candidate PNGs. Stage 2 is the "+":
  Claude LOOKS at the chosen PNG, extracts its DESIGN LANGUAGE (palette, type scale, spacing, idiom) into
  a style sheet, then redraws the figure FROM THE PAPER'S FACTS as real <rect>/<path>/<text> objects —
  never tracing pixels, never embedding the PNG. Stage 3 is a measured repair loop: `audit_svg.py`
  (stdlib, no renderer needed) catches overflow, text-on-text, icons cutting labels, stroke-scaled and
  canvas-clipped arrowheads, dangling connectors, sub-legible type, font-fallback glyphs, CSS-cascade
  colour traps and traced path-soup; ≥4 rounds, no upper bound while defects remain. Ends on a vector PDF
  verified on the real compiled page. Use when a figure must be editable and correct, not merely pretty.
---

# ts-figure-svg — PaperBanana+ : design language in, native SVG out

An image model draws a *picture of* a figure. This skill turns that picture into an actual figure: every
label live text, every edge traceable to the method, every box measured.

Two things it is not, both learned the hard way:

- **Not a pixel replica.** Auto-tracing one figure produced 59,430 paths, 10 MB, no editable text — and
  it was *still blurry when zoomed*. "No `<image>` element" does not mean "vector".
- **Not the PNG's logic.** Generated figures invent sequential links, fabricate numbers, and garble
  labels. Take the PNG's *look*; take the paper's *content*.

## Setup (once)

```bash
python3 scripts/setup_paperbanana.py            # clone official PaperBanana into engine/ + deps
export OPENROUTER_API_KEY="sk-or-v1-..."        # one key covers VLM agents + image generation
python3 scripts/setup_paperbanana.py --check-only
```

`engine/PaperBanana/` is gitignored — upstream's code, pulled, not vendored. If no key is configured,
**stop and ask the user**; do not substitute a different image backend silently.

Probe the local toolchain with `;` between checks, not `&&` — chaining dies at the first missing tool and
tells you nothing about the rest:
`command -v inkscape; command -v rsvg-convert; command -v pdftoppm; command -v pdffonts; fc-match 'Times New Roman'`.
There is no `python`, only `python3`; `xmllint`/`jq`/`zip` may all be absent (use `python3 -c`, stdlib
`json`, and `7z a -tzip`).

## Stage 0 — lock the figure brief before drawing anything

Per figure, not per paper. Scan the TeX for real placeholders, captions, labels and body references: one
paper often has 2–3 missing figures, and a "one overview figure each" guess is how the denominator ends
up wrong. The compile entry file is **found, not assumed** — `rg -l '^\\documentclass' -g '*.tex'`; in an
11-paper batch two built from `acl_latex.tex` and nine from `main.tex`.

Write `<work>/<label>.brief.md` with these sections, in this order — this is the shape that worked:

```
## Reader question and role      one line: what the reader learns from this figure
## Caption intent                the existing caption, verbatim
## Scientific facts to preserve  every module/edge/symbol/constraint, quoted from the method text,
                                 marking which edges are parallel vs sequential and what is shared
## Must not appear               results numbers in a method figure; causal claims the paper does not
                                 make; anything true only under an assumption the figure cannot show
## Visual design                 hard numbers: canvas ~1520x640, at most five semantic modules,
                                 minimum 20px body / 25px section titles at this canvas size
```

The input is the paper's **existing** Method/Design text plus its **existing** caption — not the whole
paper (that yields a whole-paper summary figure) and not a hand-written slogan (that yields generic
boxes).

Build the paper's baseline PDF **now** (without `-shell-escape`; the svg package is not loaded yet) and
record its page count and pre-existing warnings, so a later overfull box is attributable to a source
line rather than to your figure. Quarantine stale aux files with `mv`, never `rm`.

## Stage 1 — PaperBanana (official) → candidate PNGs

```bash
python3 engine/PaperBanana/skill/run.py \
  --content-file "<work>/<label>.brief.md" \
  --caption "<the figure's caption intent>" \
  --task diagram --aspect-ratio 3:2 \
  --num-candidates 3 --max-critic-rounds 3 \
  --retrieval-setting random --exp-mode demo_full \
  --output "<work>/paperbanana/<label>.png"
```

- **`--retrieval-setting random`, never `none`.** PaperBanana is reference-driven; with `none` it skips
  the reference dataset entirely, the Planner gets zero exemplars, and the Stylist paints a generic
  conference look over it. **That single flag is why an entire early batch came out as identical pale
  box-and-arrow pipelines.** `auto` is unusable with a normal context window — it feeds the Retriever the
  full method text of 200 reference papers in one call.
- **Filenames:** `--num-candidates 1` writes `--output` verbatim; N>1 writes `<stem>_0.png`, `_1.png`, …
- **`--num-candidates N` also sets the concurrency** — N simultaneous image requests. Three candidates ×
  2–3 critic rounds is a **~40 minute serial job per figure**; a batch is not an interactive turn.
- **On repeated 504/timeout: retry the *same* paper with *identical* parameters, at most 3 consecutive
  times, then mark it `blocked` and move on.** Do not raise concurrency, swap models, swap keys, cut the
  candidate count, or pass a failed run off as a success.
- `demo_full` inserts a Stylist that can over-simplify; `demo_planner_critic` is the same chain without
  it and keeps more method detail. When a figure comes back thin, run one of each and compare.

**A finished run is not a passed run.** The known silent failure: when the Critic's text call exhausts
its 5 retries the runner prints `Error: All 5 attempts failed to validate the input.` and then, on the
very next line, `[Critic Round 1] No changes needed. Stopping iteration.` — a total API failure logged as
convergence, exit 0, PNG written. **Grep the run log for `All 5 attempts failed` next to `No changes
needed`**; if you see it, the critic chain did not run and the candidate is incomplete, not selected.

**Choose in two stages, never one.** First `identify -format '%f\t%wx%h\t%b\n'` + `sha256sum` all
candidates, then a thumbnail contact sheet for triage
(`montage <cands> -thumbnail 768x512 -tile 1x3 -geometry +0+18 sheet.png`); only then read the finalists
at full size. Priority is strict: **(1) relations, directions, formulas and numbers all correct →
(2) reader grasps input→process→output in seconds → (3) legible at the real column width →
(4) geometric tidiness → (5) beauty.** Real rejections to reuse as a checklist: a candidate that was
*better laid out* but labelled the third sealed card `E2` instead of `E3` (correctness beats layout,
outright); fabricated example scores and invented timestamps; seven framed states that dissolve at column
width.

Record the decision in `<work>/<label>.design_selection.md`: chosen filename + **SHA-256** (the reference
is now immutable), *Retained design language*, and *Scientific and visual corrections required* — the
list of things you are deliberately **not** copying. Copy the winner to `<work>/<label>.target.png`.

> `--aspect-ratio` is a request, not a guarantee — some backends hardcode their own size. Record the
> requested ratio *and* the `identify` measurement.

**Then stop and show the user the contact sheet.** Candidate acceptance is a human gate; do not roll
straight into SVG work.

## Stage 2 — learn the design language, then redraw from the paper

**2a. Extract the style sheet.** `Read` the target PNG and write `<work>/<label>.style.json`: background
and card fills, accent/semantic colours (what each hue *means*), stroke weights, corner radius, type
scale, spacing rhythm and column grid, icon idiom, arrow style, and the layout skeleton. This file — not
the pixels — is what carries over.

**2b. Draw `round_01.svg` from the brief, styled by the sheet.** Read `references/svg-craft.md` first; it
is the defect catalogue this loop exists to prevent. Non-negotiables:

- real `<rect>/<path>/<line>/<circle>/<text>/<tspan>/<marker>/<g>`, semantic ids, no `<image>`, no data
  URI, no external reference, no traced pixel paths;
- `font-family="Times New Roman, Nimbus Roman, serif"`, sizes as **classes** (a per-element `fill`/
  `font-size` attribute loses to any stylesheet rule — that is the white-text-on-colour trap);
- fixed small arrowheads: `markerUnits="userSpaceOnUse"`, `6.4×4.8`, `refX="6.1" refY="2.4"`;
- connectors drawn **before** nodes, nodes before text; endpoints docking on card edges;
- canvas sized by target column (see svg-craft), not by taste.

## Stage 3 — the measured repair loop (≥4 rounds, no upper bound)

One block per round, **in this order** — snapshot first so you can diff round N against N-1, and `|| true`
the audit so a failure still leaves you the picture that explains it:

```bash
cp <work>/current.svg <work>/round_0N.svg                      # 1. snapshot BEFORE any check
python3 scripts/audit_svg.py <work>/round_0N.svg \
        --json <work>/round_0N.audit.json || true              # 2. structure + geometry
python3 ../ts-figure-optimize/scripts/render_svg.py \
        <work>/round_0N.svg <work>/round_0N.png --width 1440   # 3. wide: geometry + typography
python3 ../ts-figure-optimize/scripts/render_svg.py \
        <work>/round_0N.svg <work>/round_0N_col.png --width 480 # 4. real column width: legibility
```

Two widths, two different jobs — a figure that reads fine at 1440 can be unreadable at 480. **Then look
at both yourself**, zoom every flagged hit at 4×, and re-read the figure against the method text. Append
one line per round to `figures/repair_logs/<label>.log`: what the audit found and what you changed — the
observed diff, not the intended edit.

`audit_svg.py` fails the round on: forbidden element, data URI, external reference, duplicate id,
unresolved `url(#…)`, no live text, `path_soup` (traced rather than drawn), font stack not starting with
Times, size under the floor, `markerUnits="strokeWidth"` or an oversized head, canvas overflow **including
a clipped arrowhead**, text–text overlap, a label whose clearance is under `max(4px, 0.35 × font-size)`, a
shape painted over text, a glyph that will trigger a silent font fallback, and a `fill`/`font-size`
presentation attribute that the stylesheet beats. It warns on floating text and connectors docking on
nothing. Text boxes come from Adobe core-14 Times metrics, so no renderer is required and the numbers are
exact for the mandated stack.

**Round 4 has a job of its own:** the column-width + vector gate. Export the PDF and confirm
`pdfimages -list` returns zero image rows and `pdffonts` shows every font `emb=yes sub=yes uni=yes`.

**Stopping rule: four rounds is the floor, not the target.** A round that still finds problems means
there is a next round — one figure went to six because round 4 was "close to final" but had one badge
overhanging and one card touching its edge. Neither "the audit passes" nor "nothing looks wrong at
1440px" ends it: at round 4 of one batch all three SVGs returned `passed: true` and actual-size review
still found a 5px label overlap.

When it is genuinely clean, copy the last round to `figures/<label>.svg` and:

```bash
python3 scripts/svg_to_pdf.py figures/<label>.svg figures/<label>.pdf
```

The backend ladder is rsvg-convert → headless browser → Inkscape → cairosvg, and the result is rejected
unless it embeds fonts. Inkscape's SVG→PDF outlined every glyph *even with*
`--export-text-to-path=false`: `pdffonts` came back empty and it scored RMSE 0.127 against the reference
render where the browser's PDF scored 0.087. Both passed a naive "no rasters" check; only the font table
told them apart.

## Stage 4 — page-level acceptance

Insert with the minimum possible diff: replace only the placeholder token with an extension-less
`\includegraphics[width=\columnwidth]{figures/<label>}` (`\textwidth` inside `figure*`), keeping the
existing `\caption`/`\label`. **Prove "nothing else changed" mechanically** — `cmp` every other section
file against a pristine copy — rather than asserting it. Four exceptions are legitimate but must each be
declared as a body-text change: an `\IfFileExists` guard, promoting `figure` → `figure*` for a wide
diagram, inserting a whole new float where no placeholder existed, and replacing real content (one paper
displaced a live 15-line `tabular`).

(If you use `\includesvg` instead, `inkscapelatex=false` is **mandatory** — without it the svg package
splits the file into a LaTeX text overlay and dies on the first Unicode glyph — and `-shell-escape`
becomes load-bearing because svg.sty shells out to Inkscape at compile time.)

Then compile and check the **page**, not the exit code:

- Five log counters: LaTeX/Package/Fatal errors · `Overfull \hbox|\vbox` · undefined references ·
  missing files · the figure filename's own hit count (proof the asset was actually consumed).
- **Find the figure's page, never assume it** — loop the pages and grep the extracted text for the
  caption string.
- `pdfimages -f P -l P -list | tail -n +3 | wc -l` == 0 proves *that page* carries no raster. It does
  **not** prove the document — other pages legitimately carry rasters.
- `pdffonts` on the whole document will show Type 3 DejaVu subsets from pre-existing matplotlib plots.
  Attribute them; do not "fix" them.
- **Measure the smallest word instead of eyeballing it:** `pdftotext -f P -l P -bbox out.html`, parse
  every `<word>`, and report min/median/max of `yMax − yMin` in **points** within the figure's y-band.
  Accepted bands in the record ran 5.56 / 6.39 / 9.81 pt; a single 5.0 pt outlier sent one subtitle back
  for another round. This catches the one straggler label that both a CSS font audit and a glance miss.

Finally, the **fresh rebuild**. Copy the distribution sources to a new directory and `cd` **into it**.
Three ways this was botched, all of which produced a false PASS or a false failure:

1. `rsync --exclude='*.pdf'` stripped the paper's *own* pre-existing figure PDFs → build died.
2. The temp directory was created but `latexmk` ran in the paper directory anyway — the comparison then
   compared the paper against itself and reported PASS.
3. A trailing `rm -rf` on the temp dir was rejected outright by the safety gate, killing the build with
   it. Never chain cleanup onto the command whose evidence you still need.

Acceptance is a **triple**: equal page count, equal `pdftotext -layout` sha256, equal per-page 100dpi PNG
sha256. **PDF byte hashes legitimately differ** — do not use them.

## Batch bookkeeping (more than one figure)

- One row per **figure**, and a closed status vocabulary: `pending / generating / vectorizing /
  compiling / passed / blocked`. No other word, so the table stays greppable.
- **A status may only advance when its evidence cell changes with it.** Partial satisfaction does not
  advance: a paper with both candidates generated but one critic round skipped stayed `generating`, with
  the defect written into the cell.
- **Encode exclusions inside every scan command**, never as a note beside it. A final sweep reported 24
  SVGs and five audit failures because the excluded project lived in prose; the failures were all from
  the out-of-scope directory. Exclude the per-figure work directories too (`! -path '*_work/*'`), or you
  will audit `round_03.svg` as if it were a deliverable.
- **A sweep that returns nothing must be proven against a known hit.** One placeholder scan printed an
  empty `PENDING PLACEHOLDERS` list while three papers still had unfilled placeholders — the pattern
  simply did not match their syntax.
- **A search that errors looks exactly like a search that found nothing.** One negative assertion failed
  with `regex parse error: look-around … is not supported` and was read as "all markers compliant".
  Check the exit code of every check whose value is its *emptiness*.
- Report against the **figure** denominator and state both ("6/11 papers, 11/16 figures"). When a count
  is discovered wrong, correct the table and every downstream report in one atomic patch — the batch
  total moved 16 → 17 mid-run.
- After any global normalisation (e.g. shrinking every arrowhead), **sweep the whole batch, don't spot
  check**: 13 of 17 final SVGs still carried the old markers. Then recompile only the affected papers,
  and append the sweep to each figure's record as a section that *supersedes* the earlier verdict.

## Record

`figures/figures.manifest.json` entry:

```json
{"label":"...","type":"architecture","engine":"paperbanana",
 "reference_used":"paperbanana:<label>_2","grounding":"design-language",
 "critic_rounds":3,"svg_redraw":true,"svg_rounds":6,
 "svg_audit":"figures/audit_logs/<label>.audit.json"}
```

`run_gates.py <workdir> all` enforces it: a redrawn figure needs `svg_rounds ≥ 4`, a passing audit JSON,
and a non-empty `repair_logs/<label>.log`.

Report per figure: candidate chosen + why the others lost, SVG round count, the final audit's error and
warning counts, the figure's page number, the smallest measured word in points, and any residual warning.
"Passed" means those artifacts exist — not that a summary said so.
