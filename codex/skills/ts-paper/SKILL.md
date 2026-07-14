---
name: ts-paper
description: >-
  Run one evidence-bound research-to-publication lifecycle from a raw seed, supplied proposal, or
  verified results. Use for end-to-end scientific paper work including field and venue calibration,
  Idea discovery, research design, optional governed execution, citations, planning, writing, review,
  figures, LaTeX, and release audit.
---

# ts-paper

Run one lifecycle under `<workdir>/research`. Every specialized skill contributes to that state; none
creates a parallel Idea, research program, result set, manuscript truth, or second paper pipeline.
Trust the main model with semantic and scientific judgment. Use deterministic code only for exact
facts such as schemas, hashes, source identities, budgets, process outcomes, metric recomputation,
citation wiring, artifact sets, and compilation.

Read the governing references in `../ts-research-lifecycle/references/` before acting, especially
`reasoning-and-validation-boundary.md`, `state-transition-table.md`,
`artifact-invalidation-rules.md`, and `bounded-execution-contract.md`.

## Choose one profile

- `proposal`: design and write without claiming unmeasured outcomes.
- `exploratory`: run bounded pilots; findings remain exploratory.
- `standard_empirical`: run claim-supporting acquisition, verification, pilot, confirmation, and
  reconciliation.
- `high_risk`: use the empirical path plus proportionate independent and human confirmation.

Initialize once with `scripts/init_research_run.py`. Do not upgrade for spectacle or downgrade to
avoid a validity requirement.

## Unified lifecycle

### 1. Preserve the request and resources

Register the user policy, literal Idea seed, target venue behavior, submission constraints, deadline,
compute/storage/API/financial limits, and review availability. Unknown values remain explicit; never
silently manufacture user confirmation. Credentials stay outside the research tree.

### 2. Build two distinct calibrations before design

Use a **science profile** to understand the topic. Search fresh primary literature from appropriate
leading field venues, read the relevant full text, and record closest work, benchmark landscape,
scientific conventions, evidence conventions, writing conventions, open questions, freshness, and
limitations. An optional immutable Paper Wiki snapshot may accelerate recall, but decisive claims
must return to primary sources and a fresh delta search.

Use a separate **venue profile** to understand the intended publication. Freeze inclusion/exclusion
criteria first, then acquire a comparable accepted-paper corpus from the target venue or a documented
leading-venue substitute. Inspect real PDFs for page and citation distributions, figure/table scale,
domain-specific figure roles, evaluation counts and kinds, evidence dimensions, and evaluation
difficulty. The sample is an observed calibration envelope, not a manuscript quota. Keep official
venue rules separate from empirical accepted-paper conventions.

### 3. Discover and select one active Idea

Invoke `ts-idea-discovery`. Produce evidence-grounded candidates from the seed, science profile,
fresh closest-work search, benchmark landscape, resources, and optional read-only memory. Include a
faithful seed candidate when appropriate. The main model compares falsifiability, scientific value,
false-novelty risk, feasibility, benchmark fit, and reasons each candidate may fail. Register one
selection judgment and one active Idea. A supplied proposal uses the same path with a faithful single
candidate; there is no narrative `story` artifact or automatic novelty score.

### 4. Ground claims and freeze a research program

Search applicable benchmarks, evaluators, datasets, repositories, counterexamples, and failure modes.
An applicable benchmark must be acquired and reproduced; an absent or incompatible benchmark is a
valid evidenced outcome, not permission to run an unrelated one.

The main model designs claim-linked `evaluation_units`. Units may be benchmarks, experiments,
simulations, observational analyses, qualitative studies, proofs, or artifact evaluations. Select the
program from the Idea's validity needs, field conventions, observed venue evidence scale, user
resources, and a measured dominant-cost feasibility probe. Venue observations calibrate completeness
but never dictate an irrelevant topology. Review estimands, comparison fairness, evaluator semantics,
leakage, confounders, positive and negative interpretation, and out-of-scope conclusions. Freeze only
after a G3 judgment and scoped `FREEZE_RESEARCH_PROGRAM` approval.

### 5. Execute a bounded evidence loop when required

Invoke `ts-paper-experiment` on the same root. Pin repositories and licenses, keep upstream code
read-only, govern adapters/patches, lock the actual local or remote environment, reproduce applicable
references, review implementation meaning, and run discriminative scientific tests.

Use pilot evidence to expose feasibility and protocol problems before confirmation. Classify each
failure before acting: infrastructure may retry; dependency/implementation requires a material repair
and renewed review; protocol changes reopen the research program; data/license/resource limits stop
or narrow scope; unsupported hypotheses remain negative evidence. Competing scientific alternatives
use bounded branches, never untracked metric chasing.

Evidence may revise the Idea. Editorial changes preserve evidence; scope, estimand, mechanism, or core
changes invalidate proportionate dependents. Test-informed Ideas require independent confirmation.

### 6. Reconcile claims and select publication targets

After design in proposal mode, or after evidence reconciliation in empirical modes, let the main
model select a publication contract inside the calibration envelope. It contains a page range,
relevant unique-citation minimum, total figure/table counts, section projection, per-figure
source-of-truth class, and explicit rationales. User and official venue constraints are hard; accepted
paper distributions are evidence. Choices outside the observed range require an explained deviation.
There is no global citation floor and no arithmetic-mean quota.

### 7. Build the manuscript once

Use `ts-paper-cite`, `ts-paper-plan`, `ts-paper-data` when measured facts exist, and `ts-paper-write`.
Draft the complete argument from stable claims and real sources, then use one holistic
`ts-paper-refine` pass. `ts-paper-review` examines the whole manuscript for claim/evidence alignment,
contradictions, method-result mismatch, alternative explanations, citation support, terminology and
notation drift, redundancy, filler, limitations, and venue fit. Close focused issues through delta
review rather than restarting the whole paper.

Internal hashes, gate ledgers, command transcripts, and audit inventories belong in the artifact
package, never in the reader-facing paper. Reproducibility text in the manuscript must be scientifically
useful to readers, not page filler.

### 8. Execute figures by source of truth

Use `ts-paper-figure` only after the figure program is frozen:

- `measured_evidence`: deterministic or original evidence, bound to canonical fact IDs;
- `original_observation`: the reviewed original scientific artifact;
- `exact_structure`: domain-native tools that preserve exact geometry, topology, notation, or apparatus;
- `explanatory_synthesis`: the real upstream PaperBanana Retriever→Planner→Stylist→Visualizer→Critic
  workflow, followed by DrawAI only when an approved raster lacks a born-vector source and preflight
  succeeds.

PaperBanana is not a label for a direct image-model call. Exact structures must not be distorted by
generative rendering, and explanatory figures must not bypass the upstream workflow with hand-drawn
boxes.

### 9. Compile, inspect, and release

Use `ts-paper-latex` for deterministic assembly and compilation. Then the main model must open the
actual final PDF and write the Publication Judgment, explicitly reviewing claim/argument consistency,
cross-section consistency, method-result alignment, redundancy and filler, internal-provenance
separation, limitations/negative results, figure roles, citation relevance, venue-scale substance,
and visible layout defects. The release audit binds that judgment and all exact verdicts to the current
artifacts.

Completion requires a valid lifecycle, current manuscript, passing exact checks, no unresolved
semantic blocker, and visible limitations. A negative or stopped research outcome is a valid terminal
result; it must not be tuned or rewritten into a positive paper.
