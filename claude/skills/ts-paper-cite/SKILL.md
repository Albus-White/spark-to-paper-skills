---
name: ts-paper-cite
description: Search, inspect, and maintain the real sources required by science calibration, venue calibration, research design, and the frozen publication contract. The main model judges relevance and support; deterministic tools verify metadata, citation keys, artifact wiring, and the selected unique-citation minimum.
---

# ts-paper-cite

Read `../ts-research-lifecycle/references/bounded-execution-contract.md` and the lifecycle reasoning
reference. Never fabricate metadata, source
content, acceptance status, or a claim-support relationship.

## Keep three source purposes distinct

1. **Science profile corpus:** current primary papers from appropriate leading field venues. Use it
   to understand closest work, scientific/evidence conventions, benchmarks, and topic-specific
   writing practice.
2. **Venue calibration corpus:** comparable accepted papers from the target venue, frozen before
   acquisition. Use it to observe publication scale and official/empirical venue conventions.
3. **Manuscript bibliography:** sources that support actual sentences, comparisons, definitions,
   protocols, limitations, and claims in this paper.

A paper may serve more than one purpose, but the artifacts and selection rationales remain distinct.
Do not inflate a target-venue sample with merely related papers or treat a field-style corpus as an
acceptance sample.

## Before research-program freeze

Search closest work, canonical formulations, counterexamples, datasets, evaluators, benchmark and
author repositories, strongest comparators, and domain guidance needed to judge the design. Read the
relevant full text when the decision depends on details beyond title or abstract. Record benchmark
compatibility, license/access status, and valid no-benchmark outcomes. This compact design set
supports Idea selection and G1-G3; it is not the final bibliography.

## After claims stabilize

For every material manuscript statement:

1. identify the evidence type required;
2. prefer the primary or authoritative source;
3. inspect enough source content to judge local support and limitations;
4. record verified metadata, inspected scope, supported claim IDs, intended sections, and an evidence
   note;
5. cite the source where it actually supports text.

The publication contract's minimum is selected by the main model from claim coverage, topic breadth,
user requirements, official rules, and the observed venue citation distribution. There is no global
floor. Meeting the number never authorizes padding. If adequate claim support and the selected venue
scale cannot be reconciled honestly, reopen the publication contract or venue/Idea fit decision.

## Exact checks

Before drafting:

```bash
python scripts/bib_integrity_lint.py <workdir>
```

After drafting/refinement:

```bash
python scripts/citations_lint.py <workdir>
```

The tools verify BibTeX integrity, unique keys, coverage-map equality, in-text key existence, and the
selected actual-citation minimum. They cannot decide whether a source truly supports a sentence. The
main model performs that semantic review and preserves uncertainty when support or metadata remains
limited.
