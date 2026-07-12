---
name: ts-paper-figure
description: Create only the publication figures the paper needs using an adaptive, evidence-bound renderer workflow. Use for measured plots, architecture and mechanism diagrams, domain-native visualizations, qualitative evidence, maps, graphs, or image-model figures. The main model selects renderer, references, and candidate budget; scripts verify data/fact provenance, render hashes, actual-image review, vector artifacts, and published identity.
---

# ts-paper-figure

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md`,
`../ts-research-lifecycle/references/adaptive-design-budget.md`, and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Decide whether a figure is needed

The main model inspects the manuscript and chooses figures that materially communicate method,
evidence, mechanism, domain structure, or failure behavior. There is no minimum figure count. Remove a
figure that duplicates a table or prose without adding understanding.

## Choose the truthful renderer

Select the renderer from the semantic source of truth:

- measured data: matplotlib, seaborn, domain plotting tools, GIS, or another reproducible renderer;
- exact graph/flow/dependency structure: Graphviz, networkx, TikZ, Mermaid, or domain-native tools;
- geometry, circuits, scientific apparatus, or maps: a suitable code/domain renderer;
- real qualitative evidence: the original images with reproducible annotation;
- novel illustrative concept with no exact code representation: image model, followed by actual-image review;
- vector reconstruction of an approved raster: `ts-figure-optimize`.

Do not ban a renderer by figure label. Record why the chosen renderer best preserves meaning.

## Adaptive pipeline contract

For each figure create `figures/<label>.pipeline/` containing:

- `figure_contract.json`: semantic type, source of truth, renderer/rationale, caption, required and
  forbidden content, data sources and fact IDs when measured;
- `search_plan.json`: `direct` or `candidate_search`, a model-selected candidate budget justified by
  the user resource envelope and unresolved visual uncertainty, its run-specific safety cap and
  resource basis, stop conditions, and whether visual references are useful;
- `renders/render_manifest.json`: actual output paths and hashes;
- `selection.json`: selected render, comparison rationale when needed, final path and hash;
- `critique/final_vision_review.json`: a reviewer that opened the actual image, question-level checks,
  limitations, and blocking issues;
- optional hash-bound repair rounds with observed changes and regression checks.

Use one direct render for deterministic low-uncertainty figures. Use multiple candidates only when
layout or generative uncertainty benefits from comparison. Add candidates after a concrete unresolved
defect, not to satisfy a quota. References are optional and selected for relevance, never fixed Top-K.

Run:

```bash
python scripts/validate_pipeline.py figures/<label>.pipeline
```

## Publication artifacts

Write `figures/figures.manifest.json` with label, source of truth, renderer, pipeline directory,
published raster/vector paths, and fact IDs for measured figures. The final paper artifact must match
the reviewed image/vector hash.

Use the active venue's typography and accessibility requirements. Preserve real data and labels.
Never invent a result, arrow, node, region, or qualitative example. DrawAI is available for semantic
SVG/PDF/PPTX reconstruction when useful; it is not mandatory for already-correct born-vector output.
