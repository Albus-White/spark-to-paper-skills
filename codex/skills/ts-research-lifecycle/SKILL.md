---
name: ts-research-lifecycle
description: Manage the v5 single research-to-publication state across user policy, Idea seed and selection, science and venue calibration, versioned Ideas and claims, frozen research programs, governed evidence, publication contracts, manuscripts, semantic judgments, compilation, and release audit.
---

# ts-research-lifecycle

This skill owns lifecycle state and exact provenance. It does not decide whether an Idea is novel,
an experiment is scientifically adequate, code implements the intended mathematics, prose is
coherent, or a figure communicates well. Those are explicit main-model judgments bound to evidence.

Read the references in this skill before the corresponding phase. The lifecycle under
`<workdir>/research` is the sole source of truth.

Always read `references/bounded-execution-contract.md`; every iterative stage must declare finite
attempt, time, and no-progress stops.

## Initialize and register intake

```bash
python scripts/lifecycle.py --root <research> init --profile <profile> --run-id <id>
python scripts/lifecycle.py --root <research> register-resource-envelope --file <resources.json>
python scripts/lifecycle.py --root <research> register-user-policy --file <policy.json>
python scripts/lifecycle.py --root <research> register-idea-seed --file <seed.json>
```

Empirical profiles require a user-confirmed capability envelope. Store capabilities and target
identities, never credentials.

## Calibrate science and venue independently

Register a full-text-bound science profile after the seed. It records topic literature and
scientific/writing conventions. Then freeze a comparable accepted-paper venue corpus before
downloading it, register PDF-bound observations, and add a separate venue judgment.

```bash
python scripts/lifecycle.py --root <research> register-science-profile --file <science.json>
python scripts/lifecycle.py --root <research> register-venue-corpus --file <corpus.json>
python scripts/lifecycle.py --root <research> register-venue-profile --file <venue.json>
python scripts/lifecycle.py --root <research> set-venue-judgment --file <venue-judgment.json>
```

Venue metrics record universal counts plus domain-authored figure roles, evaluation kinds, evidence
dimensions, and difficulty. Different papers may use different vocabularies. Aggregation treats them
as observations, never automatic quotas.

## Register optional memory and Idea selection

Paper Wiki is optional read-only memory. Snapshot it before discovery; a changed snapshot cannot
silently mutate an active Idea.

```bash
python scripts/lifecycle.py --root <research> register-memory-snapshot --file <snapshot.json>
python scripts/lifecycle.py --root <research> register-idea-candidates --file <candidates.json>
python scripts/lifecycle.py --root <research> register-idea-selection --file <selection.json>
python scripts/lifecycle.py --root <research> register-idea --file <idea.json>
```

The first active Idea must exactly match the selected candidate on its scientific fields. Later Idea
versions record revision level and approval. L2-L4 changes require user approval; test-informed
changes invalidate confirmation until independent evidence exists.

## Freeze one research program

The research program binds active policy, science profile, venue profile, claims, benchmark decision,
adaptive feasibility probes, resources, and claim-linked evaluation units. It uses
`research_program_id` everywhere; there is no second experiment contract.

The main model writes a G3 scientific judgment. Record approval with action
`FREEZE_RESEARCH_PROGRAM`, scope equal to the active Idea, and the judgment in its evidence, then run:

```bash
python scripts/lifecycle.py --root <research> freeze-research-program \
  --file <research-program.json> --approval <AP-id>
```

Evaluation units are domain-neutral. Applicable public benchmarks require acquisition and
reproduction. Empirical programs require at least one measured dominant-cost probe and a deadline-fit
resource plan; proposal programs may be planned-only.

## Govern code, runs, branches, and facts

Pin repository origin, exact commit, license, cleanliness, and modification mode. Lock the selected
execution environment. Formal run manifests name `evaluation_unit_ids`, repository/environment locks,
replicate identity, protocol and input hashes, test access, status, and failure class.

Use `run_iteration.py` for bounded execution. Automatic retries are limited to infrastructure
failures. Implementation/dependency failures require a material state change; protocol failures
reopen design; unsupported hypotheses remain evidence.

Scientific alternatives use `propose-branch` and `evaluate-branch`. Branch count/depth comes from the
research program, and negative/inconclusive branches stay in the ledger. Canonical result facts bind
claim IDs to compatible completed runs, evaluation units, raw artifacts, and aggregation code.

## Freeze publication and manuscript artifacts

After claims stabilize, derive an observed envelope with `derive_publication_envelope.py`. The main
model selects justified targets and freezes a publication contract after scoped approval. Register
bibliography coverage and figure routing against that exact contract.

Figure class determines route: measured evidence, original observation, exact structure, or
explanatory synthesis. Only explanatory synthesis requires PaperBanana. DrawAI is conditional after
raster approval.

Register only reader-facing manuscript files. The allowlist excludes research state, code, data,
logs, caches, credentials, and internal audit material. Register the exact LaTeX verdict and compiled
PDF, then a Publication Judgment that binds and confirms actual-PDF review. The deterministic release
audit cannot substitute for this semantic judgment.

## Gates and invalidation

Semantic gates require structured model judgments only where scientific reasoning is needed. Exact
gates reject model self-report for facts code can establish. High-risk G3/G7/G12/G14/G16 require
independence; high-risk release also requires scoped human confirmation.

Every gate stores evidence hashes. Changed policy, seed, corpus, profile, Idea, protocol, repository,
environment, result source, manuscript, figure route, or compile verdict invalidates only its
dependents. Editorial changes do not erase valid empirical evidence. Run `validate` before every
release transition.
