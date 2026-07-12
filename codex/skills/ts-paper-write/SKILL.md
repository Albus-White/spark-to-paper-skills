---
name: ts-paper-write
description: Draft a complete LaTeX manuscript from blueprint.json, real sources, and optional canonical result facts. Use after the research profile and claims are stable. The main model owns scientific exposition, section structure, citation support, terminology, equations, and evidence-calibrated claims; deterministic lint checks only manuscript integrity and provenance wiring.
---

# ts-paper-write

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md` and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Draft once from stable inputs

Read the whole blueprint, active Idea and claims, frozen contract, source evidence, bibliography, and
canonical result facts when present. Draft all sections coherently in one pass so terminology,
notation, assumptions, and claim strength remain aligned.

Follow `blueprint.section_order` and each section's semantic roles. Do not assume a section named
`experiments`, a fixed subsection count, a fixed contribution count, or a domain-specific metric.
Choose equations, pseudocode, tables, and examples only when they improve scientific understanding.

## Integrity modes

**Proposal:** describe hypotheses, planned evaluations, possible outcomes, and limitations in future
or conditional language. Protocol constants and cited dataset facts are legitimate; measured outcomes
are not.

**Exploratory/empirical:** report only canonical facts authorized by active claims. Preserve
population, condition, denominator, uncertainty, comparison, negative outcomes, and scope. Create
`results_bindings.json` through `ts-paper-data`.

## Main-model review while drafting

For every important claim, ask whether the cited source or result actually supports the sentence,
whether an alternative explanation remains, and whether the wording exceeds the evidence. Explain
code or algorithms by their scientific meaning rather than translating syntax line by line.

Write `sections/<id>.tex` and `sections/abstract.tex` as body files without top-level document
commands. Then run:

```bash
python scripts/draft_lint.py <workdir>
python ../ts-paper-cite/scripts/citations_lint.py <workdir>
python scripts/reflow_tex.py <workdir>
```

Fix missing files, placeholders, malformed LaTeX, unknown citation keys, and provenance failures.
Treat wording and word-target warnings as input to model judgment, not automatic blockers.
