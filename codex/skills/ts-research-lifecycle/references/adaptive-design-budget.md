# Evidence-Grounded Design and Resource Budget

The main model sizes the research and manuscript from evidence. Fixed counts are not quality proxies.
Explicit user counts remain requirements when feasible and scientifically honest.

## User resource envelope

Before an empirical contract is frozen, ask the user once for the information they can provide:

- desired delivery deadline or maximum elapsed time;
- available local/remote compute, hardware count/type, access windows, and server target metadata;
- financial/API/storage limits;
- available human review time and non-negotiable deliverables;
- ordered priorities, such as scientific confidence, breadth, speed, venue readiness, or artifact quality.

Unknown values remain explicit. The model may propose conservative assumptions, but the user confirms
the resulting envelope. Never store credentials. Register `intake/resource-envelope.json` and bind its
hash into the frozen contract budget.

Run a representative microprobe, then estimate wall time, compute time, storage, external-service
cost, and review time. Allocate the user's envelope among essential confirmation, mechanism
discrimination, robustness/scope, independent revalidation, figures, and manuscript work according to
which artifacts most improve the final scientific decision. If the deadline does not fit, narrow the
claim or plan transparently before freeze.

## Venue and field evidence

Before choosing paper structure, figure/table count, or experiment breadth, the main model studies:

- official guidance for the user-selected venue, when supplied;
- recent accepted papers at that venue with a similar paper archetype and evidence type;
- relevant leading venue/journal papers when the target is unspecified or offers little detail;
- field conventions that change what constitutes adequate comparison, uncertainty, replication,
  qualitative evidence, or mechanism analysis.

Record sources, observations, and decisions in `venue-study.json`. Observed counts and ranges are
context, not requirements. The model explains why this paper needs fewer, similar, or more artifacts.

## Scientific sizing

Every essential claim receives a discriminative evaluation or proof unit. Add comparisons,
replications, conditions, ablations, robustness checks, or mechanism tests only when they address a
named claim, alternative explanation, venue expectation, or decision risk. Prefer artifacts that
answer several compatible questions without hiding units, uncertainty, or failures.

Use no figure or table when it adds no understanding. Combine related result views when scientifically
legible; separate them when combination would obscure semantics. Qualitative evidence includes
representative failures. Candidate generation expands only for a concrete unresolved visual defect.

Use the smallest review and experiment portfolio that resolves important uncertainty within the user
envelope. Stop when additional work will not change a claim/decision, the hypothesis is unsupported,
the resource envelope is reached, or remaining uncertainty must be disclosed.

System hard caps exist only to prevent runaway execution. They are not recommended research sizes and
must never be treated as targets.
