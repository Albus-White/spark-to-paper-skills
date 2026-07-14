# Spark-to-Paper Research Lifecycle v5

This document describes the implemented architecture shared by the Codex and Claude Code
distributions.

## 1. Design objective

The system separates two kinds of correctness:

1. **Scientific and semantic correctness:** the main model reads raw sources and artifacts to judge
   literature relevance, novelty boundaries, design validity, code meaning, evidence interpretation,
   argument logic, prose consistency, and visual communication.
2. **Exact reproducibility and identity:** deterministic tools verify schemas, paths, hashes, source
   identities, commits, environments, limits, process outcomes, metric recomputation, citation wiring,
   artifact sets, image bindings, and LaTeX compilation.

Rules never promote a semantic proxy into proof. Model confidence never overrides an exact failed
check.

## 2. One lifecycle, one active scientific truth

Every run owns one `research/` tree containing user policy and resources, literal Idea seed, optional
memory snapshot, science and venue profiles, candidate/selection artifacts, one active versioned Idea,
claims, one frozen research program, governed code/runs/facts, one publication contract, one current
manuscript, semantic judgments, and release audit.

Specialized skills consume and update this state. They do not create a second experiment lifecycle,
story truth, venue study, result store, or manuscript pipeline.

## 3. Reference-project integration

The v5 design studies the cloned projects as sources of patterns, not templates to copy wholesale.

| Reference project | Retained | Deliberately rejected or narrowed | v5 destination |
|---|---|---|---|
| `AI-Scientist-v2` | bounded branch/journal history, failure-aware iteration, separation of debugging from scientific change | fixed ML stage/dataset assumptions, runtime inflation, scalar-metric winner selection | lifecycle branches, failure classes, Idea evolution, experiment skill |
| `idea2paper_product/Story2Paper` | evidence-first blueprint, cross-section narrative continuity, complete manuscript construction | a parallel narrative `story` object, fixed paper shapes, repeated whole-draft loops | Idea discovery, blueprint, one-pass writing/refinement |
| `idea2paper_product/Paper-KG-Pipeline` | reusable domain recall and source-linked patterns | embeddings/clusters as novelty proof, mandatory KG construction for one paper | optional `ts-research-memory`; fresh search remains canonical |
| `PaperBanana` | real Retriever→Planner→Stylist→Visualizer→Critic execution, field references, multi-candidate comparison | direct image-model calls relabeled as PaperBanana, generic box plans, use for exact scientific structures | explanatory-synthesis branch of `ts-paper-figure` |
| `DrawAI` | post-approval raster reconstruction, semantic SVG/PDF/PPTX, actual-output comparison | treating vectorization as figure generation, reconstructing existing born-vector/domain-native work | optional `ts-figure-optimize` tail |
| `paperjury` | holistic quote-backed review, issue normalization, focused closure | fixed courtroom fan-out and repeated reviewer multiplication | `ts-paper-review` and risk-proportional independent review |
| `paper-wiki` | structured cited research memory, paper/concept/gap links, compile/search/critique/ideate/teach workflow | wiki gaps as novelty, writable wiki state inside a paper run, mandatory wiki for one-off work | immutable optional snapshot via `ts-research-memory` |

`aaai_arr_idea_wiki` is an example user/domain Paper Wiki, not a lifecycle source of truth. The system
may snapshot it and run a fresh delta search before Idea selection.

## 4. Two calibrations before design

### Science profile

The science profile is bound to the literal seed and real local full text. It records current primary
field literature, closest work, benchmark/evaluator landscape, scientific conventions, evidence
conventions, writing conventions, open questions, freshness, and limitations. Leading field venues
are selected for relevance to the topic, not to estimate the target submission's page count.

### Venue profile

The venue corpus freezes comparable accepted-paper source identities and inclusion/exclusion criteria
before acquisition. The profile binds local PDFs and observes universal counts (pages, cited
references, figures, tables, evaluation count) plus domain-authored figure roles, evaluation kinds,
evidence dimensions, and difficulty. Different papers need not share one vocabulary. A separate venue
judgment reviews comparability, distortion, confidence, evidence program, and limitations.

Official venue rules are constraints. Accepted-paper statistics are an observed envelope, not quotas.

## 5. Idea discovery and memory

An optional Paper Wiki snapshot is immutable and read-only during discovery. It accelerates recall but
cannot establish novelty or rewrite the active Idea. The model always checks decisive claims against
primary sources and performs a fresh outward search.

