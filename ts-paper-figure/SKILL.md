---
name: ts-paper-figure
description: >
  Stage 6 of the ts-paper suite. Fill a Traitement du Signal paper's figure placeholders with real
  diagrams, distilled from PaperBanana into a Claude-native loop: Claude DESIGNS a concrete, rich figure
  and GROUNDS it on a real on-topic top/mid-journal MAIN figure (Claude **WebSearches** for it, then
  `fetch_reference_figures.py` pulls that paper's MAIN figure, passed to the image model as an
  image-condition — grounding is MANDATORY, no silent skip), an external image model renders it (the only
  irreducible code — Claude can't draw pixels), Claude then LOOKS at the rendered PNG with its own vision
  and critiques/refines it over ≥2 ENFORCED rounds, then ALWAYS vectorizes
  it to an editable PDF (matplotlib figures are born-vector; an image-model raster is vectorized by
  **ts-figure-optimize**'s DrawAI **HYBRID** = the approved render kept pixel-exact + an editable <text>
  overlay; if DrawAI is unavailable the approved PNG is kept as-is — never a lossy redraw, PNG always kept) and inserts it.
  You configure only the image model (model/key/url). Engine is routed by SECTION: only real measured-data
  results plots (data-aware mode, results section) use matplotlib; EVERY other figure — architecture/pipeline/
  concept/math-geometry/schematic — is image-model rendered (so in proposal mode every figure is image-model).
  In proposal mode quantitative results plots are SKIPPED (no real data — drawing one fabricates results).
  Use to turn the empty \fbox placeholders into publication-quality figures.
---

# ts-paper-figure — figures, the PaperBanana way, distilled into Claude

PaperBanana made good academic figures with a team of LLM agents (Planner → Stylist → Visualizer →
**Critic** → Polish) running a **critique-and-refine loop** (it rendered an image, *looked at it*,
scored it, refined the description, re-rendered, up to 3 rounds). Every step except drawing pixels is
LLM reasoning + **vision** — which Claude does natively. So the whole system distills to: **Claude is
the Planner/Stylist/Critic/Polish; one tiny script (`gen_image.py`) is the Visualizer.**

**Three things make this a SKILL and not just "Claude drawing a flowchart" — NEVER skip them:**
**(C1) DESIGN a concrete, rich visual blueprint** (step 2) instead of an abstract box list;
**(C2) GROUND every free-form figure in a real on-topic MAIN journal figure** (step 2b) — Claude
**WebSearches** for a TOP/MID-venue on-topic paper, fetches its MAIN figure, and passes it as an
image-condition (`/images/edits`) **plus** convention guidance — **mandatory, gate-enforced, no silent
skip**; **(C3) ENFORCE a logged multi-round vision critique** (steps 4–5, gated). The default
aesthetic is **rich & concrete** (real imagery, layered tensors, coordinated panels) — **never a flat
thin-line flowchart**. (Without C1–C3 the figures regress to the sparse boxes-and-arrows this redesign
fixed.)

## The only code: `scripts/gen_image.py`
It does one thing — send a prompt to an external image model, save a PNG. Configure the image model only:
```
export TS_FIG_MODEL="gpt-image-2"          # ← the image model (default gpt-image-2); from the repo .env
export TS_FIG_API_KEY="<image api key>"
export TS_FIG_BASE_URL="<openai-compatible base>"  # e.g. https://api.openai.com/v1
export TS_FIG_API_STYLE="images"           # or "chat" for nano-banana-style gateways
export TS_FIG_SIZE="1536x1024"             # QUALITY: landscape, mirrors the product's default (not 1024x1024)
export TS_FIG_QUALITY="high"               # gpt-image-* quality knob (the product used "high")
```

> **⛔ MODEL POLICY — do NOT pick a model yourself.** The image model is whatever **`TS_FIG_MODEL`** says
> (set in the repo-root `.env`; default **`gpt-image-2`**). **Never substitute, downgrade, or guess a model**
> (e.g. do NOT fall back to `gpt-image-1`), and never improvise the key (use `TS_FIG_API_KEY`, not
> `OPENAI_API_KEY`). If `TS_FIG_MODEL`/`TS_FIG_API_KEY`/`TS_FIG_BASE_URL` are unset, `gen_image.py` returns
> `unset env: …` — **STOP and ask the user to set them in `.env`**; do not export a model of your own choice.
Note: `TS_FIG_SIZE`/`TS_FIG_QUALITY` take effect only in images API style (`TS_FIG_QUALITY` only for
`gpt-image-*` models); in chat style the gateway controls resolution, so verify the render size in the
critique loop and re-render if crude.
(scaffold in `scripts/figure_config.example.sh` — copy to `figure_config.sh`, fill, `source` it.)
Text planning and critique need **no** config — they are Claude. **Quality matters:** render at
`1536x1024` `quality=high` (the defaults above), give a detailed prompt, and do a real refine pass —
a 1024×1024 low-effort render looks crude.

## Two figure engines, routed by SECTION (matplotlib only for results-section data plots)
The engine is decided by **which section the figure lives in**, NOT by its `type` — because matplotlib
only looks good for real-data plots and renders concept/schematic figures poorly (the "ugly matplotlib
figure" complaint this routing fixes):
- **matplotlib — ONLY for a real measured-data results plot in the results/experiments section**
  (`../ts-paper-data/scripts/plot_results.py --script`, figures4papers house style auto-applied — see
  `ts-paper-data/references/plot-style.md`). This is the one place exact-from-values plotting is needed:
  a results bar/line/heatmap/radar built from real numbers in `results.facts.json`, so **only in
  `data_aware` mode**. **Born vector:** the plot script MUST end with `finalize(fig, OUT)` and MUST NOT
  call `plt.savefig()` itself — `finalize` writes the PNG **and** a vector `figures/<label>.pdf` (editable
  text via `svg.fonttype=none`). In `proposal` mode there are no real numbers, so a results plot must NOT
  exist — if one slipped through, remove the float (never leave a blank `\fbox`, never fabricate/stub).
  Removing such a float does NOT violate the no-blanks rule: a results placeholder is illegitimate in
  proposal mode and should never have been emitted, so never render a substitute.
- **image model — EVERY OTHER figure, in every other section** (`gen_image.py` + GROUND + the
  vision-critique loop below): architecture / pipeline / framework / flow diagrams, qualitative scenes,
  icon schematics, **AND every concept / math-geometry illustration** (a distribution, manifold,
  trajectory, loss-curve shape, 3D geometry). These used to go to matplotlib and came out ugly — they
  are now DESIGNED + GROUNDED + image-model-rendered + ≥2-round vision-critiqued. (A concept illustration
  makes no real-metric claim and is grounding-OPTIONAL — ground it on a clean on-topic concept figure if
  one exists, else treat it like a qualitative scene.) After the PNG is approved, it is **vectorized** by
  the sibling **ts-figure-optimize** skill (step 5b; DrawAI **HYBRID** — the approved render kept
  pixel-exact + an editable <text> overlay, key-free). If DrawAI is unavailable, the approved PNG is kept
  as-is — never redrawn.
  - **🔴 HARD RULE — generation is INDEPENDENT of vectorizer availability.** A free-form figure is ALWAYS
    produced by the image model (steps 2→2b→3→4: rich DESIGN + GROUND on a top-journal MAIN figure +
    render + ≥2 critique rounds). The vectorize tail (5b) is a SEPARATE downstream step: **if
    `ts-figure-optimize`/DrawAI is unavailable, that affects ONLY 5b — it does NOT permit skipping the
    image-model render, and you must NEVER hand-author a from-scratch SVG as the figure.** Hand-authoring a
    flat SVG yields exactly the boxes-and-arrows regression this redesign removes — a HARD violation. The
    manifest `engine` of a free-form figure is **always `image-model`** (never `svg-native`/hand-authored);
    `check_figure_critique` FAILS the build on any non-`image-model` free-form figure.
  - **If the image MODEL itself is unconfigured** (`gen_image.py` returns `unset env: TS_FIG_*`): this is a
    CREDENTIAL gap, handled at the orchestrator **Preflight** — **ASK the user whether to generate figures**
    (it needs `TS_FIG_API_KEY` / `TS_FIG_BASE_URL` / `TS_FIG_MODEL`, e.g. gpt-image-2). If they decline →
    **skip the free-form figures** (leave their placeholders, note in `logs/6_figure.io.md`); matplotlib
    results/concept plots still run (no key). **Never** substitute a hand-drawn diagram or improvise a key.

This unifies the suite's two figure-craft sources — **figures4papers (matplotlib)** for results-section
data plots, **PaperBanana (image model)** for everything else. **NET: in `data_aware` mode only the
results-section data plots are matplotlib; every other figure is image-model. In `proposal` mode there
are no data plots, so EVERY figure is image-model.** The figure floor (`figures.min`) is met by both kinds, and
**every placeholder ends rendered — no blanks. Both engines then end on an editable VECTOR PDF**:
every figure ends as `figures/<label>.pdf` (the embedded vector), with the original
`figures/<label>.png` and its source (`.plot.py` for matplotlib, `.svg` for an image-model hybrid) kept
alongside. matplotlib is born-vector; an image-model raster is vectorized via **ts-figure-optimize**
(DrawAI **HYBRID**: pixel-exact render + editable text). If DrawAI is unavailable the approved PNG is
kept as-is — HYBRID-only, no lossy redraw fallback; vectorization must NEVER reduce quality.

## Procedure — the distilled Planner→render→Critic→refine→insert loop
Run after review (stage 5), before latex (stage 7). For EACH `\begin{figure}` placeholder in
`sections/*.tex` that still has an `\fbox{\rule…}` (no `\includegraphics` yet):

1. **Classify + route by SECTION (Critic's first job).** Read `%% FIGURE-SPEC type=…`, `%% DESC:`, the
   caption, and **which section the placeholder is in**, then pick the engine:
   - **Real-data results plot, in the results/experiments section (`data_aware` only):** write a
     self-contained matplotlib script `figures/<label>.plot.py` embedding the real numbers **from
     `results.facts.json`** (grouped_bar for the main comparison, line for a sweep, bar for ablation
     deltas), run `python3 ../ts-paper-data/scripts/plot_results.py --script figures/<label>.plot.py --out figures/<label>.png`,
     then **`Read` the PNG** to vision-check (labels legible, no clipped bars, right metric), fix the
     script if needed, then go to **step 6 (Insert)**. `proposal` mode → remove the float (no data). This
     is the ONLY matplotlib path.
   - **EVERY other figure** — architecture/pipeline/framework/flow schematic, qualitative scene, AND any
     concept / math-geometry illustration (distribution, manifold, trajectory, loss-curve shape, 3D shape):
     continue to **step 2** (the `gen_image.py` Planner→render→Critic→refine loop). A concept/math-geometry
     figure is illustrative (no real-metric claim) and grounding-OPTIONAL, but is still IMAGE-MODEL — never
     matplotlib (`check_figure_critique` FAILS a matplotlib figure outside the results section).
   The image-model path always runs the vision-critique loop. Either way, no placeholder is left blank.
2. **DESIGN the figure, then write the prompt (Planner + Stylist).** Adopt the lens of a *Lead Visual
   Designer for a top-tier venue (NeurIPS/CVPR/TGRS)*. FIRST sketch a concrete VISUAL BLUEPRINT (in your
   reasoning): for each position in the figure decide WHAT concrete thing appears — real imagery, a
   data/result panel, a layered-tensor network block, a depicted icon — **not just a labelled box** — and
   wire the data flow from the equations (below). THEN write a single, self-contained image-generation
   prompt that realises that blueprint and is **as detailed and concrete as possible — vague/abstract
   specs are the #1 cause of thin flowchart output**:
   - **Semantics:** name **every** box/module and **every** connection/arrow, in the order the method
     presents them; group related blocks; show the real data-flow direction. **Use the paper's own
     terminology verbatim** for each label (correct, fully spelled — garbled labels are the #1 AI-figure failure).
   - **Wire it from the equations (architecture/method/overview/pipeline/framework figures).** Before
     writing the prompt, build the **edge list from the math**: for every output/intermediate symbol the
     figure will show, find the equation whose **left-hand side defines** it and record `source-module →
     symbol`. The prompt must wire **each output from the single module that defines it** — e.g. "arrow
     from *ML+LLM anomaly detection* to chip *Anomaly score s*" because `s = σ(…)` is that module's
     equation — **never a detached output column where all outputs hang off the whole stack**. Include
     **every** module named in the FIGURE-SPEC `DESC`. (This is the born-from-text analogue of DrawAI's
     box-IR geometry constraint; its ground truth is the equations.)
   - **Conciseness (signal-to-noise):** boxes hold **short keywords/conceptual blocks**, NOT full
     sentences (>15 words) and NOT raw equations — a diagram is a visual abstraction, not box-ified text.
     (Full-sentence text is allowed only when it's an illustrative *data example*, e.g. a sample input.)
   - **Form — rich & concrete (publication-grade), NOT a flat flowchart.** Depict concrete visual
     content, not abstract boxes: **real photographic / data imagery** exactly where the method consumes
     or produces it (satellite tiles, segmentation masks, change maps, sample inputs/outputs); network
     blocks as **layered feature-map tensor slabs with gentle depth**; **multiple coordinated panels**; a
     clear left-to-right data flow; a refined, harmonious palette with **real visual hierarchy and depth**.
     Aim for the density and authority of a MAIN figure in a top-venue paper (the GROUND reference in
     step 2b sets the bar). Keep only these HARD constraints: a clean (white or lightly-toned) background;
     legible, correctly-spelled labels; the figure fits a LaTeX rectangle (no protruding bits/dead
     corners); no watermark and no draw.io-style background grid. **Avoid** flat thin-line box-and-arrow
     flowcharts, sparse single-colour diagrams, and "box-ified text".
   - **Icon semantics:** if the method implies conventional icons, keep their meaning (snowflake =
     frozen/non-trainable, flame = trainable); don't invent or garble them.
   - **Keep out of the image:** the figure caption / "Figure N:" title text, and any redundant text legend.
   - **No numbers** that would imply real results.
   Save it to `figures/<label>.prompt.txt` (so the trace shows what was asked).
2b. **GROUND on a real on-topic MAIN figure — MANDATORY, via your own search (the richness/authority core).**
   Every free-form schematic MUST be grounded on the **MAIN / hero / overall-method figure of an on-topic
   TOP-venue paper** (MID venue only if, after genuinely searching, no top-venue match exists). Use the
   SAME literature-search capability the cite stage uses — **YOU (Claude) actively `WebSearch`**; do NOT
   depend on any pre-existing file:
   1. **Search (`WebSearch`).** Query for the most relevant on-topic paper whose MAIN figure matches THIS
      figure's TYPE (architecture ↔ a paper's main architecture figure; concept ↔ a clean on-topic concept
      figure). Build queries from the paper's domain + this figure's subject (+ "architecture"/"framework"/
      "overview"/"arxiv"). If `<workdir>/retrieved_papers.json` happens to exist (upstream story stage), use
      it as a SEED — but never as the only source, and never assume it exists.
   2. **Confirm venue tier + relevance, then fetch the MAIN figure.** For the top hits, confirm the venue is
      **TOP** (or MID) and the topic genuinely matches. Write your chosen candidate(s) as
      `[{"title","venue","arxiv_url"}]` to `figures/refs/<label>.papers.json` and run
      `python3 scripts/fetch_reference_figures.py --papers figures/refs/<label>.papers.json --out-dir figures/refs --label <label>`
      (or `--arxiv <id> --venue "<venue>"` for a single clear winner). It reports `best_tier` + a **`search_again`** flag.
   3. **If `search_again` is true** (best candidate is not top/mid venue, or none came back) **OR the fetched
      figures are off-topic / minor (not a MAIN overview figure) → go back to step 1 and SEARCH AGAIN** with
      refined queries (different venue, broader/narrower terms). **Do NOT settle** for a low-tier or loosely
      related paper, and **do NOT skip grounding.**
   4. **`Read` the fetched candidates** (`figures/refs/<label>.candidates.json` + the images) and SELECT the
      single best **MAIN / hero / overall-method-overview** figure matching THIS figure's type. **Reject
      scattered minor figures** (results / ablation / qualitative / curves / insets / sample-grids /
      receptive-field / attention maps are NOT references).
   When you pick one: **distil its visual conventions** (how the field draws inputs / tensors / modules /
   outputs) INTO the step-2 prompt, AND **pass it as the render image-condition** (step 3 `--reference`).
   The reference guides CONVENTIONS and richness only — **never copy its content / text / labels / results.**
   Record the chosen paper (arxiv id + venue tier + fig no) in the manifest `reference_used` and set
   `grounding` to `image-cond` (or `vision-distill`).
   **🔴 NO graceful skip — grounding is NOT optional.** `check_figure_critique` FAILS a free-form schematic
   whose `grounding`/`reference_used` is `none`. If, after a GENUINE multi-query search (log the queries you
   tried), a top/mid-venue on-topic MAIN figure truly cannot be found (rare), **STOP and tell the user** —
   never silently render flat-and-ungrounded. (Skip 2b only for matplotlib / results figures.)
3. **Render (Visualizer).** `python3 scripts/gen_image.py --prompt-file figures/<label>.prompt.txt --out figures/<label>.png [--reference figures/refs/<chosen>.png]`
   With a `--reference` on a gpt-image images-style endpoint, `gen_image.py` GROUNDS the render via
   `/images/edits` (image-condition) and reports `"path":"edits"`; with no reference or on any edits
   failure it automatically falls back to text→image (`"path":"generations"`). Either way the rich
   step-2 prompt drives the content.
4. **Critique with your own eyes (Critic — the quality core).** **`Read` the produced `figures/<label>.png`**
   and judge it on PaperBanana's four dimensions; each has hard **red-lines** — any red-line = fail, fix it:
   - **Faithfulness** (most important): matches the Method + Caption; **no hallucinated** modules/connections;
     no reversed or missing data-flow; stays within the caption's scope; **no gibberish/garbled labels or
     broken-LaTeX text** in boxes/arrows. (Smart simplification is fine — simpler ≠ less faithful.)
   - **Semantic faithfulness vs the EQUATIONS (architecture/method/overview/pipeline/framework figures —
     not just spelling/layout):** cross-check the figure against the math, not just against itself.
     Enumerate **every symbol shown** (outputs + intermediates); for each, confirm with your eyes that the
     **incoming arrow leaves the module whose equation DEFINES that symbol** (e.g. `s` must come from the
     anomaly-detection module per `s = σ(…)`, `Q` from the aggregation module, etc.). A symbol sourced
     from the wrong module / the whole stack / a detached column = **red-line**; a module named in the
     method/DESC but **missing** from the figure = red-line. Fix in this same loop and re-render.
   - **Conciseness:** a visual abstraction, not a text dump — red-line if boxes are full sentences (>15 words,
     unless a data example) or crammed with raw equations, or it's a "box-ified" copy of the text.
   - **Readability:** clear flow at a glance — red-line on the caption/"Figure N:" text rendered *inside*
     the image, overlapping/occluded labels, spaghetti arrow crossings, illegible/inconsistent font size,
     low contrast, a non-rectangular layout with dead corners, or a black background.
   - **Aesthetics:** publication polish — red-line on draw.io grids, pixelation/blur/distortion, neon or
     clashing colours, or mixed/misaligned fonts. (Rich, depicted, photographic, non-flat styling is
     GOOD — never red-line a figure for being detailed or realistic.)
   - **Richness / density (publication-grade) — the de-flat dimension:** the figure must show CONCRETE
     content (real imagery / data panels / layered tensors / depicted modules), multiple coordinated
     elements, and clear visual hierarchy — **red-line a thin, sparse box-and-arrow flowchart.** If it
     reads as a generic flowchart, name what to ADD (real imagery where the method touches data, tensor
     detail in the blocks, coordinated panels, denser correct labelling, stronger hierarchy) and
     re-render. Use the step-2b GROUND reference's density as the bar to clear.
   - **Integrity:** no fabricated numbers/results depicted; the GROUND reference informs CONVENTIONS only,
     never copied content/text/results.
5. **Refine (loop) — at least 2 rounds, the product ran 3.** "No red-line" ≠ "as good as it gets": a
   render can be red-line-free yet **crude** (sparse, generic, weak hierarchy, thin labelling). So do NOT
   accept round 1 just because nothing failed — run **at least one genuine improvement pass**: name what
   would make it more *publication-grade* (denser/clearer labels, stronger visual hierarchy, tighter
   layout, better use of the canvas, more faithful detail) and re-render. Repeat **up to 3 rounds**
   (PaperBanana's `max_critic_rounds`); accept early **only when the render is genuinely polished**, not
   merely red-line-free. Keep the best version; never ship a garbled or crude figure — if it's still weak
   after 3 rounds, ship the best and note the residual issue in the log.
   **Prove each "improvement" is real (no phantom v2):** write each round to a DISTINCT file
   (`<label>_vN.png`) and, before you claim a round improved anything, confirm the new render is **not
   byte-identical** to the prior (`md5sum`/`cmp`) **and** that your own vision sees the named change. If
   the re-render came back identical, it is **not** a new version — re-issue the edit or log "round N:
   no change, kept v(N-1)"; **never narrate an improvement that did not happen.** The log records the
   **observed** diff (what changed between renders), not the requested prompt edit; delete discarded
   intermediates so no stray `_vN.png` lingers. (DrawAI re-renders+revalidates every attempt; this is
   the lean analogue.)
   **MANDATORY trace (enforced by the gate).** For every image-model figure, run **≥2 rounds** and write
   each round's observed diff to `figures/repair_logs/<label>.log` (≥1 line; **never empty**). An empty or
   missing `repair_logs/<label>.log` for an image-model figure is a **stage-6 failure** —
   `run_gates.py <workdir> all` runs `check_figure_critique`, which fails on an empty trace,
   `critic_rounds < 2`, or missing grounding manifest fields. This is the fix for the historical
   "critique loop never ran / empty repair_logs" regression.
   **"Accept" here means the PNG is approved and ready to vectorize (step 5b)** — not yet inserted.
5b. **Vectorize via DrawAI HYBRID — the ONLY vectorizer, image-model figures only.** Vectorization is
   **`ts-figure-optimize`**'s DrawAI **HYBRID** and nothing else: SAM3 + PaddleOCR + Box-IR, then a
   deterministic **hybrid build** = the **approved render kept pixel-exact** (a whole-canvas raster) with an
   **editable `<text>` overlay** (~0.91 SSIM; 63 editable text boxes on the test figure). It is **key-free**
   (no Codex; the optional GPT text-correction is skipped with `--no-text-gpt`). This keeps the figure's
   richness EXACTLY — it IS the approved render — while making every label editable.
   **There is NO full-vector redraw and NO Claude-redraw fallback.** A redraw of a dense figure measurably
   loses fidelity vs the exact render (we tested it), so the rule is: **HYBRID, or else keep the PNG — never redraw.**
   **If the DrawAI runtime is not ready** (`drawai doctor` ≠ ok / models absent): ENVIRONMENT gap —
   **SELF-CONFIGURE it (do NOT ask first):** `python ../ts-figure-optimize/scripts/setup_drawai.py --device gpu`
   provisions it from **ModelScope (NO HF token)** — downloads SAM3/RMBG/PaddleOCR + builds the runtime venv
   (see `ts-figure-optimize` for the exact recipe + known fixes; perception runs on a GPU box and needs **no
   Claude/Codex account**). Then run + map in:
   ```
   python ../ts-figure-optimize/scripts/run_hybrid.py \
       --image figures/<label>.png --run-name <label> --device gpu --no-text-gpt
   python ../ts-figure-optimize/scripts/export_paper_figure.py \
       --run-dir runs/<label> --label <label> --figures-dir figures
   ```
   `export_paper_figure.py` writes self-contained `figures/<label>.svg` (render + editable text, base64-inlined)
   + `figures/<label>.pdf` and keeps the `.png`. Vectorize ONCE at this proposal/first-draft stage (the main
   schematic is results-independent; later experiment-phase figures are matplotlib born-vector and skip 5b).
   **Only if provisioning is genuinely impossible** (no GPU / no network after trying) → **KEEP the approved
   `figures/<label>.png` as-is** (insert the PNG; editability deferred, full richness preserved) and log it.
   Do NOT redraw, do NOT hand-author an SVG, do NOT degrade to a flat diagram — `check_figure_critique` blocks
   any non-`image-model` free-form figure (the carbon-paper regression).

   Then **lint** via ts-figure-optimize's gate (the suite's figure check):
   `python ../ts-figure-optimize/scripts/check_vector_pdf.py lint --svg figures/<label>.svg --type <type> --render-check`.
   A **hybrid passes** when its labels stayed **editable `<text>`** over the render — the whole-canvas render
   raster is **expected and fine** (that is what a hybrid is). The gate fails only a **textless raster** (a
   bare screenshot) or an editability-breaking element. (A kept PNG has no `.svg` to lint — that path is
   allowed by the DoD check as "unconverted, PNG kept".) **The hybrid is visually = the approved render (it
   IS the render); never a worse figure, never a deleted PNG.** (matplotlib figures skip 5b — born-vector from `finalize`.)
6. **Insert + record.** Replace the placeholder `\fbox{\rule…}` (only that token) with the
   **extension-less** `\includegraphics[width=\columnwidth]{figures/<label>}` — keep the existing
   `\caption`/`\label`; use `\textwidth` for a wide (`figure*`) float. Extension-less so pdflatex embeds
   the vector `figures/<label>.pdf` (and falls back to the kept `.png` if a `.pdf` is ever missing). Then
   **append this figure to `figures/figures.manifest.json`** — for an **image-model** figure record
   `{"label","type","engine":"image-model","reference_used":"<arxiv>#fig<n>",`
   `"grounding":"image-cond"|"vision-distill","critic_rounds":<int ≥ 2>}` — for a SCHEMATIC type the
   `reference_used`/`grounding` must be REAL (the gate FAILS `"none"`); only a `qualitative` scene may be `"none"`. A **matplotlib** figure
   records `{"label","type","engine":"matplotlib"}`.
   — so the DoD gate knows each figure's type: `run_gates.py all` calls `check_vector_pdf.py check`, which
   asserts every figure has an embedded artifact and that every **converted** figure's `.svg` is a **valid
   hybrid** (editable `<text>` over the render) — an unconverted figure that kept its PNG is allowed; and
   `check_figure_critique`, which asserts every image-model figure has a non-empty `repair_logs/<label>.log`,
   `critic_rounds ≥ 2`, and the `grounding`/`reference_used` fields (this is what blocks a flat hand-draw).

## Placeholder format (emitted by the write stage)
```latex
\begin{figure}[htb]\centering
%% FIGURE-SPEC type=architecture
%% DESC: one concise line — the exact boxes, arrows, and data flow, in the paper's own terms
\fbox{\rule{0pt}{3cm}\rule{0.9\columnwidth}{0pt}}
\caption{...}\label{fig:...}\end{figure}
```
`type` renderable: `{architecture, pipeline, framework, concept, schematic, overview, qualitative, diagram, flow}`;
skip-it: `{results, plot, curve, bar, chart}`. A legacy bare placeholder (no spec) still works — classify
it from the caption + context in step 1. The placeholder/FIGURE-SPEC is **unchanged** by vectorization —
the write stage emits the same `\fbox{\rule…}` token; only the inserted target is now an editable
vector PDF (step 6).

## Compile fit
Figures land in `<workdir>/figures/<label>.pdf` (the embedded vector) with `<label>.png` + the source
(`.plot.py` / `.svg`) kept alongside; `assemble_paper.py` compiles in `<workdir>` and the bundled
`.sty` already `\RequirePackage{graphicx}`, so the extension-less `\includegraphics{figures/<label>}`
resolves the `.pdf` (vector preferred over `.png` under pdflatex) with no extra wiring — and no
`\includesvg`/Inkscape dependency (cairosvg pre-renders SVG→PDF). If you re-run write/refine/review,
re-run this stage.

## Trace
Write `logs/6_figure.io.md` — INPUT (placeholders found: label / type / caption), DECISIONS (per figure:
SKIP+why, or **the GROUND reference chosen** (paper id + figure no + venue, or `none` + why) and the
`grounding` mode (`image-cond`/`vision-distill`/`none`), the final prompt + the per-figure critic round
count (also mirrored line-by-line in `figures/repair_logs/<label>.log`) + **the OBSERVED diff each render
round made** (not the requested edit — and never claim a round that produced a byte-identical render); for
method/architecture figures the **symbol→defining-module edge list** and the per-symbol semantic-
faithfulness verdict; **and the vectorize outcome** — branch = matplotlib born-vector vs image-model
HYBRID (editable text over the render) vs PNG-kept (DrawAI unavailable), with a one-line note), OUTPUT
(per figure the artifact set — `figures/<label>.pdf` (embedded vector) +
`.png` (kept) + source (`.plot.py` / `.svg`) — which `.tex` was edited, and the `figures.manifest.json`
entry). The kept `figures/<label>.prompt.txt` files are part of the trace.
