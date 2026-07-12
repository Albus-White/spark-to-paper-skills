---
name: ts-paper-refine
description: Perform one holistic, evidence-preserving refinement of a drafted paper. Use to improve argument flow, terminology, notation, section balance, claim calibration, and readability after drafting or to close a specific review issue. The main model judges prose and scientific coherence; deterministic tools protect citations, result bindings, LaTeX integrity, and compilation.
---

# ts-paper-refine

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md` and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Holistic mode

Read the entire manuscript and its evidence once. Improve the argument as a paper rather than editing
sentences independently. Preserve source meaning, canonical result facts, equations, citation keys,
and explicit limitations. Remove redundancy, vague transitions, unsupported certainty, and genuine
AI-style habits when context warrants it. Do not replace them mechanically from a phrase blacklist.

Word targets are guidance. Add material only when a scientific explanation, assumption, comparison,
failure mode, or limitation is missing; cut material only when it is redundant or irrelevant.

Run deterministic draft, citation, result-binding, and LaTeX checks after the pass. Correct exact
failures; let the model decide style warnings.

## Review-fix mode

Receive one normalized issue, its close criterion, the relevant manuscript excerpt, source evidence,
and current diff. Make the smallest scientifically complete fix, then produce a delta closure artifact.
Do not reread or rewrite the entire paper unless the issue reveals a manuscript-wide inconsistency.

Stop after one fix and one closure check. Reopen broader refinement only when new evidence or a
materially changed scientific object justifies it.
