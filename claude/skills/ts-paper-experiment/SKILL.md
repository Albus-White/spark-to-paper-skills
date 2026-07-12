---
name: ts-paper-experiment
description: Execute the empirical branch of the shared research lifecycle on one existing research root. Use after a grounded Idea, measured feasibility probe, and approved frozen contract. Acquire pinned benchmark or author repositories, govern patches and environments, reproduce applicable baselines, let the main model design scientific verification, run bounded pilot/full experiments, classify failures, diagnose mechanisms, evolve Ideas, and produce canonical result facts.
---

# ts-paper-experiment

Operate on the existing `<workdir>/research`. Never create a second lifecycle or wait for a completed
proposal PDF before experiments.

Read:

- `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md`
- `../ts-research-lifecycle/references/remote-experiment-execution.md`
- `../ts-research-lifecycle/references/repository-governance.md`
- `../ts-research-lifecycle/references/scientific-sanity-tests.md`
- `../ts-research-lifecycle/references/adaptive-design-budget.md`
- `../ts-research-lifecycle/references/scientific-branching-loop.md`
- `../ts-research-lifecycle/references/artifact-invalidation-rules.md`
- `../ts-research-lifecycle/references/bounded-execution-contract.md`

## 1. Acquire code and data

Prefer an official benchmark or author repository when it matches the claim. Otherwise use the
closest maintained implementation and record its status, or implement the missing minimum locally.
Pin repository URL, commit, license, submodules, checkpoints, dataset versions, and evaluator source.

Keep upstream checkouts read-only. Put adapters in `code/adapters`, integration code in
`code/integration`, and necessary upstream modifications in an ordered patch stack. Resolve version
conflicts by behavior and reference tests, never by blindly choosing one side. An upstream upgrade
creates a new lock and invalidates affected executable evidence.

Credentials remain outside the research tree. Store only non-secret target and fingerprint metadata.

## 2. Lock execution

Select local or remote compute before G5, snapshot the actual environment, and lock backend, target,
Python/framework/CUDA/dependencies/hardware. A mid-run backend switch is a new environment, not a
retry. Use bounded commands and preserve start, exit, timeout, and outcome-unknown states.

## 3. Reproduce the applicable reference

When G2 identifies an applicable benchmark or baseline, reproduce its official metric/config range
before evaluating the new method. The main model compares task, split, preprocessing, evaluator,
checkpoint, and expected behavior. Code recomputes the numbers. If no valid benchmark exists, record
G6 `NOT_APPLICABLE` with evidence and a counterfactual trigger; do not run an unrelated benchmark for
the appearance of certainty.

## 4. Verify implementation scientifically

The main model explains the implementation in mathematical and protocol terms, compares it with the
contract, and enumerates ways it could run without crashing yet answer the wrong question. Design the
smallest discriminative test suite for those risks. Run it and validate
`reports/code/verification-suite.json`; do not require irrelevant universal test names.

Use an independent code review when risk, uncertainty, or a material disagreement warrants it. Review
raw code/diff, contract, and test evidence with minimal context.

## 5. Run pilot and bounded confirmation

Use pilot data to test feasibility, signal direction, variance, protocol behavior, and failure modes.
Do not tune on the sealed confirmation set. Before full execution, confirm that projected runtime and
storage remain within the frozen budget.

Run only contract-authorized full experiments. Preserve manifests, configs, domain-appropriate
replicate IDs, optional random seeds, raw outputs,
failures, test access, and environment/repository hashes. Every formal run names the structured
`experiment_id` entries it executes, preserving the claim-to-run path.

## 6. Classify before iterating

- infrastructure: bounded retry without scientific change;
- dependency/implementation: repair, rerun affected review/tests, then retry;
- protocol: return to contract judgment and invalidate dependents;
- data/license/resource: stop or explicitly narrow scope;
- unsupported hypothesis: preserve negative evidence and weaken/reject the claim;
- inconclusive: report uncertainty; do not keep tuning until positive.

The same normalized failure without a material state change stops the loop.

For genuinely competing scientific alternatives, propose a bounded lifecycle branch. Preserve its
parent, delta, expected positive/negative observations, cost, runs, and model evaluation. Promote a
branch only for protocol-valid discriminating evidence; never choose it solely because one averaged
metric is larger.

## 7. Diagnose and evolve the Idea

Let the main model compare mechanism predictions, alternatives, subgroup/condition behavior, and
failure evidence. Decide KEEP, NARROW_SCOPE, REVISE_MECHANISM, REFRAME_PROBLEM, BRANCH_NEW_IDEA,
REJECT_AND_STOP, or INSUFFICIENT_EVIDENCE. Core changes create a new Idea version. Evidence used to
invent the revision cannot independently confirm it.

## 8. Emit evidence

Write canonical facts to `research/evidence/results/results-manifest.jsonl`, binding each value to
claim IDs, completed run IDs, raw artifacts/hashes, and aggregation code/hash. Reconcile claim wording
before handing evidence to `ts-paper-data`, `ts-paper-write`, and review. This skill does not rewrite or
compile the manuscript.
