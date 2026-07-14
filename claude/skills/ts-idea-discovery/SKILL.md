---
name: ts-idea-discovery
description: Discover, compare, and select falsifiable research Idea candidates from a raw seed, fresh primary literature, applicable benchmarks, and an optional read-only Paper Wiki snapshot. Use before freezing the active lifecycle Idea. Produces candidates and a model-authored selection judgment, never a narrative story, novelty score, or automatic novelty claim.
---

# ts-idea-discovery

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md`,
`../ts-research-lifecycle/references/bounded-execution-contract.md`, and
`../ts-research-lifecycle/references/idea-discovery-contract.md`.

## Preserve the seed

Register the user's literal research seed before expanding it. Separate direct user statements,
reasonable interpretations, unresolved ambiguity, and constraints. Do not replace the seed with a
more fashionable problem or infer desired positive findings.

## Build candidates from evidence

Use the current science profile and a fresh closest-work search. Read full primary sources when a
candidate depends on details outside the abstract. Search for established formulations, counterexamples,
benchmarks, evaluators, datasets, repositories, and known failure modes.

An optional Paper Wiki snapshot may supply remembered papers, concepts, and gaps. Treat it as retrieval
memory, not authority. Check its source cutoff and limitations, then run a fresh delta search. Never
write to the wiki during candidate selection and never let a post-selection wiki update mutate the
active Idea.

Create `research/discovery/idea-candidates-vNNN.json`. Each candidate records the problem, testable
hypothesis, mechanism or explanatory basis, scope, assumptions, falsifiers, tentative claims,
alternative explanations, minimum validation path, closest-work comparison, source evidence, and
reasons it may fail. Include faithful `KEEP_SEED` and `NARROW_SEED` candidates when warranted; do not
force recombination or a novelty trope.

## Select once, then register

Compare candidates on scientific value, falsifiability, evidence gap, feasibility, benchmark fit,
resource fit, and risk of false novelty. The main model writes
`research/discovery/idea-selection-vNNN.json` with pairwise distinctions, evidence, uncertainty,
rejected alternatives, and the selected candidate. Similarity and retrieval scores may order reading;
they cannot select the Idea.

Register only the selected candidate as the lifecycle active Idea. Candidate and selection artifacts
remain immutable provenance, not parallel scientific truth. A complete supplied proposal still uses a
single faithful candidate so its assumptions and closest work are explicit.

Stop rather than inventing novelty when no candidate is sufficiently grounded, falsifiable, or feasible.
An incremental or negative candidate is valid when honestly characterized.

