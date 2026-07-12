---
name: ts-paper-plan
description: Plan the manuscript structure after the research question and evidence profile are stable. Use to create blueprint.json for a proposal or evidence-backed paper in the active venue template. The main model chooses the paper archetype, sections, contributions, tables, and figures from the actual work; deterministic checks validate only structure, venue limits, and result provenance declarations.
---

# ts-paper-plan

Plan the paper the research needs. Do not use a venue template as a scientific outline.

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md`,
`../ts-research-lifecycle/references/adaptive-design-budget.md`, and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Preconditions

- Proposal: G3 is frozen and no measured outcomes are claimed.
- Exploratory/empirical: the active Idea decision and claim reconciliation are stable enough to write.
- `template.json` is explicitly selected and validated. Never silently fall back to another venue.

## Main-model planning

1. Identify the paper archetype from the research: method, empirical finding, dataset/benchmark,
   systems, application, theoretical, negative result, replication, or another justified form.
2. Search the user-selected venue's official guidance and recent accepted papers with a similar
   archetype/evidence type. If no venue is specified, study relevant leading venues/journals before
   choosing one. Record sources, observed conventions, user-specified counts, and model decisions in
   `venue-study.json`. Observed counts are context, not quotas.
3. Read the active claims, evidence, limitations, resource envelope, venue study, and page budget.
4. Choose section IDs, titles, order, and semantic roles. `experiments` is not a reserved ID; use roles
   such as `framing`, `related_work`, `methods`, `evaluation`, `results`, `discussion`, and
   `limitations` so downstream tools remain domain-independent.
5. State only the contributions the evidence supports. No fixed count applies unless the venue itself
   has an explicit formal requirement.
6. Let the model decide figure count, table count, experiment reporting breadth, and visual composition
   from the venue study and this paper's evidence. Follow explicit user counts when feasible and honest.
   Plan each artifact only when it materially improves understanding; no internal quota applies.
7. For measured figures/tables, declare `source_of_truth: measured_data`, `fact_ids`, `data_source`,
   and an appropriate renderer. Proposal mode must not declare measured results.
8. Treat target word ranges as editing guidance, not scientific acceptance criteria.

Write `blueprint.json` with:

- `paper_title`, authors/venue metadata, `venue_study`, and keywords when the venue supports them;
- `section_order`;
- `sections.<id>.title`, `roles`, purpose, claims/evidence to cover, optional target words,
  citation needs, tables, and figures;
- notation and terminology only when the paper uses them;
- limitations and disclosure plan.

Run:

```bash
python scripts/template_lint.py <workdir>
python scripts/blueprint_lint.py <workdir>
```

Fix structural errors. Treat word-target warnings and optional venue suggestions as advice for the
main model. Do not add content, references, tables, or figures merely to satisfy a count.
