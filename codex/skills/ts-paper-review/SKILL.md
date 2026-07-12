---
name: ts-paper-review
description: Review and harden a complete research manuscript with evidence-bound, risk-proportional scientific judgment. Use after refinement or when asked to critique a paper. The main model inspects the whole manuscript and raw evidence; independent reviewers are added only for high-risk or disputed questions, and fixes close through focused delta review instead of multiplicative reviewer loops.
---

# ts-paper-review

Read `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md` and
`../ts-research-lifecycle/references/bounded-execution-contract.md`.

## Primary review

Give the main model the current manuscript, active claims, closest sources, contract, canonical facts,
and important code/review artifacts. Review scientific validity, evidence calibration, protocol and
implementation alignment, alternative explanations, citation support, reproducibility, limitations,
and communication quality. Quote exact manuscript text and cite artifact paths for each issue.

Normalize issues by root cause. Each issue records severity, affected claim, evidence, why it matters,
proposed action, and a verifiable close criterion. Do not multiply stylistic variants into separate
issues.

## Independent review policy

Use the smallest fresh independent reviewer set justified when the profile is high-risk, the primary
review is uncertain, a core claim is disputed, or the implementation/protocol is unusually fragile. Give reviewers only
the raw task-local artifact bundle, not parent conversation history or the intended answer.

Do not assign a fixed reviewer count to every issue. Add another independent opinion only for an
unresolved material disagreement or unusually high consequence.

## Closure

Send valid issues to `ts-paper-refine` in review-fix mode. Recheck only the issue, close criterion,
relevant diff, and evidence. Close it when the criterion is met. If the normalized issue repeats
without new evidence, stop and mark it disclosed, author-required, or unresolved; do not loop for a
different wording.

Register the final manuscript and write the G16 `scientific_judgment`. Deterministic gates then verify
artifact hashes, citation keys, result bindings, vectors, and LaTeX compilation. A model review cannot
override a failed exact check, and an exact check cannot declare the science correct.
