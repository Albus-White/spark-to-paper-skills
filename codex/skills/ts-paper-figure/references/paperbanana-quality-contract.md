# PaperBanana quality contract

The main model owns visual semantics and quality. Deterministic checks prove source identities,
bindings, stage execution, candidate sets, artifact hashes, and review freshness; they do not assign an
aesthetic score.

## Reference record

`references/retrieval.json` records search queries, attempted accepted-paper/primary sources, opened
candidates, source identity, local image, scientific content, visual intent, selection reason, and
field conventions. Its decision is `SELECTED` with exact IDs or `NO_SUITABLE_REFERENCE` with a
rejection summary. Retrieval similarity may order inspection but cannot make the decision.

## Reviewed semantics

`paperbanana/semantic_plan.json` records:

- figure ID, communication goal, visual story, and concrete panel/spatial blueprint;
- semantic edges, concrete domain objects, and field visual conventions;
- text, hierarchy, and anti-generic strategies;
- required and forbidden content;
- retrieval hash and selected/no-reference decision;
- `RICH_DOMAIN_SPECIFIC` or a precedent-backed `JUSTIFIED_MINIMAL` decision.

`paperbanana/input.json` is the only content consumed by the upstream Planner. It must bind the exact
semantic-plan and retrieval hashes, repeat the frozen caption and candidate budget, explain how its
content was derived from the reviewed plan, select bounded critic rounds/models, and reference the
field-specific style guide. A stale or unbound input fails before execution.

## Real upstream execution

`paperbanana/run.json` must be written by `execute_paperbanana.py` and declare
`executor: upstream_papervizprocessor_adapter`. It binds the upstream Git identity, Python runtime,
input, semantic plan, retrieval record, style guide, worker report, candidate count, and successful
return code. Every candidate must contain actual traces proving Retriever, Planner, Stylist,
Visualizer, and Critic ran, plus a readable final image and hash.

Manual JSON claiming those stages, a direct image-model call, or a candidate without all five traces
cannot pass.

## Selection and final review

`selection.json` may select only an executed upstream candidate and must bind the final image/hash.
When several candidates exist, compare their actual images on semantic fidelity, visual specificity,
information hierarchy, reference alignment, and the reason for selection.

`critique/final_vision_review.json` comes from a fresh context that opened the selected image. It binds
the image hash and records minimal context. It separately reviews semantic fidelity, specificity,
hierarchy, field conventions, anti-genericness, legibility, and integrity with visible evidence. It
must explicitly decide whether the image degenerated into a generic box flowchart, compare selected
references when present, and retain no blocking issue.

Focused repair records bind input/output hashes, observed visual changes, regression checks, and the
accept/reject decision. Candidate and repair counts remain adaptive but bounded; repeated states or no
material progress stop the loop.

## Conditional DrawAI

An available preflight requires reconstruction of the approved raster and hash-bound SVG/PDF/PPTX
plus actual-vector review. An unavailable preflight requires the attempted command/configuration,
observed error, rationale, and reviewer. DrawAI never changes scientific semantics and is not applied
to an existing correct born-vector or domain-native figure.

