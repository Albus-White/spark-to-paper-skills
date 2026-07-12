---
name: ts-research-lifecycle
description: Manage the single evidence and state lifecycle for grounded research, including profile-specific phases, versioned Ideas and claims, model-authored scientific judgments, scoped approvals, feasibility-tested contracts, repository and environment locks, bounded runs, result provenance, invalidation, Idea evolution, and manuscript release. Use whenever a paper needs grounded design, experiments, result-backed claims, recovery, or auditable scientific decisions.
---

# ts-research-lifecycle

Use this skill as the only scientific state for a run. Other skills import artifacts into it; none may
create parallel Idea, contract, experiment, result, or manuscript truth.

## Read first

- `references/reasoning-and-validation-boundary.md`
- `references/profiles.md`
- `references/state-transition-table.md`
- `references/gate-verdict-spec.md`
- `references/gate-artifact-contracts.md`
- `references/artifact-invalidation-rules.md`
- `references/bounded-execution-contract.md`
- `references/scientific-sanity-tests.md` before G8
- `references/scientific-branching-loop.md` before feedback-driven experiment branching
- `references/remote-experiment-execution.md` before remote execution
- `references/repository-governance.md` before repository acquisition or conflict resolution

## Start

```bash
python scripts/lifecycle.py --root <research> init --profile <profile> --run-id <id>
```

The profile writes its own legal phase sequence. Proposal does not traverse empirical gates;
exploratory cannot create confirmatory full runs; standard and high-risk follow the empirical path.

For empirical profiles, capture the user's confirmed time, compute, financial, storage, and review
constraints before sizing the design:

```bash
python scripts/lifecycle.py --root <research> register-resource-envelope \
  --file <resource-envelope.json>
```

The main model allocates this envelope across the evidence needed by the active claims. The lifecycle
does not supply a default research budget.

## Scientific gates

G1, G2, G3, G6, G7, G8, G9, G12, G13, G14, G15, and G16 require a structured
`scientific_judgment` written after the main model inspects raw evidence. Pass it with:

```bash
python scripts/lifecycle.py --root <research> set-gate Gx \
  --verdict PASS \
  --evidence <artifact> \
  --judgment <judgment.json> \
  --summary <short-summary>
```

The CLI validates structure and artifact hashes, not the scientific conclusion. High-risk G3/G7/G12/
G14/G16 judgments require an independent reviewer. `NOT_APPLICABLE` requires a rationale and the
counterfactual condition that would make the gate applicable.

## Contract freeze

For empirical profiles, run a representative feasibility microprobe before freezing. The contract
must bind the current resource-envelope hash and record measured cost, deadline fit, budget fit, and
evidence. The G3 judgment precedes freeze. Record an
approval with action `FREEZE_CONTRACT`, scope equal to the active `idea_id`, and the G3 judgment as
evidence; pass the resulting approval ID to `freeze-contract`.

Pipeline synchronization only imports candidates. It cannot pass G1-G3 or freeze a contract.

## Experiments and Idea evolution

Pin external repositories and lock the selected environment before formal runs. Use
`run_iteration.py` for finite retries and explicit failure classification. Let the main model design
the G8 verification suite from implementation-specific scientific risks; the validator checks only
that every declared applicable risk has passing executable evidence.

Classify failures before acting:

- infrastructure: bounded retry;
- dependency or implementation: repair, re-review, rerun affected evidence;
- protocol: revise contract and invalidate dependents;
- data/resource/license: stop or reduce scope explicitly;
- hypothesis unsupported: preserve the negative result and decide keep/narrow/revise/branch/reject.

When several decision-relevant alternatives remain, use the branch ledger rather than overwriting the
current implementation or launching an untracked search. The contract bounds branch count/depth;
selection prioritizes validity and discriminating evidence over a scalar metric.

```bash
python scripts/lifecycle.py --root <research> propose-branch --file <proposal.json>
python scripts/lifecycle.py --root <research> evaluate-branch <branch-id> --file <evaluation.json>
```

L2-L4 Idea changes require user approval. Test-informed changes require independent confirmation.

## Results and manuscript

Canonical empirical facts live in `evidence/results/results-manifest.jsonl`. Every fact binds to
completed run IDs, raw artifact hashes, claim IDs, and aggregation code/hash. Formal runs name frozen
contract experiment IDs, so G11 can validate the complete claim-to-experiment-to-run-to-fact path
deterministically.

Register only the manuscript allowlist (`main.tex`, `refs.bib`, template assets, `sections/`,
`figures/`, `assets/`). Research state, code, data, caches, and credentials are excluded.

```bash
python scripts/lifecycle.py --root <research> register-manuscript <paper-workdir>
python scripts/lifecycle.py --root <research> validate
```

Changed evidence, approval, result source, or manuscript hash invalidates its dependent verdict.
Passing a gate clears its previous blocker. Negative and stopped states remain valid auditable outputs.
