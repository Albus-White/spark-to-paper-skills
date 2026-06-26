# Candidate Lessons

Candidate rules learned from paper repair runs. These are **NOT active**. They are promoted
into `../resources/golden_rules.md` **only with explicit user approval**, and the promotion is
recorded in `rule_change_log.md`. See `../scripts/promote_lessons.py`.

Append new candidates using the format below.

## Candidate rule format

```
Rule ID:
Observation:
Trigger:
Condition:
Action:
Scope:
Automation level: candidate / auto / ask-user
Source paper:
Status: candidate
```

---

<!-- Append candidate rules below this line -->

Rule ID: CAND-013
Observation: When real data were not on hand, the run wrote a Monte Carlo into `./paper/` and labeled it "Simulation results / not empirical estimates for China". The user rejected any "simulated/fake" wording in the manuscript.
Trigger: Real data unavailable at experiment time.
Condition: About to write numbers into `./paper/`.
Action: Never put simulated/synthetic numbers or the word "simulation" in the manuscript; use real downloaded data, or forward-looking placeholders + requirements report. (Promoted: GR-022.)
Scope: general
Automation level: auto
Source paper: AI-Enhanced Carbon Accounting Quality under EPT Law
Status: promoted (GR-022)

Rule ID: CAND-014
Observation: The experiment substituted a Monte Carlo / a different proxy instead of the datasets and design the paper itself states.
Trigger: Running the experiment stage.
Condition: Paper's Implementation/Experimental Design names specific data and a specific outcome/estimator.
Action: Reproduce the paper's stated design faithfully (its datasets, outcome, treatment, estimators); never swap in an easier proxy/simulation. (Promoted: GR-023.)
Scope: general
Automation level: auto
Source paper: same
Status: promoted (GR-023)

Rule ID: CAND-015
Observation: The run assumed the data were unavailable and went straight to simulation, instead of downloading the open datasets (CHAP on Zenodo, official monitoring archive, province rates) that were in fact downloadable.
Trigger: Design names open/public datasets.
Condition: Before declaring an experiment "blocked".
Action: Genuinely attempt the downloads (Zenodo/figshare/GitHub/official portals); only a real failed attempt justifies a requirements report. (Promoted: GR-024.)
Scope: general
Automation level: auto
Source paper: same
Status: promoted (GR-024)

Rule ID: CAND-016
Observation: After running experiments, the paper's three result tables were left blank `--` while the numbers were placed in separate new tables; the user flagged the empty tables.
Trigger: Experiments produced numbers.
Condition: The manuscript already has result tables.
Action: Fill the manuscript's own result tables in place with the real values; a blank `--` table after a run is a failure. Report null/insignificant results honestly with SE and p. (Promoted: GR-025.)
Scope: general
Automation level: auto
Source paper: same
Status: promoted (GR-025)

Rule ID: CAND-017
Observation: The finished paper was not pushed to Overleaf until the user asked; Overleaf was off by default.
Trigger: Run completion (and after every results change).
Condition: An Overleaf remote is configured (OVERLEAF_GIT_URL/TOKEN in ./.env).
Action: Always commit + push `./paper/` to Overleaf; push ON by default. Use the push helper; never run git in a parent repo; clone with `find -mindepth 1`; delete token-bearing clones. (Promoted: GR-026; paper_config push flags set true.)
Scope: general
Automation level: auto
Source paper: same
Status: promoted (GR-026)

Rule ID: CAND-018
Observation: After switching from the simulation to real data, the final review reports still described the superseded simulation version.
Trigger: Results/tables/abstract/conclusion change after the first review.
Condition: Step 8–17 reports already exist.
Action: Re-run the consistency/claim-evidence/narrative-integrity review on the current HEAD; never leave stale review reports. (Promoted: GR-027.)
Scope: general
Automation level: auto
Source paper: same
Status: promoted (GR-027)

Rule ID: CAND-019
Observation: Figure vectorization was run degraded (`--no-repair --max-rounds 1`) to save time, lowering quality; the user objected.
Trigger: Running ts-figure-optimize `run_reconstruction.py`.
Condition: Vectorizing a paper figure.
Action: Run the full measured multi-round repair by default; never pass `--no-repair`/`--max-rounds 1` to cut the loop unless the user explicitly opts into a degraded pass. (Promoted: ts-figure-optimize/SKILL.md Hard rules.)
Scope: figures
Automation level: auto
Source paper: same
Status: promoted (ts-figure-optimize Hard rules)

## Promoted / moved out (no longer candidates)

- **CAND-006…CAND-012** were validated by the user on 2026-06-14 and **promoted** into the formal
  skill (steps/resources/scripts/golden rules). They now live in `lessons_validated.md`; see
  `rule_change_log.md` for the decision. Do not re-add them here.
