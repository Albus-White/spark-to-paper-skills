# Model-Designed Scientific Verification

G8 asks whether the implementation represents the intended scientific object. The main model owns
this judgment because applicable failure modes depend on the mathematics, data semantics, code path,
and claim. Do not require a universal list of test names.

## Procedure

1. Read the frozen contract, implementation, data path, metric implementation, repository diff, and
   available reference behavior.
2. Explain the implementation in scientific terms before inspecting existing tests.
3. Enumerate concrete failure modes that could run without crashing yet invalidate a claim. Include
   each failure's scientific consequence and why it is or is not applicable.
4. Design the smallest discriminative executable test set that covers every applicable risk. Prefer
   independent oracles: hand-computable fixtures, official evaluators, invariances implied by the
   method, matched reference implementations, or deliberately adversarial data.
5. Run the tests and preserve commands, inputs, outputs, and logs. A test passes only against its
   declared oracle, not because the process exited successfully.
6. Write `reports/code/verification-suite.json` with `selection_judgment.risks[]` and `tests[]`, then run
   `validate_verification_suite.py --root <research-root>`. Use its result as structural evidence for a
   separate G8 scientific judgment.

Examples such as tiny-batch overfit, label shuffle, finite-difference gradients, metric parity,
preprocessing parity, leakage checks, checkpoint reload, seed behavior, temporal ordering, patient
separation, placebo tests, candidate-pool isolation, or systems warm-up are a menu, not a quota.
Selecting an irrelevant check adds no confidence. Omitting a plausible risk without rationale and a
counterfactual trigger is a blocker.

The main model should actively look for the important case where unit tests pass but the research
logic is wrong: a metric with the wrong averaging population, a split that answers another estimand,
a baseline with unequal tuning budget, a preprocessing transform fitted on future/test data, or an
implementation that preserves shapes while changing the mathematical operation.
