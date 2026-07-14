---
name: ts-paper-latex
description: Deterministically assemble and compile the current manuscript in its explicitly selected venue template. Use after writing, review, and figures to build main.tex/main.pdf, copy official assets, normalize template-controlled formatting, diagnose exact LaTeX failures, and verify a hash-bound compile verdict. This skill formats and compiles; it never changes scientific meaning or invents content.
---

# ts-paper-latex

This is a low-freedom deterministic stage. Read
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Preconditions

Require `template.json`, `blueprint.json`, `refs.bib`, and all blueprint section files. The selected
template must use user-provided or official venue assets for submission. Bundled approximations are
demo-only. Missing templates fail closed; never silently substitute another venue.

## Assemble and compile

```bash
python scripts/assemble_paper.py <workdir> --backup
```

The script deterministically applies template-controlled heading titles, section order, caption
position, citation merging, keyword formatting, table-width safeguards, front matter, and asset copy.
It runs `latexmk` once with a timeout and reports `compiled`, `error_count`, `error_tail`, and an
`input_hash` over template, blueprint, references, sections, and published figures.

After a passing compile, register the exact verdict and PDF in the lifecycle:

```bash
python ../ts-research-lifecycle/scripts/lifecycle.py --root <workdir>/research \
  register-latex-verdict --file <workdir>/assemble.json --pdf <workdir>/main.pdf
```

Fix only concrete syntax or artifact errors: unbalanced math/environments, escaping, missing files,
bad labels, unresolved citation keys, or invalid figure assets. Do not alter claims, equations,
numbers, citations, or scientific wording to make compilation pass.

Use at most three compile/fix attempts. Stop when the normalized error set repeats or grows. Restore
the backup after a regression. A cached compile verdict is accepted only when its `input_hash` matches
the current inputs.

## Release checks

- `main.pdf` exists and LaTeX reports zero errors;
- citation keys and bibliography compile without unresolved markers;
- every included figure has its route-authorized artifact; DrawAI-unavailable PaperBanana figures may
  use the reviewed raster with an audited skip record;
- the lifecycle validates and can enter `LATEX_COMPILED`, `RELEASE_AUDITED`, or `RELEASED`;
- the registered manuscript is the current allowlisted snapshot.

Compilation is exact evidence of LaTeX/build correctness. It is not evidence that the science or
rendered paper is correct. G16 supplies source-level scientific review; the post-compile Publication
Judgment requires the main model to open and review the actual final PDF.
