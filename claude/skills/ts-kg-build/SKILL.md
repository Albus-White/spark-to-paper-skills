---
name: ts-kg-build
description: Build a reusable, evidence-grounded research-pattern index from a real paper corpus. Use when multiple future Ideas in the same domain will benefit from shared recall, or when the user explicitly requests a knowledge graph. Skip for ordinary single-paper runs; web and source search are the default. Embeddings and clusters retrieve patterns but never prove novelty or scientific transferability.
---

# ts-kg-build

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md` and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

Build a KG only when its expected reuse justifies corpus extraction and embedding cost. Good triggers
include a maintained domain corpus, a planned series of papers, or explicit user request. A single
paper with a small search result set should use a flat evidence shelf instead.

## Procedure

1. Validate real corpus metadata and preserve source provenance.
2. Let the main model extract transferable problem, mechanism, assumptions, evidence pattern,
   failure mode, scope boundary, and Idea-evolution pattern. Do not force every paper into a reframe
   narrative or reject legitimate integration/system contributions by vocabulary.
3. Embed and cluster only when an endpoint is configured and the corpus is large enough to benefit.
   Otherwise emit an explicitly labeled flat shelf.
4. Let the main model name and summarize clusters from representative members. Cluster size and
   cosine similarity are retrieval signals, not quality or novelty judgments.
5. Run `kg_build.py` and `kg_lint.py` for IDs, edges, schema, hashes, and computed consistency.

Never fabricate abstracts, reviews, scores, edges, or cluster semantics. Preserve failed hypotheses
and negative evidence as distinct patterns so downstream recall does not mistake a compelling story
for current-domain support.