The literal seed, science profile, venue context, benchmark landscape, resources, and optional memory
produce candidates. Each candidate includes falsifiers, alternatives, closest-work comparison,
minimum validation path, evidence, and reasons it may fail. A separate model judgment compares them
and selects one. A supplied proposal takes the same path with a faithful candidate.

## 6. Research program and code correctness

The research program binds every active claim to one or more domain-neutral evaluation units:
benchmark, experiment, simulation, observational analysis, qualitative study, proof, or artifact
evaluation. Units declare the question, protocol summary, positive/negative interpretation,
confounders, out-of-scope conclusions, difficulty, and stop condition.

The model selects units from scientific validity, field conventions, benchmark applicability, venue
observations, resources, and a measured dominant-cost probe. It does not copy an accepted-paper mean.

Code acquisition prefers official benchmark/author repositories, pins exact versions and licenses,
keeps upstream read-only, and governs adapters/patches. Version conflicts are resolved against
behavior, published protocols, reference tests, evaluator semantics, and affected outputs. The model
reviews implementation-to-method meaning and designs discriminative tests for ways code can run
without crashing yet answer the wrong question.

## 7. Bounded evidence loop and Idea evolution

```text
pilot -> observe -> classify -> repair/revise/stop -> rerun only affected evidence
```

Infrastructure may retry within budget. Dependency/implementation failures require a material change
and renewed checks. Protocol changes refreeze the research program. Data/license/resource failures
stop or narrow scope. Unsupported hypotheses remain negative evidence. Inconclusive outcomes do not
authorize tuning until positive.

Competing scientific alternatives use bounded branches with expected observations and explicit costs.
Idea revisions are versioned; changes to scope, estimand, mechanism, or core hypothesis invalidate
proportionate dependents. Evidence used to invent a new Idea cannot independently confirm it.

## 8. Canonical evidence and publication contract

Every run binds evaluation units, inputs/protocol, repository/environment locks, replicate identity,
test access, raw logs, status, and failure class. Canonical facts preserve:

```text
claim -> evaluation unit -> compatible run -> raw artifact + aggregation -> manuscript value
```

After claims stabilize, the publication envelope contains target-venue distributions, official rules,
user constraints, and observed evidence programs. The model selects page range, relevant unique
citation minimum, figure count, table count, section projection, and per-figure routes with rationales.
Outside-range choices require explained deviations. No global citation floor exists.

## 9. Writing, consistency, and artifact boundary

The blueprint forms one claim-to-section argument. Writing reads the whole evidence bundle and drafts
the complete paper once. Refinement checks horizontal consistency across title, abstract,
introduction, method, results, discussion, conclusion, equations, terminology, units, tables, figures,
and appendices.

Holistic review looks for unsupported novelty, logical fallacies, causal overreach, method-result
mismatch, alternative explanations, source misuse, contradictions, duplicated argument, filler,
hidden negative results, and weak limitations. Issues close through focused deltas.

Reader-facing reproducibility information remains in the paper. Internal hashes, gate ledgers,
commands, approval IDs, and audit inventories stay in the artifact package. The manuscript boundary
lint catches exact leakage patterns; the model decides whether all content is scientifically useful.

## 10. Figure program

Figures route by source of truth:

- measured evidence: deterministic/domain-native or original evidence, bound to facts;
- original observation: reviewed original media and faithful processing;
- exact structure: native renderer preserving geometry/topology/notation;
- explanatory synthesis: actual pinned PaperBanana five-stage execution.

PaperBanana input is hash-bound to the reviewed semantic plan and reference search. Candidate stage
traces, final images, selection, and fresh visual critique are preserved. DrawAI runs only after the
raster is scientifically approved, lacks a born-vector source, and preflight succeeds. An evidenced
unavailable state permits the reviewed raster, not a hand-drawn bypass.

## 11. Final PDF and release

LaTeX assembly proves build correctness only. After compilation, the model opens the actual PDF and
writes a Publication Judgment covering claim/argument consistency, cross-section consistency,
method-result alignment, redundancy/filler, internal-provenance separation, limitations/negative
results, figure roles, citation relevance, venue-scale substance, page range, and visible layout.

The release audit binds that semantic judgment and exact citation, fact, figure, artifact-set, and
compile verdicts to current hashes. Completion means the current claims and limitations are internally
consistent and auditable; it does not imply a positive result.

## 12. Security and remote execution

Credentials remain in environment, SSH agent, or external secret storage. Research state rejects
credential-like files and redacts logs. Remote execution locks target and environment fingerprint,
uses bounded timeouts, excludes secrets/caches from synchronization, and records outcome-unknown states
to prevent duplicate untracked execution.
