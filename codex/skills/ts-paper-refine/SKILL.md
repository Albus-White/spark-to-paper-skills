---
name: ts-paper-refine
description: Perform one holistic, evidence-preserving refinement of a complete draft or close one focused review issue. Use the main model for argument flow, consistency, redundancy, claim calibration, and readability; use deterministic tools only to protect exact citations, facts, artifacts, and LaTeX integrity.
---

# ts-paper-refine

Read `../ts-research-lifecycle/references/bounded-execution-contract.md` before acting. Read the
complete manuscript and current evidence before a holistic pass. Do not optimize sections in
isolation.

## Holistic refinement

Trace the argument from question to conclusion and check horizontally across the paper:

- claim scope and strength in title, abstract, introduction, results, discussion, and conclusion;
- definitions, symbols, units, assumptions, populations/conditions, and naming;
- method/protocol statements against the frozen research program and implementation evidence;
- every reported number/table/figure against canonical facts and its intended claim role;
- citations against the local sentence they support;
- alternative explanations, negative evidence, limitations, and out-of-scope conclusions;
- duplicated motivation, contribution lists, method summaries, result restatements, and generic prose;
- appendices for reader value rather than audit leakage or page filler.

Improve ordering, transitions, explanation depth, section balance, terminology, notation, and
readability without changing source meaning or canonical facts. Remove redundancy and unsupported
certainty. Add material only when a substantive scientific gap exists. The page range is a calibrated
expectation, never authorization to pad.

Write `reports/manuscript/refinement-report.json` with the input manuscript ID/hash, issues addressed,
claim preservation, and reviewer. One holistic pass is the default; another requires changed evidence
or a newly identified manuscript-wide defect.

Run draft, manuscript-boundary, citation, result-binding, and LaTeX checks after refinement. Exact
failures must close; semantic warnings remain model decisions.

## Focused closure

For a normalized review issue, receive the quoted text, affected claim, evidence, close criterion, and
current diff. Make the smallest scientifically complete fix and review that delta. Do not restart the
paper unless the issue reveals a genuine global inconsistency. If the same issue repeats without new
evidence, disclose it or require author action rather than looping for different wording.
