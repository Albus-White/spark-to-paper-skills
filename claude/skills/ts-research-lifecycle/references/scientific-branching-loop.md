# Scientific Branching and Feedback Loop

This loop adopts the useful part of progressive experiment search: preserve parent/child alternatives,
separate debugging from scientific changes, and use evidence summaries to choose the next question. It
does not optimize a paper by blindly selecting the highest scalar metric.

## When to branch

Create a branch only for a named unresolved question whose answer may change a claim, mechanism,
protocol, implementation, or stop decision. Common classes are:

- `debug_repair`: the intended experiment did not execute correctly;
- `implementation`: an alternative implementation may better match the frozen method;
- `protocol`: the current protocol answers the wrong or ambiguous question;
- `idea`: evidence motivates a different mechanism, scope, or research question;
- `diagnostic`: a bounded test distinguishes competing explanations.

Infrastructure retries that do not change state are not scientific branches.

## Branch contract

Each proposal records a parent branch, question, hypothesis, authorized contract experiment IDs,
positive and negative expected observations, rationale, evidence, estimated cost, and stop condition.
The frozen contract sets `max_branches` and `max_branch_depth`. Duplicate branch signatures are
rejected unless the scientific state changes.

Each branch-bound run records the branch ID. After execution, the main model evaluates raw outputs and
records `SUPPORTED`, `PARTIAL`, `UNSUPPORTED`, `INCONCLUSIVE`, or `INVALID`, plus claim implications,
limitations, and one action: promote, reject, retain as diagnostic, revise contract, evolve Idea, or
stop. Negative and inconclusive branches remain in the ledger.

## Selection policy

Do not average unlike metrics into a universal score. Order decisions lexicographically:

1. protocol and implementation validity;
2. ability to distinguish the active hypothesis from alternatives;
3. coverage of an essential claim;
4. robustness of evidence and uncertainty;
5. resource cost and remaining budget.

A lower headline metric may be scientifically preferable when it removes leakage, uses a fairer
comparator, or falsifies an overstrong claim. Test or confirmation evidence is never used for branch
generation without a new independent confirmation source.

## Context economy

The next branch receives the frozen contract, parent branch delta, relevant run artifacts, current
claim status, and a hash-bound summary of valid leaf evidence. It does not receive the full conversation
or every failed node. Repeated failure without a state change, exhausted branch budget, unsupported
hypothesis, or no decision-relevant next question terminates exploration.

## Deliberately not adopted

Do not force fixed ML stages, multiple datasets, a seed count, longer runtime, exhaustive ablations,
or a fixed worker tree. Do not inherit hard-coded iteration, timeout, worker, or compute budgets; the
main model derives them from the user's confirmed resource envelope and the scientific decision that
must be resolved. Do not select a winner from averaged unlike metrics, a missing-metric fallback, or a
single headline score. Do not inflate data/model/runtime merely because a valid run finishes quickly,
and do not rely on configuration fields that the executor does not actually consume. These patterns
can spend more compute while weakening protocol validity and cross-domain applicability.
