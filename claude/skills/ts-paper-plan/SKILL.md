---
name: ts-paper-plan
description: Create blueprint.json after the active claims and v5 publication contract are stable. The main model chooses a domain-appropriate scientific argument and section organization; deterministic checks enforce the frozen section, figure, table, venue, and provenance sets.
---

# ts-paper-plan

Plan the paper the evidence needs. A venue template controls submission structure and formatting; it
does not decide the scientific argument.

Read `../ts-research-lifecycle/references/bounded-execution-contract.md` and
`../ts-research-lifecycle/references/reasoning-and-validation-boundary.md`.

## Preconditions

- The active Idea, claims, limitations, and research program are stable enough to write.
- Proposal mode contains no claimed measured outcomes.
- Empirical modes have reconciled canonical facts and claim wording.
- `template.json` selects user-provided or official venue assets without fallback.
- The publication contract contains model-selected targets and rationales derived from the observed
  calibration envelope, user requirements, and official rules.

## Main-model planning

Read the full science profile, venue profile and judgment, active Idea and claims, research program,
canonical facts, bibliography coverage, publication contract, and limitations. Choose the actual
paper archetype: method, empirical finding, negative result, replication, theory, simulation,
observational study, qualitative study, dataset/benchmark, system, application, or another justified
form.

Build one claim-to-section argument:

- select section IDs, titles, order, purpose, and semantic roles appropriate to the domain;
- ensure every essential claim has a planned explanation and evidence location;
- keep terminology, assumptions, notation, protocol, outcomes, and limitations connected across
  sections;
- reserve space for alternative explanations, negative evidence, boundary conditions, and genuine
  reader questions;
- use target word ranges only as editing guidance.

Do not force an `experiments` section, a contribution count, a main table, an ablation, or a fixed
subsection pattern. Do not add appendices or sections merely to reach a page range.

## Frozen artifact sets

`blueprint.json` must use the publication contract's exact section, figure, and table IDs. A changed
set requires a new publication contract; it is not a local blueprint repair.

For each figure preserve its frozen class, route, source of truth, claim bindings, purpose, and
section role:

- `measured_evidence`: canonical result facts and `fact_ids`;
- `original_observation`: registered original scientific artifacts;
- `exact_structure`: exact domain-native source artifacts;
- `explanatory_synthesis`: frozen semantics for PaperBanana.

Measured tables use `source_of_truth: canonical_result_facts`, fact IDs, and a data source. Proposal
mode cannot plan measured evidence.

Write section-level citation needs, equations/notation only when used, limitations/disclosure plans,
and the title/keywords permitted by the venue. Then run:

```bash
python scripts/template_lint.py <workdir>
python scripts/blueprint_lint.py <workdir>
```

Fix exact set, template, and provenance failures. Semantic organization remains main-model judgment.
If the research cannot honestly support the frozen artifact scale, reopen the publication contract
instead of inventing content.
