---
name: ts-paper
description: Generate a complete, venue-formatted research paper from an idea, proposal, or verified results through one evidence-driven lifecycle. Use for end-to-end paper creation, including grounded design, optional experiments, evidence-bound writing, review, figures, and LaTeX compilation. Routes proposal, exploratory, standard empirical, and high-risk work without fabricating results or duplicating lifecycle state.
---

# ts-paper

Run one research lifecycle and one manuscript pipeline. Trust the main model with scientific and
semantic judgment; use code for facts it can establish exactly.

## Governing contracts

Read these before acting:

- `../ts-research-lifecycle/references/reasoning-and-validation-boundary.md`
- `../ts-research-lifecycle/references/state-transition-table.md`
- `../ts-research-lifecycle/references/gate-verdict-spec.md`
- `../ts-research-lifecycle/references/gate-artifact-contracts.md`
- `../ts-research-lifecycle/references/adaptive-design-budget.md`
- `../ts-research-lifecycle/references/bounded-execution-contract.md`

The lifecycle under `<workdir>/research` is the only research state. Never create an experiment-side
second lifecycle, and never infer a passing scientific gate from file existence.

## Route once

Choose the lightest profile that can support the user's intended claims:

| Profile | Use when | Empirical execution |
|---|---|---|
| `proposal` | No verified measured evidence is available or execution is out of scope | None |
| `exploratory` | Pilot evidence is useful but cannot support confirmatory claims | Pilot only |
| `standard_empirical` | Claims require executable confirmation | Baseline, verification, pilot, full run |
| `high_risk` | Medical, safety, legal, consequential, or unusually fragile claims | Standard path plus independent/human confirmation |

Initialize exactly once:

```bash
python scripts/init_research_run.py --workdir <workdir> --profile <profile>
```

Do not silently upgrade a profile because more work looks impressive. Do not downgrade it to avoid a
real integrity requirement.

## One canonical flow

### 1. Normalize and ground the Idea

Use `ts-idea2story` only for a raw Idea. Normalize a supplied proposal directly. Register the active
Idea, then search for closest work, relevant domain guidance, datasets, evaluators, repositories, and
benchmarks. G2 must classify the benchmark situation rather than force a benchmark to exist.

Before G3, keep artifacts deliberately scoped: a research brief, active claims, the closest sources
needed for open design questions, the benchmark decision, and a minimum falsification path. Do not build the final bibliography,
complete manuscript blueprint, or figures yet.

### 2. Check feasibility before contract freeze

For empirical profiles, ask once for the user's deadline, available GPU/server resources, financial
and storage limits, human-review availability, and priorities. Register the user-confirmed resource
envelope. Estimate data, runtime, storage, external-service, and review costs with a representative
microprobe. Let the main model allocate the envelope to the highest-value evidence. If the measured
projection misses the deadline or budget, reduce scope transparently or stop before freeze.

### 3. Let the main model judge the design

The main model reads raw sources, the Idea, benchmark decision, implementation constraints, and draft
contract. It must reason about estimand, comparison fairness, evaluator semantics, leakage, plausible
confounders, negative interpretation, and out-of-scope conclusions. Write a G3
`scientific_judgment` artifact. Use the smallest independent review set justified by risk or uncertainty;
review only the frozen artifact bundle, never the parent conversation.

Fix blockers once, then run a delta closure against the issue, close criterion, changed artifact, and
supporting evidence. Reopen full review only after a material scientific change. Obtain a scoped
`FREEZE_CONTRACT` approval ID and freeze the contract.

### 4. Follow the profile branch

**Proposal:** proceed directly to manuscript planning. State planned evaluations honestly, leave
outcomes unknown, and do not create fake empirical gates.

**Exploratory/empirical:** invoke `ts-paper-experiment` on the same research root. Acquire pinned
repositories, lock the environment, reproduce an applicable baseline, let the main model design
implementation-specific scientific tests, run pilot/full experiments within budget, diagnose
mechanisms, and decide whether to keep, narrow, revise, branch, or reject the Idea.

An Idea may evolve from evidence. Infrastructure and implementation repairs do not change the Idea;
protocol changes invalidate affected evidence; hypothesis failure is accepted as a scientific result.
If test evidence helped create a new Idea, confirm it with independent evidence.

### 5. Build the paper from stable evidence

Only after G3 for proposal mode, or after claim reconciliation for empirical modes:

1. Use `ts-paper-plan` to choose a paper archetype and sections for this work.
2. Use `ts-paper-cite` to complete only the references needed by actual claims.
3. Use `ts-paper-data` when verified results exist; every reported fact binds to the lifecycle results manifest.
4. Use `ts-paper-write` to draft the complete manuscript once.
5. Use `ts-paper-refine` for one holistic coherence pass.
6. Use `ts-paper-review` for risk-proportional adversarial review and delta closure.
7. Use `ts-paper-figure` for only the figures that materially communicate method or evidence.
8. Use `ts-paper-latex` to assemble and compile with the selected venue assets.

Scientific changes return to the lifecycle and invalidate dependents. Editorial changes stay in the
manuscript branch. Never run a second proposal-to-paper cycle after experiments.

## Model and code boundary

The main model owns:

- literature relevance and novelty comparison;
- benchmark applicability;
- experiment design and research-logic review;
- code meaning and implementation-to-mathematics alignment;
- failure interpretation, mechanism diagnosis, and Idea evolution;
- citation support, prose quality, claim strength, and visual semantics.

Deterministic tools own:

- schema, paths, hashes, commits, licenses, environment locks, budgets, and test access;
- process timeouts, exit status, raw outputs, metric recomputation, and result provenance;
- BibTeX structure and citation-key wiring;
- file completeness, placeholders, LaTeX assembly, and compilation errors;
- image existence, hashes, rendering artifacts, and actual-image review binding.

Never promote a heuristic score, regex, fixed count, or model self-report into proof of scientific
correctness. Never ask the model to assert a hash, compile result, or measured value that code can
verify exactly.

## Completion

Run stage-specific gates as artifacts become ready, then:

```bash
python scripts/run_gates.py <workdir> all
python ../ts-research-lifecycle/scripts/lifecycle.py --root <workdir>/research validate
```

The final route is complete only when the profile-specific lifecycle reaches `MANUSCRIPT_HARDENED`
or `RELEASED`, the current manuscript is registered, deterministic gates pass, and unresolved
scientific limitations are visible in the paper rather than hidden by more iteration.
