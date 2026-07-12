# Gate Artifact Contracts

These artifacts carry evidence into model judgments. Their fields organize traceability; they do not
predetermine the scientific conclusion.

Before G3 in every empirical profile, `intake/resource-envelope.json` records only user-provided or
user-confirmed deadline, compute, financial, storage, review, priority, and constraint information.
The frozen contract binds its current hash and the feasibility microprobe demonstrates deadline and
budget fit. There is no system-supplied default experiment volume.

| Gate | Required artifact | Purpose |
|---|---|---|
| G2 | `grounding/benchmark_candidates.json` | Search scope, sourced candidates, license/compatibility, and a classified decision including valid no-benchmark outcomes |
| G6 | `reports/experiments/baseline-reproduction.json` | Official source, expected behavior/source, baseline run IDs, actual outputs, comparison, deviations, limitations |
| G7 | `reports/code/implementation-review.json` | Mathematical/protocol summary, contract alignment, hash-bound code, risks, findings, limitations, reviewer |
| G8 | `reports/code/verification-suite.json` | Main-model risk selection and implementation-specific executable tests with oracles and evidence |
| G9 | `reports/experiments/pilot-assessment.json` | Pilot run IDs, feasibility, signal/variance observations, failure modes, budget projection, decision, limitations |
| G10 | `reports/experiments/full-run-integrity.json` | Authorized full run IDs, active contract/repository/environment hashes, budget/test-access summary, raw outputs |
| G11 | `evidence/results/results-manifest.jsonl` | Claim-linked facts bound to contract experiments, completed runs, raw artifacts/hashes, aggregation code/hash |
| G12 | `reports/mechanism/mechanism-diagnosis.json` | Predictions, observations, alternatives, discriminating evidence, verdict, claim implications, limitations |
| G13 | `decisions/DR-*.json` | Evidence-backed Idea keep/narrow/revise/reframe/branch/reject decision |
| G14 | `reports/experiments/independent-revalidation.json` | Revalidation run IDs, independence dimensions, compared facts, conclusion, limitations |
| G15 | `claims/claim-registry.json` | Support status, action, allowed wording, and hash-bound evidence for every active claim |
| G16 | active manuscript record plus `scientific_judgment` | Whole-manuscript evidence calibration and release decision |

For model-judged gates, both the gate evidence list and `scientific_judgment` context cite the required
artifact. The lifecycle verifies files, IDs, and hashes. The main model still decides whether the
evidence supports the conclusion.

Formal run manifests include `experiment_ids` from the frozen contract. Contract experiments include
their claim IDs and positive, negative, confounder, and out-of-scope interpretations. This creates the
traversable path `claim -> contract experiment -> run -> fact -> manuscript binding`.

Before manuscript planning, `venue-study.json` records official venue guidance, representative
accepted papers, field conventions, explicit user requirements, and the model's evidence-backed
design decisions. It informs structure and artifact selection but never creates a quota.
