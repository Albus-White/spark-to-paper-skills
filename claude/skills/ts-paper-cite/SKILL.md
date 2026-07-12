---
name: ts-paper-cite
description: Build and maintain a real, complete bibliography for the active research claims. Use for literature grounding, benchmark and evaluator sourcing, BibTeX creation, citation repair, or claim-to-source review. The main model judges relevance and support from primary sources; scripts verify metadata structure and citation-key wiring without citation-count quotas.
---

# ts-paper-cite

Use evidence need, not a reference quota, to determine bibliography size.

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md` and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Grounding pass before G3

Build a compact design source set: closest work, canonical task/protocol sources, official evaluator,
benchmark/dataset sources, strongest relevant baselines, and any domain guideline needed to judge the
design. Search and classify benchmark availability. This pass supports G1-G3; it is not the final
bibliography.

## Manuscript pass after claims stabilize

For each paper claim or necessary context statement:

1. Decide what kind of source would support or constrain it.
2. Search primary sources and authoritative metadata.
3. Read enough of the source to judge actual relevance. Titles, keywords, and embedding similarity are
   retrieval aids only.
4. Record full metadata and a short evidence note tied to the specific claim.
5. Stop when claims are adequately supported. Do not broaden into adjacent work solely to increase a count.

Prefer user-provided sources when valid, official benchmark/repository pages for protocol facts,
original papers for methods, and authoritative domain guidance for high-risk design choices. Preserve
uncertainty when metadata or support cannot be verified.

## Deterministic checks

Before sections exist, run:

```bash
python scripts/bib_integrity_lint.py <workdir>
```

This checks parseability, duplicate keys, and required metadata. It does not check whether a paper is
relevant.

After writing/refinement, run:

```bash
python scripts/citations_lint.py <workdir>
```

This checks that every `\cite{}` key exists and reports uncited entries as warnings. The main-model
review decides whether claims are properly supported and whether uncited sources should remain in a
research bibliography.

Never fabricate a paper, DOI, abstract, venue, page range, or claim-support relationship. A niche
topic with a small but complete evidence set is preferable to a padded bibliography.

If a lifecycle exists, `sync_pipeline.py ... cite` imports benchmark and bibliography artifacts but
does not pass G1/G2. Write separate scientific judgments from the raw sources.
