# Validated Lessons

Lessons that have been reviewed and validated by a human but are kept here as durable, curated
knowledge (distinct from the active `golden_rules.md`). A validated lesson may later be promoted
to a golden rule.

Each entry should reference the candidate it came from and the validating decision.

---

<!-- Append validated lessons below this line -->

## Promoted 2026-06-14 (approved by user) — CAND-006…CAND-012

These workflow lessons were validated by the user and promoted into the formal sci-paper-repair
skill. (Moved here from candidate status; recorded in `rule_change_log.md`.)

- **CAND-006 — Rendered PDF layout check.** Compilation success is not enough; visually check the
  rendered PDF pages. → SKILL Step 14; `resources/rendered_pdf_layout_check.md`;
  `scripts/check_pdf_layout.py`. Golden rule **GR-020**.
- **CAND-007 — Reference verification.** Verify every reference against a reliable source; never
  invent fields; complete/replace/remove/merge while preserving claim–reference alignment.
  → SKILL Step 12; `resources/reference_verification.md`. Covered by existing golden rule
  **GR-014** (no duplicate rule added).
- **CAND-008 — Raw-log / per-seed recomputation of table values.** Recompute every aggregated
  value from per-seed raw logs and confirm it matches. → SKILL Step 5 (Result Provenance Audit);
  `resources/raw_result_recomputation.md`; `scripts/check_result_recomputation.py`. Golden rule
  **GR-019**.
- **CAND-009 — Code–paper consistency audit.** Verify the code implements the method, components,
  baselines, ablations, and metrics the paper describes. → SKILL Step 5;
  `resources/code_experiment_paper_consistency.md`; `scripts/check_code_paper_consistency.py`.
  Golden rule **GR-018**.
- **CAND-010 — Reproducible code packaging.** Preserve preprocessing, features, model/baseline
  definitions, train/eval and table/figure scripts, and configs/commands; scratch-only code is a
  reproducibility risk. → SKILL Step 5 (Code Artifact Completeness Audit);
  `resources/reproducible_artifact_packaging.md`.
- **CAND-011 — Pre-run experiment plan & resource approval gate.** Before expensive runs or
  external-data downloads, present a pre-run plan and get user approval. → SKILL Step 2;
  `resources/experiment_prerun_approval_gate.md`. Golden rule **GR-021**.
- **CAND-012 — Post-repair narrative integrity review.** Compare original vs repaired and judge
  the whole paper. → SKILL Steps 16–17; `resources/post_repair_narrative_review.md`.
