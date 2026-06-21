# Final Submission Checklist

Mandatory gate (SKILL Step 13), run before the final commit/push. Output:
`./outputs/reports/FINAL_SUBMISSION_CHECKLIST.md`. If an item fails, fix it in `./paper/` or flag
it to the user.

## Checklist

**Front matter / placeholders**

- [ ] Author names are **not placeholder** (no "Anonymous", "John Doe", "TODO").
- [ ] Affiliations are **not placeholder**.
- [ ] Corresponding email is **not placeholder**.
- [ ] DOI placeholder handled (real DOI, or clearly marked as "to be assigned").

**References**

- [ ] References **complete and verified** (see `reference_verification.md`).
- [ ] **No title-only references** (each has authors, venue, year as appropriate).

**Figures / tables**

- [ ] Figures **readable**.
- [ ] Tables **readable**.
- [ ] Table/figure **numbering correct** and sequential.

**LaTeX integrity**

- [ ] **No undefined refs/citations** (no `??`, no undefined `\ref`/`\cite`).
- [ ] **No overfull boxes** (or none that affect readability).

**Claims / integrity**

- [ ] **No fake significance claims** ("significant(ly)" only with a real test).
- [ ] **No unsupported SOTA/best claims**.
- [ ] **No fabricated numbers** (all values trace to artifacts).
- [ ] **No unresolved `AUTHOR_TODO`** left in the manuscript.

**Sync**

- [ ] **Overleaf remote sync status** confirmed (repaired manuscript pushed; `git -C paper status`
      clean and ahead/synced with the `overleaf` remote).

## Report format

```
# Final Submission Checklist

| Item | Status | Note / fix |
|------|--------|------------|
| Author names not placeholder | pass/fail | ... |
| No unresolved AUTHOR_TODO | pass/fail | ... |
| Overleaf remote sync status | synced/pending | ... |

Overall: READY_TO_SUBMIT / FIX_REQUIRED
Open AUTHOR_TODOs: <N> (must be 0 to submit)
```
