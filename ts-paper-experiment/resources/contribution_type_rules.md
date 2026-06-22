# Contribution Type & Claim Type Rules

Used in SKILL Step 6 (classify contribution type and claims, **before** claim-evidence checking)
and referenced by the post-repair narrative review. Purpose: avoid confusing a paper's overall
contribution with a single row in an experiment table.

## 1. Identify the true contribution type

Before judging a paper, identify what it actually contributes. Pick the primary type (a paper may
have a secondary one):

- **framework** — a general approach/methodology others can instantiate.
- **model** — a specific architecture/model.
- **algorithm** — a procedure/method with defined steps and properties.
- **benchmark** — an evaluation suite/protocol/leaderboard.
- **dataset** — a new dataset/corpus.
- **system** — an engineered end-to-end system.
- **empirical study** — an analysis/measurement study (the finding is the contribution).
- **application paper** — applying known methods to a new domain/problem.

## 2. Proposed-method vs framework distinction (GR-013)

**Do not assume the `Proposed` row in an experiment table represents the whole paper contribution.**

> A paper may propose a **framework** and also implement a **specific model**. If the model is not
> best on one metric, that does **not** automatically invalidate the framework. Judge whether the
> evidence supports the **actual contribution**.

So:

- For a **framework** paper, the central claim is about the framework's generality/usefulness, not
  about winning every metric with one instantiation.
- For a **benchmark/dataset** paper, the contribution is the benchmark/dataset and its validity,
  not a particular method's score.
- Only for a **model/algorithm** paper whose central claim is "method X is better" does losing on
  the headline metric directly threaten the contribution.

When the evidence does not support the stated contribution, weaken/scope the claim — do not
overclaim, and do not dismiss a valid framework just because one model row lost.

## 3. Per-claim claim-type labels

Label each **major claim** with one of these types (used to keep claim-evidence checking aligned
with the real contribution):

- **framework claim**
- **method/model claim**
- **benchmark/protocol claim**
- **dataset claim**
- **empirical result claim**
- **efficiency claim**
- **limitation claim**
- **future work claim**

Write the classification to `./outputs/reports/CLAIM_TYPE_CLASSIFICATION.md`:

```
# Claim Type Classification

Paper contribution type: framework | model | algorithm | benchmark | dataset | system | empirical study | application
(secondary, if any): ...

| Claim | Location | Claim type | What evidence would support it |
|-------|----------|------------|--------------------------------|
| "<claim>" | abstract | framework claim | ... |
```

Then in claim-evidence checking, verify each claim against evidence **appropriate to its type** —
e.g., a framework claim needs evidence of generality, not just one winning table row.
