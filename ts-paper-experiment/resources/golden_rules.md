# Golden Rules

Authoritative, human-approved rules for the `ts-paper-experiment` skill. Candidate rules live in
`../memory/lessons_candidate.md` and are promoted here **only with explicit user approval**
(recorded in `../memory/rule_change_log.md`).

| ID | Rule |
|----|------|
| GR-001 | **Evidence first, writing second.** Establish what the evidence supports before writing claims. |
| GR-002 | **Do not polish before diagnosis.** Diagnose the research logic before improving prose. |
| GR-003 | **Rewrite abstract last.** Finalize the abstract only after logic and results are settled. |
| GR-004 | **No unsupported strong claim.** Strength of wording must match strength of evidence. |
| GR-005 | **Robustness requires robustness evidence.** Do not claim robustness without it. |
| GR-006 | **"Significant" requires statistical support.** Use statistical testing or repeated runs. |
| GR-007 | **Results describe; discussion interprets.** Keep observation and interpretation separate. |
| GR-008 | **Every table needs one message.** Each table/figure should convey one clear point. |
| GR-009 | **Final paper must be claim-evidence consistent.** Abstract↔intro↔method↔results↔conclusion align. |
| GR-010 | **Never fabricate** data, citations, results, or statistical significance. |
| GR-011 | **If experiments cannot be run, create an experiment requirements report** instead of inventing results. |
| GR-012 | **If a claim is only partially supported, use cautious language.** |
| GR-013 | **Judge the real contribution type, not one table row.** Identify whether the paper contributes a framework, model, algorithm, benchmark, dataset, system, empirical study, or application. The `Proposed` row not winning a metric does not invalidate a framework/benchmark/dataset contribution. See `contribution_type_rules.md`. |
| GR-014 | **Verify every reference; never invent citation fields.** State the verification source; complete, replace, remove, or merge as needed while preserving claim–reference alignment. See `reference_verification.md`. |
| GR-015 | **Each main-text table must earn its place.** A table must support a distinct claim; otherwise move it to an appendix or summarize in prose. Do not add tables just because results exist. |
| GR-016 | **No misleading figures/tables.** Honest axes/scales, defined `N/A`, captions that match content, values traceable to logs/CSVs. |
| GR-017 | **Gate external datasets on license/terms.** Report name, source, size, license/ToU, disk, runtime, and necessity before downloading; if the license/ToU is unclear, stop and ask. |
| GR-018 | **Results must be traceable to real executed code/logs.** A repaired paper is not complete until the reported results are traceable to real executed code/logs, and the code implements the method, baselines, metrics, and experiment protocol described in the manuscript. See `code_experiment_paper_consistency.md`. |
| GR-019 | **Raw table values must be recomputable from per-seed raw logs.** Every aggregated table/figure value must be reproducible by re-aggregating the per-seed raw logs (not copied from memory). See `raw_result_recomputation.md`. |
| GR-020 | **Compilation is not enough; check the rendered layout.** Successful LaTeX compilation does not guarantee a correct paper — the rendered PDF pages must be visually checked for overflow, broken tables/figures, missing references, and layout errors. See `rendered_pdf_layout_check.md`. |
| GR-021 | **Expensive or external-data experiments require a pre-run plan and user approval.** Before running costly experiments or downloading external data, present a pre-run plan (cost, disk, runtime, data, necessity) and get user approval. See `experiment_prerun_approval_gate.md`. |
| GR-022 | **NEVER label manuscript content as simulated / synthetic / fake / Monte Carlo / "not real".** The paper text must never say the data or results are simulated or illustrative. If real data are unavailable, either (a) run on real downloaded data faithful to the design, or (b) leave the result tables as forward-looking placeholders with a requirements report — but do **not** put simulated/synthetic numbers into the manuscript and do **not** describe any number as a simulation. A Monte Carlo may be used privately in `./workspace/` to check an estimator, but its numbers never enter `./paper/`. |
| GR-023 | **Be faithful to the paper's own experiment design.** Read the manuscript's Implementation Details / Experimental Design and reproduce exactly THAT: the datasets it names, the outcome/treatment it defines, the estimators it specifies. Do **not** substitute a different construct, outcome, method, or a simulation in place of the paper's stated design. If the stated design cannot be run, say so and write a requirements report — never quietly swap in an easier proxy and present it as the paper's experiment. |
| GR-024 | **Actually download the named open data before declaring "blocked".** When the design names open/public datasets (Zenodo, figshare, GitHub, official portals, CEADs, CHAP, monitoring archives, etc.), genuinely attempt to download and assemble them. Only after a real download attempt fails (truly licensed/paywalled/unavailable) may you write a requirements report. Do not assume data is unavailable and skip to a simulation/proxy. |
| GR-025 | **After running experiments, FILL the paper's existing result tables with the real numbers.** A result table left blank (`--`) after experiments have run is a failure, not an acceptable state. Fill the manuscript's own `main_results` / `secondary_results` / `ablation_results` tables in place; do not leave them blank while putting the numbers in separate new tables. Report insignificant/null results honestly (with SE and p), but the tables must carry the real values. |
| GR-026 | **Always commit and push to Overleaf at the end (push is ON by default).** Every completed run commits `./paper/` and pushes to the Overleaf remote (`OVERLEAF_GIT_URL` + `OVERLEAF_TOKEN` from `./.env`). Do not finish a run with un-pushed manuscript changes. Use the push helper; never run git in a parent repo; clone with `find -mindepth 1` (never delete the clone root) and remove any token-bearing clone afterward. |
| GR-027 | **Re-run the final consistency/review on the FINAL manuscript after any results change.** If the results, tables, abstract, or conclusion change (e.g., switching data sources), the Step 8–17 consistency / claim-evidence / narrative-integrity review and its reports must be re-run against the current `HEAD` — stale review reports describing a superseded version are not acceptable. |

## How to use

- These rules are always in force during repair.
- When two rules tension (e.g., narrative vs caution), caution and traceability win.
- Some rules are auto-applied per `paper_config.yaml > automation.auto_apply_rules`; others
  require asking the user (see `automation.ask_user_before`).
