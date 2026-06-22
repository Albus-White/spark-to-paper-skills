# Raw-Result Recomputation

Promoted from candidate **CAND-008**; enforced by **GR-019**. Used inside the Code–Experiment–Paper
Consistency Gate (SKILL Step 5, `RESULT_PROVENANCE_AUDIT.md`).

Purpose: every aggregated number in a table/figure must be **recomputable from the per-seed raw
logs** — not copied from memory, a chat, or a stale draft.

## Rule

For each reported value (e.g., a mean accuracy in a table cell):

1. Locate the **per-seed raw logs/metric files** it summarizes (JSON/CSV/log under
   `./workspace/experiments/` or `./outputs/`).
2. **Re-aggregate** them with the paper's stated aggregation (mean, std, median, etc.).
3. Confirm the recomputed value **matches** the reported value within rounding.
4. Record any **mismatch** as a finding: fix the manuscript value to match the logs (a traceability
   correction is allowed, GR-016/GR-018) or, if the logs are missing, mark the value `AUTHOR_TODO`
   and weaken/remove the claim. **Never** keep a value that cannot be recomputed.

## What to record per value

| Table/Fig cell | Reported | Per-seed source files | Seeds | Aggregation | Recomputed | Match? |
|----------------|----------|-----------------------|-------|-------------|------------|--------|
| Tab.1 r2c3 | 0.812 | runs/seed{1,2,3}/metrics.json | 1,2,3 | mean | 0.811 | ~ (rounding) |

## Helper script

`scripts/check_result_recomputation.py` scans `./workspace/experiments/` and `./outputs/` for
CSV/JSON metric files, groups rows/records by a `seed` field when present, and prints per-metric
mean/std to assist recomputation. It is an **aid**, not a substitute for confirming the exact
table-cell ↔ log mapping by hand. It never edits the manuscript and writes only to
`./outputs/reports/RESULT_RECOMPUTATION_CHECK.md`.

## Notes

- Per-seed logs and recomputation reports stay under `./workspace/` and `./outputs/`; they are
  never placed in `./paper/` and never committed to the AutoPaperFactory template repo.
