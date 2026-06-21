# Post-repair Narrative Integrity Review

Mandatory final review (SKILL Step 15), run **after** manuscript repair, the consistency check,
the commit, and the Overleaf push. Two outputs:

- `./outputs/reports/ORIGINAL_TO_REPAIRED_CHANGELOG.md`
- `./outputs/reports/FINAL_NARRATIVE_INTEGRITY_REVIEW.md`

## Versions to compare (from git history inside `./paper/`)

- **Original** = the **initial commit** in `./paper/` (`Initial import of AI draft`):
  `git -C paper rev-list --max-parents=0 HEAD`.
- **Repaired** = the final **`HEAD`** of `./paper/`.
- Inspect the diff: `git -C paper diff <initial>..HEAD` (use `--stat` for an overview).

Base every statement on the **actual diff** and on the evidence in `workspace/experiments/` and
`outputs/reports/`. Never fabricate improvement; never hide negative findings.

## `ORIGINAL_TO_REPAIRED_CHANGELOG.md` — must answer

- What changed in the **Abstract**?
- What changed in the **Introduction**?
- What changed in the **Method**?
- What changed in the **Experiments**?
- What changed in **Tables/Figures**?
- Which claims were **strengthened**?
- Which claims were **weakened**?
- Which claims were **removed**?
- Which **placeholders or unsupported statements** were fixed?
- Which changes were caused by **real experimental evidence** (trace to logs/CSVs)?

## `FINAL_NARRATIVE_INTEGRITY_REVIEW.md` — must answer

- Is the final paper **better or worse** than the original?
- Is the **core contribution** still valid?
- Did evidence-based claim weakening **damage the central story**?
- Is the **narrative coherent** from Abstract to Conclusion?
- Are **claims, tables, figures, and discussion aligned**?
- Does the paper still have **publishable value**?
- Did the repair produce a **stronger empirical** paper, or only a **weaker but more honest** one?
- What are the **remaining narrative risks**?
- What should the **author do next**?

## Final verdict label (exactly one)

- `SIGNIFICANTLY_IMPROVED`
- `IMPROVED_BUT_WEAKER_CLAIMS`
- `HONEST_BUT_STILL_WEAK`
- `NARRATIVE_DAMAGED`
- `NOT_READY`

## Judgment rules

- Do **not** judge only by whether the proposed method wins (see `contribution_type_rules.md`).
- Judge the **whole paper**: motivation, task value, evidence, writing, coherence, publishability.
- Be honest if the experiments **weaken** the original story.
- Do **not** hide negative findings; do **not** fabricate improvement.
- If the final paper is **worse in narrative quality**, say so clearly (e.g., `NARRATIVE_DAMAGED`).
