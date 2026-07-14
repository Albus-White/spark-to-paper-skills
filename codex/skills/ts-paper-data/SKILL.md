---
name: ts-paper-data
description: Convert verified lifecycle runs or user-supplied measured data into claim-bound manuscript evidence. Use for empirical result extraction, recomputation, tables, result prose, and plots. Canonical facts bind to run IDs, raw artifact hashes, aggregation code, and claims; the main model interprets scientific meaning while scripts verify exact provenance and manuscript locations.
---

# ts-paper-data

Use this skill only for real measured evidence. Read
`../ts-research-lifecycle/references/reasoning-and-validation-boundary.md` and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Canonical facts

For lifecycle runs, write facts to:

```text
research/evidence/results/results-manifest.jsonl
```

Each fact contains `fact_id`, `claim_ids`, `value`, `unit`, optional `display_value`, completed
`run_ids`, raw `source_artifacts` and hashes, plus aggregation method, code artifact, and code hash.
Do not promote exploratory, stale, failed, invalidated, or test-contaminated evidence.

For user-supplied results without executable runs, initialize the appropriate lifecycle profile and
freeze a claim-linked import/analysis evaluation unit. Register an immutable
`user_supplied_import` manifest that describes the import event, source hashes, and any recomputation;
it is provenance, not a claim that this suite executed the original study. Never label imported data
as a baseline, pilot, or confirmation run.

## Main-model interpretation

The main model reads raw outputs, protocol, uncertainty, subgroup/condition context, failed runs, and
claim registry. It decides what the measurements mean, whether comparisons are fair, which
limitations matter, and which claims should be supported, narrowed, contradicted, or left
inconclusive. A numerically valid result does not automatically justify a claim.

## Manuscript binding

Write result prose and tables only from canonical facts. Create `results_bindings.json` with the
canonical manifest hash and one binding per rendered fact location: artifact, line, displayed value,
artifact hash, and `fact_id`. Figures declare the same fact IDs in `figures.manifest.json`.

Run:

```bash
python scripts/validate_results_binding.py <workdir>
```

This proves that displayed values match current canonical facts and artifacts. The manuscript review
still judges whether the surrounding sentence, denominator, population, comparison, and uncertainty
are scientifically correct.

## Tables and plots

Choose tables and plots from the actual evidence question. Do not require a main table, ablation, or a
fixed number of figures. Use any reproducible renderer suited to the domain. Preserve data, script,
configuration, and output hashes. Follow the active venue typography rather than a global font rule.

Negative, null, mixed, or inconclusive findings remain visible. Never rewrite them into a positive
story or hide failed conditions.
