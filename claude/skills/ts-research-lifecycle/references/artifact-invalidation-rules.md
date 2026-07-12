# Artifact Invalidation Rules

- L0 editorial clarification invalidates only manuscript review.
- L1 scope narrowing invalidates the contract and affected pilot/full/result/diagnosis/claim/manuscript gates.
- L2 estimand, population, metric, or evaluation-scope change invalidates the contract and executable evidence.
- Idea core change invalidates all grounding-dependent experimental evidence.
- Protocol change invalidates baseline, implementation, pilot, full run, provenance, mechanism and downstream gates.
- Repository change invalidates repository review and all executable evidence.
- Environment, execution backend, remote target, or execution fingerprint change invalidates G5 and
  all baseline/run evidence. Local fallback after a remote lock is therefore a re-lock, not a retry.
- Test contamination invalidates Idea decision, independent revalidation and downstream claim/manuscript gates.
- Manuscript change invalidates final adversarial review.

Old artifacts remain immutable history; they are marked stale by state rollback rather than deleted.
