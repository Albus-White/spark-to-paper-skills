---
name: ts-paper-review
description: Perform holistic evidence-bound scientific and manuscript review after refinement. Use the main model to find contradictions, logical errors, method-result mismatch, unsupported claims, citation misuse, redundancy, filler, and communication defects; add independent reviewers only for high-risk, disputed, or fragile questions and close issues through focused delta review.
---

# ts-paper-review

Read `../ts-research-lifecycle/references/bounded-execution-contract.md` before acting. Read the whole
manuscript and raw evidence bundle. A section-by-section grammar pass is not a paper
review.

## Primary holistic review

Review these linked questions together:

1. **Problem and contribution:** Is the research question stable, significant as stated, and honestly
   distinguished from closest work without false novelty?
2. **Logic:** Do premises support conclusions? Identify circular reasoning, causal overreach,
   equivocation, selection bias, post-hoc explanation, denominator changes, unjustified
   generalization, and domain-specific fallacies.
3. **Design and implementation:** Does the written method match the frozen research program, code or
   artifact behavior, data handling, estimand, comparator, evaluator, and protocol? Could everything
   run successfully yet answer a different question?
4. **Evidence and claims:** Does every claim have the required evidence? Are negative, null, mixed,
   failed, or inconclusive conditions visible? Are alternatives and confounders treated fairly?
5. **Cross-section consistency:** Compare title, abstract, contribution statements, methods, results,
   discussion, conclusion, notation, units, terminology, assumptions, tables, captions, and appendices
   for drift or contradiction.
6. **Sources:** Does each citation support its local statement? Are primary/authoritative sources used
   where appropriate? Is citation count substantive rather than padded?
7. **Communication:** Is each section necessary, nonredundant, proportionate, and understandable to
   the target field? Does any text exist only to meet a page target? Are internal hashes, gates,
   commands, or audit inventories leaking into the paper?
8. **Venue and figures:** Does the paper have justified substance at the selected scale? Do planned
   figures/tables answer real reader questions and use the correct source-of-truth routes?

For every issue quote exact manuscript text and cite exact evidence artifacts. Normalize by root
cause. Record severity, affected claim/locations, why it matters, required action, and a verifiable
close criterion. Merge repeated manifestations of one root cause.

## Independent review

Use the smallest fresh reviewer set justified by consequence, uncertainty, core disagreement,
implementation fragility, or high-risk profile. Give each reviewer the minimal raw artifact bundle,
not parent conversation history or an intended verdict. Add another opinion only when a material
disagreement remains.

## Closure and judgments

Route valid issues to `ts-paper-refine` focused mode. Recheck the issue, close criterion, changed text,
and evidence. Do not multiply full-paper review loops.

Write the G16 scientific judgment after source-level hardening. It records the holistic scientific
review; deterministic gates verify only exact state. After figures and LaTeX compilation, open the
actual final PDF and write the separate Publication Judgment required by the lifecycle. That final
judgment explicitly covers argument/claim consistency, method-result alignment, redundancy/filler,
internal-provenance separation, limitations/negative results, figure roles, citation relevance,
venue-scale substance, and visible layout defects. Neither judgment may override a failed exact
check, and exact checks cannot declare the science correct.
