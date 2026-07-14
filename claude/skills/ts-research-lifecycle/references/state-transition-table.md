# V5 State Transitions

The executable authority is `scripts/lifecycle.py`.

Every profile begins:

`INTAKE -> USER_POLICY_LOCKED -> SCIENCE_PROFILED -> VENUE_PROFILED -> IDEA_DRAFTED -> IDEA_GROUNDED -> RESEARCH_CONTRACT_FROZEN`

The Idea seed is registered during intake. `SCIENCE_PROFILED` requires a full-text-bound science
profile. `VENUE_PROFILED` requires a pre-frozen accepted-paper corpus, PDF-bound venue profile, and
venue judgment. `IDEA_DRAFTED` requires candidate and selection artifacts plus one matching active
Idea.

Proposal proceeds to claim reconciliation without executable evidence. Exploratory permits governed
code, baseline, verification, pilot, mechanism diagnosis, and Idea decision but not confirmatory full
runs. Standard empirical and high-risk follow the full code/baseline/verification/pilot/confirmation/
mechanism/decision/revalidation/claim path authorized by the profile.

All profiles finish through one publication path:

`CLAIMS_RECONCILED -> PUBLICATION_CONTRACT_FROZEN -> CITATIONS_COMPLETE -> MANUSCRIPT_DRAFTED -> MANUSCRIPT_REFINED -> MANUSCRIPT_HARDENED -> FIGURES_COMPLETE -> LATEX_COMPILED -> RELEASE_AUDITED -> RELEASED`

Transitions are sequential. Evidence-backed terminal stop states are legal from any nonterminal
phase. Invalidation rolls back to the nearest legal phase for that profile while preserving old
artifacts as history.

`CODEBASE_LOCKED`, `FULL_EXPERIMENT_COMPLETED`, `PUBLICATION_CONTRACT_FROZEN`, `FIGURES_COMPLETE`,
and `RELEASE_AUDITED` require a current schedule checkpoint bound to the active research program. A
deadline miss records a bounded replan and blocks progression until a revised checkpoint fits.

Phases order work; they do not decide scientific answers. Specialized model judgments and exact code
checks remain separate.
