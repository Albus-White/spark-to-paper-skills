---
name: ts-paper-experiment
description: Execute the empirical branch of one existing v5 research lifecycle. Use after a grounded active Idea, approved frozen research program, and measured feasibility probe to acquire governed code/data, reproduce applicable references, review implementation meaning, run bounded evaluation units, diagnose failures and mechanisms, evolve Ideas, and produce canonical facts.
---

# ts-paper-experiment

Operate only on `<workdir>/research`. Read
`../ts-research-lifecycle/references/bounded-execution-contract.md` and the lifecycle references for
repository governance, remote execution, scientific sanity tests, branching, and invalidation.

## Acquire the right implementation

Read the benchmark decision and each frozen evaluation unit. Prefer, in order, the applicable official
benchmark/author repository, a maintained compatible implementation, a documented adaptation, or the
minimum local implementation needed when no suitable code exists. An applicable benchmark must be
acquired and reproduced; absence or incompatibility must be evidenced rather than hidden by an
unrelated benchmark.

Pin origin, full commit, license, submodules, checkpoints, dataset/evaluator versions, and expected
behavior. Keep upstream checkouts read-only. Put integrations in `code/integration`, adapters in
`code/adapters`, and unavoidable upstream changes in a hash-bound patch stack or explicit fork.

Resolve dependency or version conflicts by tracing required behavior: compare APIs, tests, published
configuration, evaluator semantics, and affected outputs. Record the selected resolution and verify it
against reference behavior. Never choose a side merely because it is newer or installs cleanly. An
upstream or environment change creates a new lock and invalidates affected executable evidence.

## Lock execution and reproduce references

Select local or remote execution before formal runs. Lock backend, target, environment fingerprint,
OS, language/runtime, framework/toolchain, dependencies, hardware, and relevant drivers. A backend
switch is an environment change, not an infrastructure retry. Credentials remain outside lifecycle
artifacts.

Reproduce the applicable baseline or reference under its official task, split, preprocessing,
evaluator, checkpoint, and configuration before evaluating the new method. The main model judges
comparability; code recomputes exact outputs. When no valid reference is applicable, G6 may be
`NOT_APPLICABLE` only with search evidence and a counterfactual trigger.

## Review code for scientific meaning

The main model maps the implementation to the intended mathematics, physical process, protocol, data
flow, and estimand. It explicitly asks how code could execute without errors yet answer the wrong
question: leakage, wrong units, coordinate frames, boundary conditions, aggregation, masking,
normalization, evaluator direction, split contamination, hidden defaults, seed/replicate semantics,
or domain-specific equivalents.

Design the smallest discriminative executable checks for the risks actually present. Code verifies
their outcomes; the model judges whether they establish alignment. Add an independent reviewer only
for material uncertainty, disagreement, fragility, or high consequence.

## Pilot before confirmation

Use a bounded pilot to test runtime, resource use, data flow, evaluator behavior, signal visibility,
variance/heterogeneity, protocol assumptions, and failure modes. Recompute remaining schedule before
expensive confirmation. Do not tune on sealed confirmation data.

Formal manifests name frozen `evaluation_unit_ids`, domain-appropriate replicate identifiers,
optional random seeds, input and protocol hashes, repository/environment locks, test access, raw logs,
status, and failure class. Evaluation units may be experiments, simulations, observational or
qualitative analyses, proofs, benchmarks, or artifact evaluations. Execute only units authorized by
the frozen program.

Venue observations inform whether the evidence program looks unusually thin or ambitious, but claim
validity, field conventions, measured feasibility, and user resources determine the final program.
Never copy an accepted-paper mean as an experiment quota.

## Iterate without outcome chasing

Classify before changing anything:

- infrastructure failure: bounded retry with unchanged science;
- dependency or implementation failure: material repair, renewed review/checks, rerun affected units;
- protocol failure: revise and refreeze the research program, invalidating dependents;
- data, license, or resource failure: stop or transparently narrow scope;
- unsupported hypothesis: preserve negative evidence and weaken, reject, or reframe claims;
- inconclusive evidence: report uncertainty or run only a predeclared discriminating unit.

The same normalized state without material progress stops. Competing alternatives use the lifecycle
branch ledger with question, hypothesis, expected positive/negative observations, authorized units,
cost, stop condition, runs, and scientific interpretation. Do not select a branch solely by one
scalar metric.

## Diagnose and evolve the Idea

Compare mechanism predictions, alternatives, conditions/subgroups, and failure evidence. Decide
KEEP, NARROW_SCOPE, REVISE_MECHANISM, REFRAME_PROBLEM, BRANCH_NEW_IDEA, REJECT_AND_STOP, or
INSUFFICIENT_EVIDENCE. Infrastructure repairs do not change the Idea; protocol and core scientific
changes do. Evidence used to invent a revised Idea cannot independently confirm it.

## Emit canonical evidence

Write facts to `research/evidence/results/results-manifest.jsonl`. Every fact binds claim IDs to
compatible completed runs, claim-linked evaluation units, raw artifacts and hashes, and aggregation
code/hash. Reconcile claim wording before writing. This skill does not draft or compile the paper.
