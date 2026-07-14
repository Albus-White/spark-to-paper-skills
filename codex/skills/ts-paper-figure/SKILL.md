---
name: ts-paper-figure
description: Execute the frozen v5 publication figure program by scientific source of truth. Use deterministic/original evidence for measured figures, original artifacts for observations, domain-native tools for exact structures, and the real upstream PaperBanana pipeline only for explanatory synthesis; use DrawAI conditionally after raster approval.
---

# ts-paper-figure

Read `../ts-research-lifecycle/references/bounded-execution-contract.md`, the lifecycle reasoning
reference, plus
`references/PAPERBANANA_NOTICE.md` and `references/paperbanana-quality-contract.md` before an
explanatory-synthesis route.

## Obey the frozen program

Read the active publication contract and `research/manuscript/figure-routing.json`. Do not choose a
new count or substitute a route because one is inconvenient. Accepted-paper statistics are already
represented in the contract's calibration envelope; they are not local figure quotas.

Every route preserves `figure_id`, class, claim IDs, section role, caption, source of truth, required
and forbidden content, renderer rationale, formats, typography, and accessibility. Contract,
blueprint, routing, manifest, and LaTeX ID sets must match exactly.

## Route by source of truth

### `measured_evidence`

Use deterministic code, a domain-native renderer, or an original evidence visualization. Bind every
reported value to canonical `fact_ids`, data/aggregation artifacts, and the active venue typography.
Do not send measured results through a generative image model.

### `original_observation`

Publish the registered scientific observation or a faithful non-semantic conversion: microscopy,
field image, spectrum, scan, map, specimen image, qualitative excerpt, or domain equivalent. Preserve
the original artifact and disclose processing. Generative beautification must not alter evidence.

### `exact_structure`

Use the tool that owns the exact representation: TikZ, Graphviz, CAD, GIS, chemical drawing,
mathematical plotting, circuit/graph tooling, domain simulation output, or another justified native
renderer. Preserve topology, geometry, notation, units, and constraints. PaperBanana is inappropriate
when visual generation could change the scientific object.

### `explanatory_synthesis`

Use the actual external PaperBanana/PaperVizProcessor workflow. A direct image-model call, hand-drawn
flowchart, manually claimed stage record, or renamed output is not PaperBanana.

## Explanatory-synthesis workflow

1. Create the known pipeline directory `figures/<figure-id>.pipeline` and run one DrawAI preflight
   with `record_drawai_preflight.py`. Register the resulting available/unavailable evidence in the
   figure route. DrawAI availability affects only post-approval editability.
2. Initialize from the frozen route:

```bash
python scripts/run_paperbanana_pipeline.py init <workdir> <figure-id>
```

3. Search accepted-paper visual precedent. Begin with the science and venue corpora, then add closer
   primary papers when needed. Open the actual figures and write `references/retrieval.json` with
   queries, attempted sources, inspected candidates, source identities, images, content, visual
   intent, conventions, selection/rejection reasons, and reviewer. Search is required; selecting a
   weak reference is not. `NO_SUITABLE_REFERENCE` is valid with an evidenced rejection summary.
4. The main model writes `paperbanana/semantic_plan.json`: communication goal, visual story,
   panel/spatial blueprint, domain objects, semantic edges, field conventions, text strategy,
   anti-generic strategy, required/forbidden content, reference decision/hash, and justified
   minimalism choice.
5. Write `paperbanana/input.json` from that reviewed plan. It must include a substantive
   `content_derivation`, the frozen caption and candidate budget, bounded critic rounds, selected
   models/style guide, and exact hashes of the semantic plan and retrieval record. This binding
   prevents the real upstream execution from bypassing the reviewed semantics.
6. Execute the pinned upstream checkout:

```bash
python scripts/run_paperbanana_pipeline.py execute figures/<figure-id>.pipeline \
  --paperbanana-root <PaperBanana-checkout>
```

The adapter records upstream origin/commit/dirty status, input/style/reference/semantic hashes,
worker report, and per-candidate Retriever, Planner, Stylist, Visualizer, and Critic traces. Candidate
count is model-selected from visual uncertainty and resources, then bounded by the route. Candidates
must explore materially distinct compositions when more than one is requested.

Use a Python 3.12 virtual environment created from the upstream `requirements.txt`. Configure a
provider through PaperBanana's supported `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or
`OPENROUTER_API_KEY` interface (and `OPENAI_BASE_URL` when supported by the OpenAI client). Legacy
`TS_FIG_*` variables do not establish a PaperBanana text-and-image provider. The adapter checks model
and provider compatibility before any generation call.
7. Open all actual candidate images. Write `selection.json` with the selected upstream candidate,
   final path/hash, rationale, and quality comparison for multi-candidate runs.
8. Use a fresh critic context to open the selected image and write
   `critique/final_vision_review.json`. Judge semantic fidelity, visual specificity, information
   hierarchy, field-convention alignment, anti-genericness, legibility, integrity, selected-reference
   comparison, and visible defects. Explicitly diagnose generic box-flowchart degeneration. Repair
   concrete defects within a bounded loop; do not pass an image because labels are merely spelled
   correctly.
9. If DrawAI preflight passed and no born-vector source exists, reconstruct only the scientifically
   approved raster with `ts-figure-optimize`; bind SVG/PDF/PPTX and vector review to the raster. If
   unavailable, preserve the evidenced skip and publish the reviewed raster. Never replace the skip
   with an unaudited hand schematic.
10. Validate:

```bash
python scripts/run_paperbanana_pipeline.py validate figures/<figure-id>.pipeline
```

## Publication manifest

Write `figures/figures.manifest.json` with each `figure_id`, class, route, source of truth, renderer,
published raster/vector, visual review, pipeline directory when applicable, DrawAI status, and fact
IDs for measured evidence. Every published artifact receives an actual-image review bound to its
hash. Never invent results, labels, arrows, nodes, geometry, regions, or examples.
