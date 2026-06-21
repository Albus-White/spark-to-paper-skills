# Claim–Evidence Rules

The labeling and action system used in `CLAIM_EVIDENCE_CHECK.md` (Step 7) and
`RESULT_ANALYSIS.md` (Step 5). Every claim in the paper is assigned a **support label** and a
resulting **action**.

## Support labels

| Label | Meaning |
|-------|---------|
| **Supported** | Evidence (traceable result/log/data) directly backs the claim as stated. |
| **Partially supported** | Evidence backs a weaker or narrower version of the claim. |
| **Unsupported** | No traceable evidence backs the claim. |
| **Contradicted** | Evidence points against the claim. |
| **Needs author confirmation** | Depends on author-provided results/context not yet verified. |

## Actions

| Action | When to use |
|--------|-------------|
| **keep** | Claim is *Supported* and worded at the right strength. |
| **weaken** | Claim is *Partially supported*; soften scope/strength (see result_writing_patterns). |
| **remove** | Claim is *Unsupported* or *Contradicted* and cannot be salvaged. |
| **add experiment** | Claim is important but *Unsupported*; a feasible experiment could support it (Step 3/4). |
| **move to limitation** | Claim is *Contradicted* / out of scope; report honestly as a limitation. |
| **mark AUTHOR_TODO** | Claim is *Needs author confirmation*; insert an explicit `AUTHOR_TODO` marker. |

## Decision guide

- *Supported* → **keep**
- *Partially supported* → **weaken** (or **add experiment** if cheap and feasible)
- *Unsupported* → **add experiment** if feasible, else **weaken** or **remove**
- *Contradicted* → **remove** or **move to limitation**
- *Needs author confirmation* → **mark AUTHOR_TODO**

## Traceability requirement

Every *Supported* / *Partially supported* label must cite a concrete artifact:
a log file, CSV/JSON metric file, figure source, or an explicit author-provided statement.
No artifact → the claim cannot be labeled *Supported* (GR-010).

## CLAIM_EVIDENCE_CHECK.md row format

```
| Claim | Location | Label | Evidence (artifact) | Action | Notes |
|-------|----------|-------|---------------------|--------|-------|
```
