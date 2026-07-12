# Spark-to-Paper Research Lifecycle v3

This document describes the implemented architecture shared by the Codex and Claude Code
distributions. It is an execution contract, not a roadmap.

## 1. Design objective

The suite must answer two different questions without confusing them:

1. **Is the research decision scientifically defensible?** The main model answers this from the
   relevant literature, code, protocol, runs, and limitations.
2. **Are the supporting facts and artifacts exact?** Deterministic tools answer this with schemas,
   hashes, source paths, run IDs, citation keys, and compilation results.

A file existing does not prove that its science is correct. A model judgment does not override a
failed hash, missing source, stale run, or failed compilation.

## 2. Single source of research truth

Every nontrivial run owns one `research/` directory managed by `ts-research-lifecycle`. It contains:

- a versioned active Idea and Idea lineage;
- claims and their status;
- the frozen Claim-Experiment Contract;
- repository, dataset, benchmark, and environment locks;
- run manifests and failure classifications;
- evidence records and canonical result facts;
- G0-G16 gate reports and structured scientific judgments;
- invalidation and rollback history.

Paper stages consume this state. They do not create a second experiment tree or independently decide
that evidence is valid.

## 3. Model and code boundary

### Main model owns

- novelty and related-work coverage;
- benchmark relevance and protocol fit;
- experimental design validity;
- implementation meaning and algorithmic fidelity;
- risk-specific verification test selection;
- failure classification when facts alone are insufficient;
- mechanism diagnosis and Idea revision;
- claim calibration and manuscript review;
- figure semantics and renderer choice.

These decisions use the `scientific_judgment` contract: conclusion, checks, evidence, limitations,
reviewer identity, and counterfactual triggers for any `NOT_APPLICABLE` verdict.

### Deterministic tools own

- JSON/schema validity and required fields;
- file existence, hashes, and identity binding;
- repository commit and environment lock records;
- command exit status and measured run provenance;
- citation metadata structure and manuscript cite-key wiring;
- canonical result-fact bindings;
- image/vector identity and actual-image review hashes;
- LaTeX assembly and compilation.

Regexes, fixed scores, word counts, citation counts, and file presence never decide scientific gates.

## 4. Profiles and legal phase paths

The lifecycle selects the smallest profile that can support the intended claims.

### Proposal

`INTAKE -> IDEA_DRAFTED -> IDEA_GROUNDED -> RESEARCH_CONTRACT_FROZEN -> MANUSCRIPT_HARDENED -> RELEASED`

No measured empirical claim is allowed. Empirical execution gates are not required.

### Exploratory

Adds a feasibility probe, pilot execution, mechanism diagnosis, an Idea decision, and calibrated
claims. It is suitable for deciding whether an Idea deserves a full study.

### Standard

Runs the complete empirical path: repository/environment locks, baseline reproduction, adaptive code
verification, pilot, bounded full experiments, canonical results, mechanism diagnosis, Idea decision,
claim update, manuscript hardening, and release.

### High risk

Uses the standard path plus independent confirmation for consequential design, implementation,
mechanism, and release decisions. Final release also requires an explicit human approval bound to the
active Idea and evidence hashes.

## 5. Contract freeze

The Claim-Experiment Contract is frozen only after:

1. the active Idea and claims are registered;
2. grounding and benchmark classification exist;
3. G3 has a passing model scientific judgment;
4. an approval record with action `FREEZE_CONTRACT` is scoped to the active Idea and binds the G3
   evidence;
5. empirical profiles register a user-provided or user-confirmed resource envelope covering deadline,
   compute, cost, storage, review availability, priorities, and constraints;
6. empirical profiles bind that envelope's current hash and include a measured feasibility microprobe
   showing deadline, budget, and backend viability.

The main model allocates the user's envelope to the evidence needed by the active claims. The system
does not invent a default research budget. The string `APPROVED` is not an approval record.

## 6. Repository and benchmark governance

The system prefers official benchmark and author repositories, then records exact commits, remotes,
licenses, patches, submodules, data versions, and environment details. Existing repositories are not
silently upgraded. Conflicts are resolved in an isolated working copy and the resulting diff is
reviewed and hashed.

Benchmark search happens during grounding. A benchmark can be classified as official, author,
adjacent, unavailable, incompatible, access-restricted, or license-restricted. “No valid benchmark”
is acceptable only with search scope, evidence, rationale, and a concrete alternative evaluation.

