# Gate Verdict Specification

Verdicts are `PASS`, `PASS_WITH_EXPLAINED_DEVIATION`, `NOT_APPLICABLE`, `FAIL`, `BLOCKED`, or
`AUTHOR_REQUIRED`.

Generic structured scientific judgments are required for G1, G2, G3, G6, G7, G8, G9, and G12-G16.
The reviewer records minimal raw context, question-level findings, rationale, artifact evidence,
limitations, uncertainty, blockers, and independence when required. Code verifies structure and
hashes; it does not replace semantic judgment.

G0, G4, G5, G10, G11, and M6 are primarily exact identity/provenance gates. V1 uses a specialized
venue judgment. M1 is a model-authored, approved publication contract checked against exact
constraints and the reproducible envelope. M2 carries model-authored source-quality review; M3 is the
registered complete draft; M4 is a hash-bound holistic refinement report; M5 combines route-specific
actual-image reviews and exact artifact validation. These specialized artifacts avoid duplicate
generic review layers.

`NOT_APPLICABLE` is legal only where the executable profile policy permits it and requires both a
scientific rationale and the counterfactual condition that would make the gate applicable.

A later passing verdict removes the gate's previous blocker. Changed evidence or judgment hashes
invalidate validation and dependent phases.
