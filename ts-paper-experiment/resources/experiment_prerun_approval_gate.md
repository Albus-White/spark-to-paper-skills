# Experiment Pre-run Plan & Resource Approval Gate

Promoted from candidate **CAND-011**; enforced by **GR-021**. Used in SKILL Step 2 (after the
experiment plan, before Step 3 runs anything). Output:
`./outputs/reports/PRERUN_PLAN_APPROVAL.md`.

Purpose: before running **expensive** experiments or **downloading external data**, present a clear
pre-run plan and **get explicit user approval**. This prevents surprise compute cost, disk usage,
long runtimes, and unintended data downloads.

## When approval is required

- The experiment is **costly** (long runtime, GPU/cluster, significant disk), **or**
- it requires **downloading external data** (also run the Dataset / License / Terms Gate, Step 3),
  **or**
- it has any **license / cost / privacy** implication.

Cheap, local runs on already-available data may proceed without a separate approval (note them in
the report as "auto-approved: low cost").

## Per-experiment plan fields

For each planned experiment, report:

- **Name / purpose** and the **claim it supports** (and whether that claim is **essential**).
- **Estimated runtime**.
- **Disk requirement**.
- **Compute / cost** (CPU/GPU, cluster, approximate $ if relevant).
- **External data** needed (name, source, size, license/ToU status — link the Dataset gate).
- **Necessity**: essential / recommended / optional.
- **Decision**: `await-approval` / `auto-approved (low cost)` / `skip`.

## Report format

```
# Pre-run Plan & Approval

| Experiment | Supports claim | Essential? | Runtime | Disk | Compute/cost | External data | Decision |
|------------|----------------|-----------|---------|------|--------------|---------------|----------|
| ... | ... | yes/no | ~2h | 20GB | 1×GPU | none / <name> | await-approval |

Awaiting user approval for: <list>
Auto-approved (low cost): <list>
```

## Rule

**Do not start** an `await-approval` experiment or download external data until the user approves.
If the user declines or does not approve, plan around it (use available data, or write an
experiment requirements report instead — GR-011). Never fabricate results to avoid a costly run.
