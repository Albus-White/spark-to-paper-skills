---
name: ts-paper-write
description: Draft one complete evidence-calibrated LaTeX manuscript from the frozen blueprint, claims, sources, and optional canonical facts. The main model owns the scientific argument, cross-section consistency, equations, terminology, citation support, and prose; deterministic checks protect structure, provenance wiring, and the reader-facing boundary.
---

# ts-paper-write

Read `../ts-research-lifecycle/references/bounded-execution-contract.md` and the lifecycle reasoning
reference. Draft only after the active Idea,
claims, research program, publication contract, blueprint, and required source coverage are stable.

## Build one argument, not independent sections

Read the complete evidence bundle before writing: literal seed and selected Idea, closest work,
science/venue profiles, active claims and allowed wording, research program, canonical facts and failed
conditions, bibliography coverage, figure/table roles, limitations, and blueprint.

Create an internal argument map from each essential claim to its assumptions, mechanism or basis,
method/protocol, evidence, alternatives, limitations, and conclusion wording. Draft all sections in
one coordinated pass so title, abstract, introduction, methods, results, discussion, conclusion, and
appendices use the same scope, terminology, notation, units, populations/conditions, and claim
strength.

Use domain-appropriate organization. Do not force an experiments section, contribution count,
equation, pseudocode, ablation, main table, or subsection pattern. Explain code by its scientific
meaning, not line-by-line syntax.

## Evidence modes

**Proposal:** use future or conditional language for planned evaluations and unknown outcomes.
Protocol constants and cited facts are allowed; invented measurements are not.

**Exploratory/empirical:** report only canonical facts authorized by active claims. Preserve
denominator, population/condition, uncertainty, comparison, units, mixed/negative outcomes, and scope.
Use `ts-paper-data` to create exact result bindings.

For each material sentence, ask whether its cited source or fact supports that exact wording, whether
an alternative explanation remains, and whether causal or general claims exceed the design. A valid
number does not make the surrounding interpretation valid.

## Reader-facing boundary

The manuscript contains scientifically useful reproducibility information: data provenance at an
appropriate public level, methods, software/version identifiers when reader-relevant, protocol,
settings needed to reproduce, and limitations. Internal SHA-256 inventories, gate ledgers, lifecycle
paths, command transcripts, approval IDs, audit tables, and release plumbing stay in the artifact
package. Never create an appendix of hashes or commands to increase page count.

Every section and appendix must answer a reader-relevant scientific question. Add content only for a
missing explanation, derivation, comparison, boundary condition, robustness check, negative result,
or limitation. Do not repeat the same motivation, contribution, method summary, or result in several
forms.

Write `sections/<id>.tex` and `sections/abstract.tex` without top-level document commands. Then run:

```bash
python scripts/draft_lint.py <workdir>
python scripts/manuscript_boundary_lint.py <workdir>
python ../ts-paper-cite/scripts/citations_lint.py <workdir>
python scripts/reflow_tex.py <workdir>
```

Fix exact missing-file, placeholder, LaTeX, citation-key, result-binding, and internal-boundary
failures. Word targets and phrase warnings are advisory; the main model decides semantic quality.
