# Rendered PDF Layout Check

Promoted from candidate **CAND-006**; enforced by **GR-020**. Used in SKILL Step 14. Output:
`./outputs/reports/PDF_LAYOUT_CHECK.md`.

Purpose: **LaTeX compiling successfully is not enough.** A paper can compile yet still have broken
tables, overflowing text, off-page figures, or missing references. The **rendered PDF pages must be
visually checked**.

## Procedure

1. Compile the manuscript in `./paper/` to PDF (the project's normal build, e.g. `latexmk` /
   `pdflatex` + `bibtex`/`biber`). Do this inside `./paper/`; do not commit build artifacts to the
   AutoPaperFactory repo.
2. Render the pages to images (the helper `scripts/check_pdf_layout.py` uses `pdftoppm`/`pdfinfo`
   when available) and look at them.
3. Record findings and fixes in `./outputs/reports/PDF_LAYOUT_CHECK.md`; apply fixes by editing
   `./paper/`.

## Checklist

- [ ] No **overfull/underfull boxes**; no text running into or past the margins.
- [ ] **Tables** render fully (not cut off / not wider than the column or page).
- [ ] **Figures** are on-page, not overlapping text, correctly sized and placed.
- [ ] **No `??`** — every `\ref`/`\cite`/`\eqref` resolves in the rendered output.
- [ ] **Captions** are present, correctly placed, and numbered sequentially.
- [ ] **Equations** are not clipped; **fonts are embedded**.
- [ ] Headers/footers, page numbers, and section breaks look correct.
- [ ] Overall layout is consistent with a submittable manuscript / the venue template.

## Report format

```
# PDF Layout Check

Build: <command used> — compiled: yes/no
Pages rendered/checked: <N>

| Page | Issue | Severity | Fix applied in ./paper/ |
|------|-------|----------|-------------------------|
| 4 | table 2 overflows right margin | high | resized columns / \resizebox |

Summary: <N issues> (<high>/<med>/<low>). Layout submittable: yes/no.
```

## Notes

Compilation success alone never closes this check. Do not commit the rendered PDF or page images to
the AutoPaperFactory template repo.
