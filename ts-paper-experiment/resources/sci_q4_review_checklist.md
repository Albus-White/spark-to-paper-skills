# SCI Q4 Review Checklist

Final readiness gate (SKILL Step 8). Review the manuscript in `./paper/` against each item, then
write the report to `./outputs/reports/SCI_Q4_READINESS.md`. If an item fails, fix it by editing
the manuscript files **directly inside `./paper/`**.

## Checklist

| # | Item | What to verify | Pass/Fail |
|---|------|----------------|-----------|
| 1 | **Title clarity** | Title is specific and states the contribution; no hype. | |
| 2 | **Abstract–result consistency** | Every abstract claim matches the reported results. | |
| 3 | **Introduction gap** | Background → gap → problem → contribution is explicit. | |
| 4 | **Related work (not citation dumping)** | Each citation supports a specific point; no padding. | |
| 5 | **Method reproducibility** | Hyperparameters, splits, seeds, hardware, and procedure are stated. | |
| 6 | **Dataset description** | Source, size, splits, preprocessing, and leakage controls are described. | |
| 7 | **Baseline completeness** | Credible, fairly tuned baselines under the same protocol. | |
| 8 | **Metric appropriateness** | Metrics fit the task; variance/multiple runs where claimed. | |
| 9 | **Table/figure traceability** | Every number traces to a log/CSV/author-provided artifact. | |
| 10 | **Results–discussion distinction** | Results describe observations; discussion interprets. | |
| 11 | **Honest limitation** | Limitations and failure modes are stated plainly. | |
| 12 | **No unsupported claim** | No claim exceeds the evidence; strong claims are scoped. | |
| 13 | **No fake citation** | Every reference is real and verifiable. | |
| 14 | **No fake statistical significance** | "Significant" only with a statistical test or repeated runs. | |

## SCI Q4 readiness score

Score each item 1 (Pass) or 0 (Fail), then report:

- **Score = (passed items) / 14.**
- **Readiness verdict:**
  - **READY** — 14/14, and items 9, 12, 13, 14 (traceability + no fabrication) all pass.
  - **NEEDS WORK** — at least one item fails but none of items 9, 12, 13, 14 fail.
  - **NOT READY** — any of items 9, 12, 13, 14 fail (traceability or fabrication problem).

Items 9, 12, 13, and 14 are **gating**: failing any one of them forces **NOT READY** regardless
of the numeric score, because they concern traceability and fabrication.

## Report format (`outputs/reports/SCI_Q4_READINESS.md`)

```
# SCI Q4 Readiness

Score: X / 14
Verdict: READY | NEEDS WORK | NOT READY

| # | Item | Pass/Fail | Note / required fix |
|---|------|-----------|---------------------|
| 1 | Title clarity | ... | ... |
...
```

## Relation to the post-repair review

This Q4 checklist is the readiness **gate** (SKILL Step 8). It is distinct from the **post-repair
review** (SKILL Step 10, the final mandatory step), which runs after the commit/push and compares
the original imported draft (initial commit in `./paper/`) against the repaired `HEAD`:

- `outputs/reports/ORIGINAL_TO_REPAIRED_CHANGELOG.md` — what changed and why.
- `outputs/reports/FINAL_NARRATIVE_INTEGRITY_REVIEW.md` — whole-paper better/worse judgment with a
  verdict label (`SIGNIFICANTLY_IMPROVED`, `IMPROVED_BUT_WEAKER_CLAIMS`, `HONEST_BUT_STILL_WEAK`,
  `NARRATIVE_DAMAGED`, `NOT_READY`).

A paper can pass the Q4 gate yet still be judged `IMPROVED_BUT_WEAKER_CLAIMS` or worse if the
evidence weakened the original story. Report both honestly.
