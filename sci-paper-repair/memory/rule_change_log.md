# Rule Change Log

An append-only audit trail of all changes to `../resources/golden_rules.md` (promotions,
edits, retirements). Every promotion from `lessons_candidate.md` must be recorded here with the
approving human.

## Entry format

```
Date:
Change type: promote / edit / retire
Rule ID:
From: (candidate / golden rule text)
To:   (new golden rule text)
Approved by:
Source paper / candidate:
Notes:
```

---

<!-- Append change-log entries below this line -->

Date: 2026-06-14
Change type: promote
Rule ID: GR-019, GR-020, GR-021
From: candidate workflow lessons CAND-008, CAND-006, CAND-011
To:
  - GR-019: Raw table values must be recomputable from per-seed raw logs. (see raw_result_recomputation.md)
  - GR-020: Compilation is not enough; the rendered PDF layout must be visually checked. (see rendered_pdf_layout_check.md)
  - GR-021: Expensive or external-data experiments require a pre-run plan and user approval. (see experiment_prerun_approval_gate.md)
Approved by: user (biaowu123456@gmail.com)
Source paper / candidate: lessons captured from the completed paper-repair test (CAND-006…CAND-012)
Notes:
  - User chose "option 2": keep existing GR-013…GR-018 intact (no renumber); append only the
    three genuinely-new rules as GR-019…GR-021.
  - The proposed "references must be real and verified" golden rule was NOT added as a new rule —
    it duplicates existing GR-014; reference verification remains promoted as workflow Step 12 and
    resource reference_verification.md (wording strengthened, tied to GR-014).
  - All workflow candidates promoted into formal steps/resources (see lessons_validated.md):
      CAND-006 rendered PDF layout check -> Step 14 + rendered_pdf_layout_check.md (GR-020)
      CAND-007 reference verification     -> Step 12 + reference_verification.md (GR-014, already present)
      CAND-008 raw-log/per-seed recomputation -> Step 5 provenance + raw_result_recomputation.md (GR-019)
      CAND-009 code-paper consistency audit -> Step 5 + code_experiment_paper_consistency.md (GR-018)
      CAND-010 reproducible code packaging -> Step 5 artifact audit + reproducible_artifact_packaging.md
      CAND-011 pre-run experiment plan & resource approval gate -> Step 2 + experiment_prerun_approval_gate.md (GR-021)
      CAND-012 post-repair narrative integrity review -> Steps 16–17 + post_repair_narrative_review.md
  - New helper scripts added: check_result_recomputation.py, check_code_paper_consistency.py,
    check_pdf_layout.py.
