---
name: ts-idea2story
description: Turn a raw research idea into a faithful, falsifiable, literature-grounded research story and citation seed. Use when the user has an idea rather than a complete proposal. The main model compares closest work, preserves explicit versus inferred assumptions, identifies plausible mechanisms and alternatives, and proposes a minimum validation path without forcing a novelty trope or fabricating results.
---

# ts-idea2story

Build a compact research story, not a finished paper and not an automatically novel claim.

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md` and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Outputs

- `idea_brief.json`: user-stated motivation, constraints, explicit assumptions, separately labeled inferred assumptions.
- `story.json`: title, abstract, problem framing, gap, solution, method skeleton, candidate claims, evaluation plan, and `research_hypothesis`.
- `story_proposal.md`: readable projection.
- `retrieved_papers.json`: real closest-work and evaluation sources with provenance.
- `novelty_report.json`: nearest-work retrieval signal, never a novelty verdict.

## Procedure

1. Preserve the literal Idea. Clarify only what is needed to make it falsifiable; do not turn thin
   input into invented user intent.
2. Search for closest work, counterexamples, established task formulations, benchmarks, evaluators,
   datasets, and competing explanations. Use an existing KG only when it is already available and
   useful; do not build one for a single run by default.
3. Read source abstracts or primary pages. Record real metadata and distinguish verified abstracts
   from missing ones.
4. Let the main model compare the Idea with the nearest works at claim level: shared assumptions,
   mechanism, scope, predicted behavior, and required evidence. Embedding similarity only retrieves
   neighbors.
5. Construct the strongest faithful story supported by the Idea and evidence. Combination,
   integration, reframing, theory, system design, dataset work, or application work are all legitimate
   when scientifically justified. Do not force preferred verbs, title styles, architecture forms, or
   novelty narratives.
6. State assumptions, falsifiers, alternative explanations, scope limits, and the minimum validation
   path. Candidate claims remain tentative until lifecycle evidence supports them.
7. Run one holistic critique for faithfulness, plausibility, discriminative value, and evidence gaps.
   Refine once when the critique identifies a material, fixable defect. A second pass is allowed only
   after new evidence or a changed scientific object; repeated wording changes are not progress.
8. Run `story_lint.py` for schema and placeholder integrity. Run `novelty_check.py` only to retrieve
   semantically close sources. The main model writes the final novelty comparison.

Never fabricate papers, abstracts, result numbers, benchmark availability, or user intent. A story may
conclude that the Idea is incremental, underspecified, untestable, or better framed as a proposal.

If a lifecycle exists, import the story with `sync_pipeline.py ... story`. Synchronization registers
the Idea and G0 only; later scientific gates require model judgments.
