# Figure/Table Publication Polish Check

Mandatory module (SKILL Step 10). Output:
`./outputs/reports/PUBLICATION_POLISH_CHECK.md`.

Purpose: catch misleading or unreadable figures/tables before submission. Fixes are applied by
editing `./paper/`; **never change a value without a traceability reason**.

## Checklist

**Tables**

- [ ] **Width and readability** — table fits the column/page; not truncated or cramped.
- [ ] **Numbering and references** — every table is numbered and referenced in the text; numbers
      are sequential; no dangling references.
- [ ] **N/A / `--` definitions** — every `N/A`/`--`/`-` symbol is defined in the caption or notes.
- [ ] **Missing cells truly not applicable** — a blank/`--` means genuinely not applicable, not a
      hidden missing result.
- [ ] **Caption clarity** — caption states what the table shows and the key takeaway.

**Figures**

- [ ] **Legend–marker consistency** — legend labels, colors, and markers match the plotted series.
- [ ] **Title/caption matches content** — the caption describes what the figure actually shows.
- [ ] **Supports the surrounding claim** — the figure backs the claim in the nearby text.
- [ ] **No misleading visualization** — honest axes (no truncated/baseline tricks), correct scale,
      no cherry-picked range, error bars defined if shown.

**Both**

- [ ] **Values trace to CSV/JSON/logs** — every plotted/tabulated value maps to a real artifact in
      `workspace/experiments/` or `outputs/`.

## Report format

```
# Publication Polish Check

| Item | Table/Figure | Status | Issue | Fix applied in ./paper/ |
|------|--------------|--------|-------|-------------------------|
| width/readability | Tab. 2 | pass/fail | ... | ... |
| no misleading viz | Fig. 3 | pass/fail | ... | ... |
| traceability | Fig. 3 | pass/fail | path | ... |

Summary: <N pass> / <N fail>. Misleading visualizations: <N> (must be 0 before submission).
```
