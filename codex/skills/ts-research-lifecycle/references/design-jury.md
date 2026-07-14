# Scientific Design Review

Before G3, give the main model the selected Idea, claims, closest primary sources, benchmark decision,
research-program candidate, design evidence, implementation constraints, venue observations, resource
plan, and measured feasibility probe.

Review the domain paradigm, estimand or target question, claim coverage, benchmark applicability,
comparison and tuning fairness, evaluator semantics, uncertainty/statistics, replication or
independence, confounders, leakage, test protection, implementation risks, positive and negative
interpretation, feasibility, and conclusions the design cannot support. Evaluation units may be
experiments, simulations, observations, qualitative studies, proofs, benchmarks, or artifacts.

Write one structured G3 scientific judgment. Add a fresh independent reviewer only when consequence,
uncertainty, fragility, or disagreement warrants it; high-risk G3 requires independence. Reviewers see
the minimal raw artifact bundle, not parent conversation or an intended answer.

Normalize blockers by root cause. Fix once and review the issue, close criterion, changed artifact,
and evidence. Reopen the whole design only after a material scientific change. Repeated review without
new evidence becomes disclosed uncertainty or author-required action.

Freeze approval uses action `FREEZE_RESEARCH_PROGRAM`, scope equal to the active `idea_id`, and cites
the passing G3 judgment. File existence, an `APPROVED` string, reviewer count, or schema validity
cannot establish scientific adequacy.
