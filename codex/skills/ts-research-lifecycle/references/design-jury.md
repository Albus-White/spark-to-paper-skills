# Scientific Design Review

Before G3, give the main model the active Idea, closest raw sources, benchmark decision, claim registry,
contract candidate, design evidence, and measured feasibility probe. Ask it to reason about estimand,
domain paradigm, benchmark fit, claim coverage, comparison/tuning fairness, evaluator meaning,
statistics, confounders, leakage, test protection, budget, negative interpretation, and conclusions the
design cannot support.

Write the structured G3 `scientific_judgment`. Add fresh independent review sized to consequence,
uncertainty, and disagreement when the profile is high-risk or a core design question is disputed.
Each reviewer receives the minimal raw artifact bundle and no parent conversation or intended answer.

Fix blocking issues once. Closure receives only the normalized issue, close criterion, relevant diff,
and evidence. Reopen full design review only after a material scientific change. Repeated review with
no new evidence stops as author-required or disclosed uncertainty.

The approval that freezes the contract uses action `FREEZE_CONTRACT`, scopes the active `idea_id`, and
cites the passing G3 judgment. File existence, a literal `APPROVED` string, or a reviewer count cannot
approve a design.
