# Experiment Table Necessity Audit

Mandatory module (SKILL Step 9). Output:
`./outputs/reports/EXPERIMENT_TABLE_NECESSITY_AUDIT.md`.

Purpose: prevent over-expanded experiment sections. More tables is not better — each main-text
table must earn its place by supporting a distinct claim.

## Rules

- Every **main-text** experiment table must support a **distinct** manuscript claim.
- **Do not add tables just because results are available.**
- If a table is **too detailed** for the main paper, move it to **appendix / supplement /
  report**, or **summarize it in prose**.
- For each table, state:
  - the **exact claim supported**,
  - the decision: **keep in main text / move to appendix / remove**,
  - the **reason**.
- **Do not remove source results or logs** (only the table's placement in the manuscript changes).
- **Do not change numeric values** unless a traceability mismatch is found (then fix to match the
  log/CSV and note it).

## Report format

```
# Experiment Table Necessity Audit

| Table | Claim supported | Decision | Reason | Traceable? |
|-------|-----------------|----------|--------|------------|
| Tab. 1 | "<exact claim>" | keep / move-to-appendix / remove | ... | yes (path) |

Summary: <N keep> / <N moved> / <N removed>. Source results/logs preserved: yes.
```

## Applying decisions

- Apply approved **keep/move/remove** decisions by editing `./paper/` (move tables to an appendix
  file or replace with a prose summary). Keep the underlying CSV/logs under `workspace/`/`outputs/`.
- A "remove from main text" decision never deletes the experiment's evidence — only its main-text
  table.
