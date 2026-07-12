# Gate Verdict Specification

Verdicts are `PASS`, `PASS_WITH_EXPLAINED_DEVIATION`, `NOT_APPLICABLE`, `FAIL`, `BLOCKED`, or
`AUTHOR_REQUIRED`.

G0, G4, G5, G10, and G11 are primarily deterministic: intake identity, repository/license lock,
environment lock, full-run integrity, and canonical result provenance.

G1, G2, G3, G6, G7, G8, G9, G12, G13, G14, G15, and G16 require a main-model
`scientific_judgment`. Its reviewer records the minimal raw context, question-level findings,
rationale, artifact evidence, limitations, uncertainty, and blockers. The lifecycle verifies the
artifact structure and hashes; it does not replace the model's semantic judgment with a heuristic.
Required gate-specific evidence bundles are defined in `gate-artifact-contracts.md`.

`NOT_APPLICABLE` is legal only for a profile/gate combination supported by the executable policy. It
requires both a scientific rationale and the counterfactual condition that would make it applicable.

A later passing verdict removes the previous blocker for that gate. Changed evidence or judgment
hashes invalidate lifecycle validation.
