# Project-wide bounded execution contract

This contract applies to every spark-to-paper stage, including standalone skill use. Quality work may
consume its full declared budget, but no stage may continue merely because its target has not been met.

Before the first attempt, record:

- immutable input/config/evidence fingerprints;
- a hard attempt cap and wall/command timeout;
- the observable success criterion;
- the progress metric or decreasing issue count;
- retryable and non-retryable failure classes;
- the terminal artifact and stop reason.

Stop immediately on success, a semantic/protocol/data failure, a repeated normalized state, an
A→B→A artifact cycle, two consecutive execution failures, no material progress, or budget exhaustion.
Resume only after recording a concrete state change. A larger budget, a paraphrased prompt, or
"try harder" is not a state change.

Hard maxima are executable in `scripts/bounded_execution.py`: plan/write/refine/LaTeX ≤3 attempts,
review ≤4 panel rounds, figure repair ≤10, formal experiment ≤3, and one-shot handoff/gate commands
exactly once. Stage-specific skills may use stricter limits but never exceed these maxima.

Every terminal state is legitimate: `PASS`, `REVIEW_REQUIRED`, `FAILED`, hypothesis rejected,
insufficient evidence, or infrastructure unavailable. Never relabel a stopped state as success and
never silently restart it from unchanged inputs.