## 7. Adaptive implementation verification

There is no universal checklist that proves all algorithms correct. The main model first identifies
implementation-specific risks, then selects executable tests whose oracles can expose those risks.
Examples include reference-output comparison, invariance, conservation, dimensionality, gradient,
numerical stability, leakage, seed, split, and metric recomputation checks.

The deterministic validator proves that every declared applicable risk is covered by passing evidence.
An omitted test needs a rationale and a counterfactual trigger. G7 records implementation review; G8
records this adaptive verification suite.

## 8. Bounded experiment loop

Empirical execution follows:

`pilot -> observe -> classify -> repair/revise -> rerun -> stop`

Failures are separated into environment, code, protocol, resource, stochastic, and method-evidence
classes. Environment or code faults may be repaired and rerun. Protocol defects return to design
review. Evidence that the method is ineffective is retained as evidence and can narrow, revise, or
reject the Idea; it is not tuned away to obtain a favorable result.

Every iteration records what changed, why, the affected artifacts, the budget consumed, and the stop
condition. Test-set access and run budgets remain bounded.

When multiple plausible alternatives remain, the lifecycle can open a bounded branch ledger. Each
branch carries a scientific question, parent delta, authorized contract experiment IDs, expected
positive and negative observations, cost, run IDs, and a model evaluation. Branch selection favors
validity and discriminating information over a scalar metric; negative branches remain evidence.

## 9. Idea evolution and invalidation

Idea changes are explicit levels:

- `L0`: editorial wording only;
- `L1`: scope or population change;
- `L2`: estimand, protocol, or evaluation meaning change;
- `L3/L4`: core mechanism or research-question change.

The lifecycle invalidates only artifacts whose meaning depends on the change and rolls back to the
nearest legal phase for the active profile. Old evidence remains in history but cannot silently support
the new Idea. Negative results can therefore produce a narrower or revised Idea without rewriting
history.

## 10. Canonical results and manuscript binding

Measured findings live in `research/evidence/results/results-manifest.jsonl`. Every fact binds:

- `fact_id` and active claim IDs;
- value and unit;
- completed run IDs;
- raw source paths and hashes;
- aggregation code and hash;
- active Idea and contract versions.

Manuscript result bindings point to these facts and identify the rendered value and source location.
Code verifies the identity chain; model review decides whether each fact actually supports the prose
claim and whether uncertainty and limitations are honestly stated.

## 11. Manuscript pipeline

After the evidence state is stable, the paper runs one manuscript pipeline:

`plan -> cite -> data binding -> write -> refine -> review -> figure -> latex`

Before planning, the main model studies official target-venue guidance, representative accepted papers
with a similar archetype, and relevant field conventions. `venue-study.json` records the sources,
explicit user requirements, observations, and design decisions. Observed paper counts are context, not
quotas; the model chooses experiment reporting breadth, sections, tables, and figures for this paper.

- Blueprint sections are selected from the research and venue; templates only force sections that the
  venue marks required.
- Bibliography integrity is checked before writing; cite-key usage is checked after writing. There is
  no citation quota.
- Draft lint catches exact structural faults and placeholders. It does not treat all numbers or Unicode
  as fabricated evidence.
- Whole-paper scientific review is primary. Fresh independent review scales with risk, uncertainty,
  and material disagreement; fixes use focused delta closure.
- Figures choose a truthful domain renderer and a candidate budget justified by the user resource
  envelope and unresolved visual uncertainty. References are optional. The final reviewed artifact is
  hash-bound to the published artifact.
- LaTeX assembly fails closed on missing template inputs and ignores stale compile verdicts whose input
  hash no longer matches.

## 12. Security and artifact boundary

The manuscript package is allowlisted: LaTeX sources, bibliography, template assets, sections,
figures, and publication assets. Research state, raw data, code, caches, credentials, and private keys
are excluded. Credentials belong in user-owned secret stores and environment variables, never in
`research/` or deliverables.

## 13. Completion meaning

“Complete” means the active profile reached its legal release phase, all required scientific judgments
are present, all exact gates pass against current hashes, stale evidence is absent, and unresolved
limitations are disclosed. It does not mean that the method achieved a positive result.
