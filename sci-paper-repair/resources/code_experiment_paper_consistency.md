# Code–Experiment–Paper Consistency Gate

Mandatory gate (SKILL Step 5), run **after experiments/analysis and before the reported numbers are
written into the manuscript**. Purpose: guarantee that every reported result is **real and
traceable** and that the **code actually implements what the paper describes**.

This gate is an **audit** over the current paper project's evidence: `./input/code/`,
`./workspace/experiments/`, and `./outputs/`. It does not invent results, and it does not edit the
manuscript except to weaken/remove claims that fail the audit. It produces six reports under
`./outputs/reports/`.

> Note: this resource describes future behavior for real paper-repair tasks. In the
> AutoPaperFactory template repository there is no real code or data; the gate runs against
> whatever the cloned paper project provides.

---

## 1. Result provenance → `RESULT_PROVENANCE_AUDIT.md`

Every numeric value in every table/figure must trace to all of:

- **dataset**
- **model / variant**
- **seed**
- **metric**
- **source JSON/CSV/log path**
- **aggregation script** (the script that turned raw logs into the reported number)

**No value may be guessed, manually invented, or written from memory.** A value without a complete
trace is a finding: weaken/remove the claim or mark `AUTHOR_TODO`.

```
| Table/Fig | Cell/series | Dataset | Model/variant | Seed(s) | Metric | Source path | Aggregation script | Traced? |
|-----------|-------------|---------|---------------|---------|--------|-------------|--------------------|---------|
```

## 2. Experiment completeness → `EXPERIMENT_COMPLETENESS_AUDIT.md`

For every reported table/figure, verify that all reported **model × dataset × seed × metric**
combinations were actually run. Classify each combination as exactly one of:

- `FULLY_RUN`
- `PARTIALLY_RUN`
- `NOT_RUN_BUT_NOT_CLAIMED`
- `CLAIMED_BUT_NOT_RUN`

Any `CLAIMED_BUT_NOT_RUN` is a hard problem: the claim must be removed/weakened, or the run
actually performed. `PARTIALLY_RUN` must be disclosed honestly (e.g., fewer seeds).

```
| Table/Fig | Model | Dataset | Seed | Metric | Status |
|-----------|-------|---------|------|--------|--------|
```

## 3. Code–paper consistency → `CODE_PAPER_CONSISTENCY_AUDIT.md`

Check that the code implements what the paper describes. Cross-check at least (adapt to the paper;
the list below is an example for a multimodal alignment paper):

- skeleton encoder
- audio encoder
- alignment head
- classification loss
- offset regression loss
- contrastive loss
- corruption protocol
- audio shift
- motion shift
- wrong music
- motion corruption
- speed perturbation
- all baselines
- all ablations
- all metrics

**If the paper describes a component that the code does not implement, stop and report.** Map each
described component to its implementation site (file/function) or mark it `NOT_IMPLEMENTED`.

```
| Described component | Implemented? | Code location | Note |
|---------------------|--------------|---------------|------|
```

## 4. Experiment design correctness → `EXPERIMENT_DESIGN_CORRECTNESS_AUDIT.md`

Check:

- no **train/test leakage**
- correct **split protocol**
- **seeds actually used** (not just declared)
- **metrics appropriate** for the task
- **N/A cells truly not applicable**
- **offset MAE only computed where offset labels exist**
- **retrieval metrics only computed for models with alignment scores**
- **cross-dataset replication is not falsely described as zero-shot transfer**

```
| Check | Result (pass/fail/NA) | Evidence | Required fix |
|-------|-----------------------|----------|--------------|
```

## 5. Code artifact completeness → `CODE_ARTIFACT_COMPLETENESS_AUDIT.md`

The experiment code should be preserved enough for reproducibility. Check for:

- preprocessing code
- feature extraction code
- model definitions
- baseline definitions
- training script
- evaluation script
- table/figure generation script
- config or documented commands

**If code only exists as scratch scripts, report a reproducibility risk** (and what is missing).

```
| Artifact | Present? | Location | Reproducibility note |
|----------|----------|----------|----------------------|
```

## 6. Final verdict → `EXPERIMENT_TRUTHFULNESS_VERDICT.md`

A single overall verdict, exactly one of:

- `FULLY_TRACEABLE_AND_CONSISTENT`
- `TRACEABLE_WITH_MINOR_GAPS`
- `PARTIAL_TRACEABILITY_RISK`
- `CODE_PAPER_MISMATCH`
- `UNVERIFIED_RESULTS_RISK`

```
# Experiment Truthfulness Verdict

Verdict: <one label>
Basis: provenance (Step 5.1), completeness (5.2), code-paper (5.3), design (5.4), artifacts (5.5).
Blocking issues: <list, or none>
Required actions before reporting these numbers: <list>
```

## Enforcement (GR-018)

- **Never write a number that fails provenance.**
- If anything is `CLAIMED_BUT_NOT_RUN`, or the verdict is `CODE_PAPER_MISMATCH` or
  `UNVERIFIED_RESULTS_RISK`, **weaken or remove the affected claim, or stop and ask the user**.
- Do **not** fabricate, and do **not** quietly downgrade a problem. A repaired paper is not
  complete until results are traceable to real executed code/logs and the code implements the
  method, baselines, metrics, and experiment protocol described in the manuscript.
