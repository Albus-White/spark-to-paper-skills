---
name: ts-paper-experiment
description: Repair an AI-generated scientific paper draft by diagnosing research logic, completing feasible experiments, rewriting the experiment section, and updating the full manuscript for claim-evidence consistency.
---

# ts-paper-experiment

> **Now part of the spark-to-paper-skills suite (Stage 8).** Previously a separate project
> (AutoPaperFactory); merged in so the whole pipeline lives in one repo. It runs in an **experiment
> workspace** (default `<ts_paper_run>/experiments/`, seeded by `ts-paper/scripts/handoff_to_experiments.py`
> with this skill's `paper_config.yaml` template). "Project root" below = that workspace. Overleaf is OFF
> by default; enable via the workspace `.env` (`OVERLEAF_GIT_URL`/`OVERLEAF_TOKEN`) — also in repo-root
> `.env.example`. References to "AutoPaperFactory" in the resource docs mean this same workspace.

Repair an AI-generated scientific paper draft into a more complete, honest manuscript. This
skill **diagnoses** the paper, **plans and runs only feasible experiments**, **edits the LaTeX
manuscript directly inside `./paper/`**, and **keeps the full paper claim–evidence consistent**.

## Working directory

**Assume Claude Code is always started from the project root** (the directory that contains
`./paper_config.yaml`). The project root is `.`. Use **relative paths only** — never absolute or
machine-specific paths. Key locations:

- `./paper_config.yaml` — project configuration
- `./draft_overleaf.zip` — the AI-generated Overleaf export (primary input)
- `./input/draft/` — alternative location for raw draft files
- `./paper/` — **the manuscript: the source of truth, an independent Git repo synced to Overleaf**
- `./workspace/` — diagnosis, experiment planning/runs, logs, lessons (never the manuscript)
- `./outputs/` — reports, analysis, exported figures/tables (never the source-of-truth manuscript)

## Manuscript Source of Truth

`./paper/` is the source of truth for the manuscript.

All LaTeX manuscript edits must happen directly inside `./paper/`.

Allowed manuscript files in `./paper/` include:

- `.tex`
- `.bib`
- `.sty`
- `.cls`
- figures
- tables
- section files

Do not put the following inside `./paper/`:

- diagnosis reports
- experiment logs
- raw datasets
- source code
- workspace files
- skill files
- large model files

## Non-negotiable rules

- **Never fabricate** results, numbers, tables, figures, citations, references, or statistical
  significance.
- Every reported number must be **traceable** to actual code execution, provided logs, provided
  data, or clearly marked author-provided results (`AUTHOR_TODO`).
- If an experiment **cannot be run**, write a requirements report — do **not** invent results.
- **Ask the user** before changing the main contribution, deleting the core method, adding a new
  experiment type, or making strong claims from weak results.
- **`./paper/` is the manuscript source of truth.** Do **not** create a competing "final"
  manuscript under `./outputs/final/`, and do **not** copy any file from `./outputs/` back into
  `./paper/`. Edit the manuscript in place inside `./paper/`.
- See `resources/golden_rules.md` and `resources/claim_evidence_rules.md` for the full policy.

---

## Correct Workflow

### Step 0: Entry check and Overleaf setup

**Embedded (ts-paper Stage 8) mode — the DEFAULT in this suite, and it AUTO-RUNS.** When driven by the
ts-paper orchestrator, the draft is ALREADY staged under `./input/draft/` as a LaTeX manuscript
(`main.tex` + `sections/` + `refs.bib` + `figures/` + template `.sty` — **NOT a zip**), real experiment
inputs (if present) are under `./input/{data,code}`, and `overleaf.require_overleaf_url` is `false`.
In this mode **auto-proceed without stopping**: ingest `./input/draft/` into `./paper/` and run the full
workflow end-to-end — do **NOT** ask for a zip or an Overleaf URL. (The "stop and ask" prompts below apply
ONLY to standalone manual usage, never to embedded Stage-8 runs.)

- Check for the AI draft (at least one of): `./input/draft/` (the staged manuscript — **primary in the
  embedded workflow**), `./draft_overleaf.zip` (standalone only), or existing LaTeX files under `./paper/`.
- **Overleaf toggle (check first):** read `overleaf.require_overleaf_url` from `./paper_config.yaml`.
  - If it is **`false`** (Overleaf disabled): **skip the Overleaf Git target check, the URL ask, and all
    pushing entirely.** Work only on the local `./paper/` repo (init + local commits, **no remote, no
    push**), regardless of the `push_*` flags. Do not call `init_paper_overleaf.py --push`. Then continue
    to the draft check below.
  - If it is **`true`**: enforce the Overleaf Git target as described next.
- Check for the Overleaf Git target (at least one of): `overleaf.git_url` in
  `./paper_config.yaml`, or `OVERLEAF_GIT_URL` in `./.env`, or an existing remote named
  `overleaf` inside `./paper/`. (`paper_config.yaml` takes precedence, then the `.env` value.)

If the AI draft is missing **(standalone manual usage only — in embedded Stage-8 mode `./input/draft/`
is always present, so never reached)**, **stop and ask**:

> Please provide the AI draft. Put an Overleaf project zip at ./draft_overleaf.zip, or place the draft files under ./input/draft/.

If `require_overleaf_url` is **`true`** and the Overleaf Git URL is missing, **stop and ask**:

> Please provide the Overleaf Git URL. Create a blank Overleaf project first, open Git Integration, and paste the Git URL into ./paper_config.yaml under overleaf.git_url.

**Security rule:** Do not ask for passwords or tokens in the prompt. For non-interactive pushes,
the user can create a `./.env` file with `OVERLEAF_GIT_URL` and `OVERLEAF_TOKEN`. The token is
read only from `./.env`, is **never** stored in `paper_config.yaml`, **never** written into the
git remote URL, and **never** printed. `scripts/init_paper_overleaf.py` supplies it to git via a
temporary askpass helper. `./.env` is gitignored and must never be committed. A Git credential
helper or SSH also works.

Then:

- **Extract/copy the AI draft directly into `./paper/`** (unzip `./draft_overleaf.zip` and/or copy
  `./input/draft/` files into `./paper/`).
- **Initialize `./paper/` as an independent Git repository.**
- **Commit the original AI draft** inside `./paper/` with message: `Initial import of AI draft`.
- **Push the original AI draft** to the Overleaf remote if configured
  (`overleaf.push_initial_draft`).

You may use the helper `scripts/init_paper_overleaf.py` (add `--push` to push). Never run git in
the parent AutoPaperFactory repository for paper content.

### Step 1: Diagnose the paper

- **Read the manuscript files directly from `./paper/`** (the `.tex`/`.bib` sources).
- Read `paper_config.yaml` and the resources: `methodology_core.md`, `golden_rules.md`,
  `anti_patterns.md`, `experiment_templates.md`, `claim_evidence_rules.md`,
  `contribution_type_rules.md`, `human_scientific_style.md`, `sci_q4_review_checklist.md`,
  `reference_verification.md`, `experiment_table_audit.md`, `publication_polish_check.md`,
  `final_submission_checklist.md`, `post_repair_narrative_review.md`, `dataset_license_gate.md`,
  `code_experiment_paper_consistency.md`, `raw_result_recomputation.md`,
  `rendered_pdf_layout_check.md`, `reproducible_artifact_packaging.md`,
  `experiment_prerun_approval_gate.md`.
- **Write diagnosis reports to `./workspace/diagnosis/`:**
  - `DIAGNOSIS.md`, `PAPER_LOGIC_MAP.md`, `EXPERIMENT_GAP_REPORT.md`.
- The diagnosis must identify: paper **topic**, **research problem**, claimed **contribution**,
  **method**, **current experiments**, **missing experiments**, **unsupported claims**, and
  likely **SCI Q4 readiness issues**. Do **not** polish prose yet (GR-002).

### Step 2: Plan experiments

- **Write the experiment plan to `./workspace/experiments/EXPERIMENT_PLAN.md`** specifying:
  which experiments are **necessary**, which are **feasible** with available data/code, which are
  **blocked** (and why), **metrics**, **baselines**, expected **outputs**, and **commands/
  scripts** to run. Use `resources/experiment_templates.md`. Plan the **minimum** set.
- **Pre-run plan & resource approval gate (GR-021).** Before running **expensive** experiments or
  **downloading external data**, present a pre-run plan and **get explicit user approval**. Write
  `./outputs/reports/PRERUN_PLAN_APPROVAL.md` covering, per experiment: estimated **runtime**,
  **disk**, **compute/cost**, **external data** needed (with the Dataset / License / Terms Gate,
  Step 3), and whether it is **needed for an essential claim**. Cheap, local, already-available
  runs may proceed without a separate approval; costly/external ones must wait for approval. See
  `resources/experiment_prerun_approval_gate.md`.

### Step 3: Run feasible experiments

- If data/code are available, inspect `./input/code/`, run existing scripts or create **minimal**
  scripts only when necessary, and use the seeds in `paper_config.yaml`.
- **Dataset / License / Terms Gate (mandatory before any external dataset download or use).**
  Before downloading or using an external dataset, report (see
  `resources/dataset_license_gate.md`): dataset **name**; **source URL**; expected **download
  size**; **license / terms-of-use** status; whether **user confirmation** is required; **disk**
  requirement; estimated **runtime**; and whether the dataset is **needed for essential claims**.
  **If the license/ToU is unclear, stop and ask the user.**
- **Write experiment logs/results to `./workspace/experiments/` and `./outputs/`** (final
  tables/figures to `./outputs/tables/` and `./outputs/figures/`).
- **Do not put logs, raw data, or code into `./paper/`.**
- **Never hardcode fake numbers.** Create `workspace/experiments/EXPERIMENT_RUN_REPORT.md`. If
  experiments cannot be run, create `workspace/experiments/EXPERIMENT_REQUIREMENTS.md` instead.

### Step 4: Analyze results

- **Write the result analysis to `./outputs/reports/RESULT_ANALYSIS.md`**: main findings; whether
  each original claim is supported (labels from `resources/claim_evidence_rules.md`); weak or
  negative results (do not hide them); limitations; which claims must be weakened or removed.

### Step 5: Code–Experiment–Paper Consistency Gate (MANDATORY)

Before any reported number is written into the manuscript, verify that the evidence is **real** and
that the **code matches the paper**. This gate reads the current paper project's evidence
(`./input/code/`, `./workspace/experiments/`, `./outputs/`) — it does not invent or run anything
new here. See `resources/code_experiment_paper_consistency.md`. Produce six reports under
`./outputs/reports/`:

1. **`RESULT_PROVENANCE_AUDIT.md`** — every numeric value in tables/figures must trace to:
   **dataset**, **model/variant**, **seed**, **metric**, **source JSON/CSV/log path**, and
   **aggregation script**. **No value may be guessed, manually invented, or written from memory.**
   **Recompute each reported value from the per-seed raw logs** and confirm it matches (GR-019);
   record mismatches. See `resources/raw_result_recomputation.md`; the helper
   `scripts/check_result_recomputation.py` aggregates per-seed logs to assist this check.
2. **`EXPERIMENT_COMPLETENESS_AUDIT.md`** — for every reported table/figure, verify all reported
   **model × dataset × seed × metric** combinations were actually run. Classify each combination as
   `FULLY_RUN`, `PARTIALLY_RUN`, `NOT_RUN_BUT_NOT_CLAIMED`, or `CLAIMED_BUT_NOT_RUN`.
3. **`CODE_PAPER_CONSISTENCY_AUDIT.md`** — verify the code implements what the paper describes
   (components, corruption protocol, all baselines, all ablations, all metrics). **If the paper
   describes a component the code does not implement, stop and report.** The helper
   `scripts/check_code_paper_consistency.py` scans `./input/code/` for expected artifact types to
   assist this check.
4. **`EXPERIMENT_DESIGN_CORRECTNESS_AUDIT.md`** — check for train/test leakage, correct split
   protocol, seeds actually used, task-appropriate metrics, truly-not-applicable `N/A` cells,
   offset MAE only where offset labels exist, retrieval metrics only for models with alignment
   scores, and that cross-dataset replication is not falsely described as zero-shot transfer.
5. **`CODE_ARTIFACT_COMPLETENESS_AUDIT.md`** — check that preprocessing, feature extraction, model
   definitions, baseline definitions, training script, evaluation script, table/figure generation
   script, and config/documented commands are preserved. If code only exists as scratch scripts,
   report a **reproducibility risk**. Use `resources/reproducible_artifact_packaging.md` for the
   target packaging layout.
6. **`EXPERIMENT_TRUTHFULNESS_VERDICT.md`** — a single overall verdict, one of:
   `FULLY_TRACEABLE_AND_CONSISTENT`, `TRACEABLE_WITH_MINOR_GAPS`, `PARTIAL_TRACEABILITY_RISK`,
   `CODE_PAPER_MISMATCH`, or `UNVERIFIED_RESULTS_RISK`.

**Enforcement:** never write a number that fails provenance. If anything is `CLAIMED_BUT_NOT_RUN`,
or the verdict is `CODE_PAPER_MISMATCH` / `UNVERIFIED_RESULTS_RISK`, weaken or remove the affected
claim, or stop and ask the user — do not fabricate (GR-018).

### Step 6: Rewrite the experiment section

- **Edit the relevant `.tex` files directly inside `./paper/`** to rewrite the experiment section:
  setup, dataset, baselines, metrics, implementation details, main results, and any available
  ablation/sensitivity/efficiency/qualitative analysis, plus limitations.
- Use safe phrasing from `resources/result_writing_patterns.md`. Results describe observations;
  interpretation belongs in the discussion (GR-007). Every table/figure must be traceable to a
  log/CSV/author file.

### Step 7: Classify contribution type and claims (before claim-evidence checking)

- Identify the paper's **true contribution type** using `resources/contribution_type_rules.md`:
  framework / model / algorithm / benchmark / dataset / system / empirical study / application
  paper. **Do not assume the `Proposed` row in a results table is the whole contribution** (GR-013).
- Label each major claim with a **claim type**: framework claim / method-or-model claim /
  benchmark-or-protocol claim / dataset claim / empirical result claim / efficiency claim /
  limitation claim / future-work claim.
- **Write `./outputs/reports/CLAIM_TYPE_CLASSIFICATION.md`** and use it to keep the next step's
  claim-evidence checking aligned with the actual contribution (not just one table row).

### Step 8: Full manuscript consistency repair

- **Edit the abstract, introduction, method, results, discussion, and conclusion directly inside
  `./paper/`** so the whole paper is claim–evidence consistent.
- **Rewrite the abstract last** (GR-003). Do not use "significantly" without statistical/
  repeated-run support; do not claim robustness/generalization without evidence; weaken, remove,
  or `AUTHOR_TODO` unsupported claims.
- **Write `./outputs/reports/CLAIM_EVIDENCE_CHECK.md`** recording each claim's type (Step 7),
  label, evidence artifact, and action.

### Step 9: Human scientific style pass

- **Apply `resources/human_scientific_style.md` directly to the manuscript files in `./paper/`**:
  one sentence one idea, short sentences, remove AI filler and empty adjectives, no grandiose
  claims, every paragraph starts with a clear point, claim strength matches evidence. Do **not**
  attempt to bypass AI detection — focus on clarity, accuracy, and scientific style.

### Step 10: Experiment Table Necessity Audit

Per `resources/experiment_table_audit.md`, **write
`./outputs/reports/EXPERIMENT_TABLE_NECESSITY_AUDIT.md`**:

- Every **main-text** experiment table must support a **distinct** manuscript claim.
- **Do not add tables just because results are available.**
- If a table is too detailed for the main paper, **move it to appendix/supplement/report or
  summarize in prose**.
- For each table, state: the **exact claim supported**; **keep in main text / move to appendix /
  remove**; and the **reason**.
- **Do not remove source results or logs.** **Do not change numeric values** unless a
  traceability mismatch is found. Apply approved keep/move decisions by editing `./paper/`.

### Step 11: Figure/Table Publication Polish Check

Per `resources/publication_polish_check.md`, **write
`./outputs/reports/PUBLICATION_POLISH_CHECK.md`** checking:

- table **width and readability**; table **numbering and references**;
- **N/A / `--` definitions**, and whether missing cells are **truly not applicable**;
- **caption clarity**; figure **legend–marker consistency**;
- figure **title/caption matches what the figure actually shows**;
- figure **supports the surrounding claim**; **no misleading visualization**;
- values **trace to CSV/JSON/logs**.

Fixes are applied by editing the manuscript in `./paper/` (never change values without a
traceability reason).

### Step 12: Reference Verification

Run **after manuscript repair and before the final submission checks**. Per
`resources/reference_verification.md`, **write
`./outputs/reports/REFERENCE_VERIFICATION_REPORT.md`**:

- **Every bibliography entry must be verified**, and the report must **state the verification
  source** for each (search results alone are not enough).
- **Do not invent** authors, years, venues, pages, DOI, arXiv ID, or URLs.
- If a reference is **real but incomplete**, complete it from reliable sources.
- If a reference **cannot be verified**, remove it or replace it with a real, related reference.
- If a reference is **duplicated**, merge/remove the duplicate.
- Citation changes must **preserve claim–reference alignment**.
- Reliable sources include official publisher pages, **CVF, IEEE, ACM, AAAI, NeurIPS, ICLR,
  arXiv, PubMed, DBLP**.

### Step 13: SCI Q4 review checklist

- Run `resources/sci_q4_review_checklist.md` and **write the review report to
  `./outputs/reports/SCI_Q4_READINESS.md`** (per-item pass/fail + a readiness score).
- If fixes are needed, **edit the manuscript files directly inside `./paper/`**.
- You may run `scripts/consistency_check.py` to scan the `./paper/` `.tex` files for risky terms.

### Step 14: Rendered PDF Layout Check

Successful LaTeX compilation is **not** sufficient (GR-020). Compile the manuscript in `./paper/`
and **visually check the rendered PDF pages**. Write `./outputs/reports/PDF_LAYOUT_CHECK.md` (see
`resources/rendered_pdf_layout_check.md`). Check for:

- overfull/underfull boxes and text running into the margins;
- broken or oversized tables/figures; figures off-page or overlapping;
- missing/`??` references, citations, or undefined labels in the rendered output;
- caption placement and numbering correct on the page;
- equations not clipped; fonts embedded;
- overall page layout consistent with a submittable manuscript.

The helper `scripts/check_pdf_layout.py` locates the compiled PDF under `./paper/` and reports page
count / render hints (using `pdfinfo`/`pdftoppm` if available). Apply fixes by editing `./paper/`.
Do **not** commit the rendered PDF or page images to the AutoPaperFactory repo.

### Step 15: Final Submission Checklist

Per `resources/final_submission_checklist.md`, **write
`./outputs/reports/FINAL_SUBMISSION_CHECKLIST.md`** checking:

- author names not placeholder; affiliations not placeholder; corresponding email not placeholder;
- DOI placeholder handled; references complete and verified; no title-only references;
- figures readable; tables readable; table/figure numbering correct;
- no undefined refs/citations; no overfull boxes;
- no fake significance claims; no unsupported SOTA/best claims; no fabricated numbers;
- **no unresolved `AUTHOR_TODO`** in the manuscript;
- **Overleaf remote sync status**.

If any item fails, fix it in `./paper/` (or flag it to the user) before the final commit/push.

### Step 16: Commit and push repaired manuscript

- Run `git status` **inside `./paper/`**.
- If manuscript files changed, **commit inside `./paper/`** with a clear message:
  `Repair manuscript after experiment and consistency review`.
- **Push to the Overleaf remote** if configured (`overleaf.push_after_repair`).
- **Never run git commit/push in the parent AutoPaperFactory repository for paper content.**

### Step 17: Post-repair review (FINAL MANDATORY STEP)

This is the **final mandatory step**, run **after** manuscript repair, the consistency check, the
commit, and the Overleaf push. It compares the repaired manuscript against the original imported
AI draft and judges whether the paper is overall better or worse. See
`resources/post_repair_narrative_review.md`.

**Determine the two versions from git history inside `./paper/`:**

- **Original** = the **initial commit** in `./paper/` (the `Initial import of AI draft`). Find it
  with `git -C paper rev-list --max-parents=0 HEAD`.
- **Repaired** = the **final `HEAD`** of `./paper/`.
- Inspect the difference with `git -C paper diff <initial>..HEAD` (and `--stat` for an overview).

Base every statement in both reports on the **actual diff** and on the evidence in
`workspace/experiments/` and `outputs/reports/`. Do **not** fabricate improvements; do **not**
hide negative findings.

#### 10a. `outputs/reports/ORIGINAL_TO_REPAIRED_CHANGELOG.md`

Compare the repaired manuscript against the original imported AI draft. The report must answer:

- What changed in the **abstract**?
- What changed in the **introduction**?
- What changed in the **method** section?
- What changed in the **experiment** section?
- What changed in **tables and figures**?
- Which claims were **strengthened**?
- Which claims were **weakened**?
- Which claims were **removed**?
- Which **placeholders or unsupported statements** were fixed?
- Which changes were caused by **real experimental evidence** (trace to logs/CSVs in
  `workspace/experiments/` or `outputs/`)?

#### 10b. `outputs/reports/FINAL_NARRATIVE_INTEGRITY_REVIEW.md`

Judge whether the final paper is overall **better or worse** than the original draft. The report
must answer:

- Is the **core contribution** still valid after evidence-based revisions?
- Did the real experimental results **damage the paper's central story**?
- Is the final **narrative coherent** from abstract to conclusion?
- Are the **claims, tables, and discussion aligned**?
- Does the paper still have **publishable value**?
- Did the repair turn the paper into a **weaker but more honest** proposal, or a **stronger
  empirical** paper?
- What are the **remaining narrative risks**?
- What should the **author do next** to further improve the paper?

**Final verdict** — use exactly one of these labels:

- `SIGNIFICANTLY_IMPROVED`
- `IMPROVED_BUT_WEAKER_CLAIMS`
- `HONEST_BUT_STILL_WEAK`
- `NARRATIVE_DAMAGED`
- `NOT_READY`

**Judgment rules:**

- Do **not** judge only by whether the proposed method wins.
- Judge the **whole paper**: motivation, task value, evidence, writing, coherence, and
  publishability.
- Be honest if the experiments **weaken** the original story.
- Do **not** hide negative findings. Do **not** fabricate improvement.
- If the final paper is **worse in narrative quality**, say so clearly (e.g.,
  `NARRATIVE_DAMAGED`).

### Step 18: Lessons (self-evolution)

- Create `workspace/lessons/LESSONS_LEARNED.md`: what worked, what failed, repeated AI-draft
  problems, useful user decisions, candidate golden rules.
- Append candidate rules to `.claude/skills/ts-paper-experiment/memory/lessons_candidate.md`.
- **Do not** auto-promote candidates into `resources/golden_rules.md`; promotion needs explicit
  user approval and is recorded in `memory/rule_change_log.md`.
- Run **Active Suggestion Capture** (below) and print the closing message.

---

## Active Suggestion Capture

During every paper repair task, Claude Code must actively watch for improvement opportunities.

It should capture suggestions in these categories:

1. **Writing rules**
   - recurring AI-style writing problems
   - unclear paragraph structure
   - overlong sentences
   - repeated filler phrases
   - weak claim-evidence alignment

2. **Experiment rules**
   - commonly missing baselines
   - commonly missing metrics
   - useful ablation patterns
   - robustness tests that should become templates
   - repeated experiment failures

3. **Workflow rules**
   - steps that should be automated
   - repeated user decisions
   - unnecessary manual steps
   - Overleaf/Git workflow improvements

4. **Safety and integrity rules**
   - risks of fabricated results
   - unsupported claims
   - fake citations
   - statistical language misuse

5. **Skill improvement rules**
   - missing checklist items
   - unclear SKILL.md instructions
   - missing scripts
   - reusable prompts
   - candidate golden rules

### Required output after each task

Claude Code must create or update `./workspace/lessons/SUGGESTIONS_FOR_USER.md` using this
format (one block per suggestion, numbered `SUG-001`, `SUG-002`, ...):

```md
# Suggestions for User Review

## Suggestion SUG-001

Category:
writing / experiment / workflow / safety / skill

Observation:
What happened in this paper?

Trigger:
When should this suggestion apply?

Suggested rule or change:
What should be added or changed?

Recommended action:
accept / reject / revise / observe more

Scope:
general / ML papers / image papers / NLP papers / this paper only

Automation level:
manual / ask-user / auto

Risk:
low / medium / high

Reason:
Why this suggestion matters

User decision:
PENDING
```

### Capture rules

- Also append a **compact** candidate rule for each suggestion to
  `./.claude/skills/ts-paper-experiment/memory/lessons_candidate.md` (use the candidate format in
  that file).
- **Do not edit** any of the following unless the user explicitly approves:
  - `resources/golden_rules.md`
  - `resources/human_scientific_style.md`
  - `resources/experiment_templates.md`
  - `resources/sci_q4_review_checklist.md`
- Suggestions are **never** auto-promoted. The user decides what to accept; only approved rules
  are promoted into official resources (recorded in `memory/rule_change_log.md`).

### Closing message (required)

At the end of each paper repair task, Claude Code must print a short message:

> I found N suggestions for improving the workflow/rules. Please review ./workspace/lessons/SUGGESTIONS_FOR_USER.md and tell me which ones to promote.

(Replace `N` with the actual number of suggestions captured.)

---

## Output checklist

- [ ] `./paper/` initialized; original AI draft committed (`Initial import of AI draft`) and pushed
- [ ] `workspace/diagnosis/DIAGNOSIS.md`, `PAPER_LOGIC_MAP.md`, `EXPERIMENT_GAP_REPORT.md`
- [ ] `workspace/experiments/EXPERIMENT_PLAN.md`
- [ ] `outputs/reports/PRERUN_PLAN_APPROVAL.md` (for expensive/external-data experiments; user-approved)
- [ ] `EXPERIMENT_RUN_REPORT.md` **or** `EXPERIMENT_REQUIREMENTS.md`
- [ ] `outputs/reports/RESULT_ANALYSIS.md`
- [ ] Code–Experiment–Paper Consistency Gate (Step 5):
  - [ ] `outputs/reports/RESULT_PROVENANCE_AUDIT.md`
  - [ ] `outputs/reports/EXPERIMENT_COMPLETENESS_AUDIT.md`
  - [ ] `outputs/reports/CODE_PAPER_CONSISTENCY_AUDIT.md`
  - [ ] `outputs/reports/EXPERIMENT_DESIGN_CORRECTNESS_AUDIT.md`
  - [ ] `outputs/reports/CODE_ARTIFACT_COMPLETENESS_AUDIT.md`
  - [ ] `outputs/reports/EXPERIMENT_TRUTHFULNESS_VERDICT.md` (with one verdict label)
- [ ] `outputs/reports/CLAIM_TYPE_CLASSIFICATION.md` (contribution type + per-claim types)
- [ ] manuscript `.tex` edits made **directly in `./paper/`** (experiment section + full-paper consistency + style)
- [ ] `outputs/reports/CLAIM_EVIDENCE_CHECK.md`
- [ ] `outputs/reports/EXPERIMENT_TABLE_NECESSITY_AUDIT.md`
- [ ] `outputs/reports/PUBLICATION_POLISH_CHECK.md`
- [ ] `outputs/reports/REFERENCE_VERIFICATION_REPORT.md` (verification source stated per entry)
- [ ] `outputs/reports/SCI_Q4_READINESS.md`
- [ ] `outputs/reports/PDF_LAYOUT_CHECK.md` (rendered PDF visually checked)
- [ ] `outputs/reports/FINAL_SUBMISSION_CHECKLIST.md`
- [ ] `./paper/` repaired manuscript committed (`Repair manuscript after experiment and consistency review`) and pushed
- [ ] `outputs/reports/ORIGINAL_TO_REPAIRED_CHANGELOG.md` (original initial-commit vs repaired HEAD)
- [ ] `outputs/reports/FINAL_NARRATIVE_INTEGRITY_REVIEW.md` (with one verdict label)
- [ ] `workspace/lessons/LESSONS_LEARNED.md` + appended candidate rules
- [ ] `workspace/lessons/SUGGESTIONS_FOR_USER.md` written + closing message printed
