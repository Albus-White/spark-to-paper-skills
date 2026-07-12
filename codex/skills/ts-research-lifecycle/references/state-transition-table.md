# Profile-Specific State Transitions

The executable source is `scripts/lifecycle.py` (`PROFILE_PHASES` and `required_gates_for`).

`proposal`:

`INTAKE -> IDEA_DRAFTED -> IDEA_GROUNDED -> RESEARCH_CONTRACT_FROZEN -> MANUSCRIPT_HARDENED -> RELEASED`

`exploratory`:

`INTAKE -> IDEA_DRAFTED -> IDEA_GROUNDED -> RESEARCH_CONTRACT_FROZEN -> CODEBASE_LOCKED -> BASELINE_VERIFIED -> IMPLEMENTATION_VERIFIED -> PILOT_VERIFIED -> MECHANISM_DIAGNOSED -> IDEA_DECIDED -> CLAIMS_RECONCILED -> MANUSCRIPT_HARDENED -> RELEASED`

`standard_empirical` and `high_risk` use the complete G0-G16 empirical sequence.

Transitions must follow the active profile's next phase. Terminal stop states remain legal from any
nonterminal phase. Invalidation rolls back to the nearest legal phase in that profile.
