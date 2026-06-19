---
name: ts-paper-review
description: >
  Adversarial peer-review HARDENING pass for a ts-paper draft — the thing a forward-only
  drafter/refiner can't do: argue the other side of the paper's claims. Distilled from PaperJury into a
  lean Claude-native engine: N isolated domain reviewers read the whole paper (verbatim-quote anti-skim)
  → merge/dedupe → perspective-diverse skeptics try to refute each issue → loop-until-dry → a prioritized,
  verified issue list, which is fixed through the refine stage (each fix bound to a close_criterion) and
  re-linted. Run after refine (before figure/latex), or whenever the user asks to "review / critique /
  审稿 / harden" the paper. Adapts to proposal vs data-aware mode. Stage 5 of the suite: runs by default
  (engine-agnostic — via the Workflow tool, parallel subagents, or fully in-context; identical algorithm
  and output, so it is NEVER skipped merely because a Workflow tool is absent); skip only on explicit user
  request for a quick/no-review draft. Cost-tiered (it spends extra passes), so tune how heavy it is — not
  whether it runs.
---

# ts-paper-review — adversarial peer-review (harden the draft before finalizing)

Stage 5 of the ts-paper suite — runs by default after refine, before figure.

The rest of the suite is forward-only: it drafts, then polishes. Nothing argues *against* the paper the
way a reviewer will. This stage does — a lean version of PaperJury's courtroom engine. It **runs by
default** as stage 5; skip only on explicit user request for a quick/no-review draft, recorded in
`logs/0_route.io.md`. It is cost-tiered (it costs extra passes), so tune *how heavy* it runs, not whether.

## When to use / not
- **Use** by default after `ts-paper-refine` (before `ts-paper-figure`/`ts-paper-latex`) as the
  pre-finalization hardening pass, or whenever the user says review / critique / 审稿 / 评审 / harden /
  "pick it apart".
- **Skip only on explicit user request** for a quick/no-review draft (record the opt-out in
  `logs/0_route.io.md`), or when the user just wants a single asked-for edit (that is the refine / write
  stage). This is not an official-venue rebuttal and not a from-scratch drafter.

## THE REVIEW ALGORITHM (one spec, three execution tiers)
The algorithm is **engine-independent** — it runs identically on any of the three execution tiers in
"How to run it". Describe it once; the tier changes only HOW issues are produced, never the algorithm or
the output. It implements, in order:
1. **N isolated reviewers** (default 3 full-surface lenses — Theory/Foundations, Empirical/Benchmark,
   Applied/Systems — each with the "unflinching academic gatekeeper" core + a two-pass critique). Each
   reads the WHOLE paper; **isolation** = the paper text is the only thing in its prompt (no peers, no
   prior passes). Each weakness MUST carry an **exact verbatim quote** (can't quote = didn't read =
   anti-skim) + severity + a `close_criterion`.
2. **Merge** — semantic dedupe within the pass and against everything already seen: collapse same-issue
   rows (same section anchor AND overlapping summary; when unsure, keep separate) into one whose
   `raised_by` lists every source, carrying its `evidence_quote` through unchanged; and **drop any
   candidate that lacks a usable `close_criterion` into `dropped_no_criterion`** (it is not actionable).
3. **Adversarial verify** — each new issue faces **3 perspective-diverse skeptics** (misreading /
   already-addressed / scope-or-severity); it **survives unless a MAJORITY refute it** — i.e. with 3
   angles it is **dropped on ≥2 refutes** (`refutedCount < ceil(N_angles/2)` survives). Bias to keep —
   the human gate catches residual noise. This filters plausible-but-wrong issues.
4. **loop-until-dry** — a pass counts as **dry** when it yields no NEW issues **OR** when every new
   candidate is refuted (zero survivors); any surviving issue resets the dry counter to 0. Re-run fresh
   panels until `dryStop` consecutive dry passes, capped by `maxRounds` (budget-aware).

**The issue object (identical across all tiers):** `{ severity: blocker|major|minor|nit, section,
summary, evidence_quote (EXACT verbatim — "cannot quote ⇒ do not file"), close_criterion, raised_by[] }`;
after the loop each is sorted by severity (`blocker<major<minor<nit`) and assigned a final id `I-NN`.
**Returns** `{ issues, refuted, dropped_no_criterion, rounds_run, per_round }`.

**Invariant:** the chosen execution tier changes only HOW issues are produced, never WHICH algorithm or
WHAT output. Every tier emits this exact structure and the same `logs/5_review.io.md`.

### Mode adaptation (passed as `resultsMode`)
- **proposal**: reviewers are told the result tables are intentionally blank and prose is forward-looking
  — so they do NOT file "results missing" as a flaw; they judge **method soundness/completeness, novelty/
  positioning, clarity, whether the evaluation PLAN would validate the claims, internal consistency,
  unsupported claims**.
- **data_aware**: full claims-vs-evidence scrutiny (numbers support claims, baseline fairness, ablation
  coverage, over-claiming, abstract numbers match tables).

## How to run it
1. **Assemble the paper text.** Concatenate `sections/*.tex` (+ abstract) into one readable blob (strip
   pure-LaTeX noise; keep section headings + prose + table/figure captions). This is `paperText`.
2. **Select the execution tier**, then run the algorithm on it. Look at the tools you actually have and
   use the **highest tier whose tool is available**; Tier 3 is the universal floor and always works. The
   knobs are the same algorithm params on every tier: lean default `maxRounds:2, dryStop:1, verify:true`;
   cheapest `maxRounds:1, verify:false`; thorough `maxRounds:4, dryStop:2`. `venueProfile` and
   `resultsMode` come from `template.json` (e.g. "Traitement du Signal journal — rigor, well-read, signal
   processing"; `proposal|data_aware`).

   - **Tier 1 — Workflow** (use if the `Workflow` tool is available): true parallel reviewer isolation —
     the gold reference.
     ```
     Workflow({ scriptPath: "scripts/review_panel.workflow.js", args: {
       paperText: "<assembled text>", venueProfile: "<…>", resultsMode: "<proposal|data_aware>",
       maxRounds: 2, dryStop: 1, verify: true }})
     ```
   - **Tier 2 — subagents** (use if there is NO Workflow tool but you CAN spawn subagents — the `Task`/
     `Agent` tool; **this is the normal path at "max tier", and it has the SAME quality as Tier 1**
     because each subagent is a separate context = true isolation). Per round: (a) spawn the **N reviewer
     subagents in one message** (parallel) — each prompt = the gatekeeper core + its one lens +
     `venueProfile` + the mode note + the **isolation rule** + the **inlined `paperText`** + "return your
     ISSUE_TABLE as JSON"; a fresh subagent literally cannot see peers or prior rounds. (b) **You merge**
     the tables in-context (a single reasoning op — no isolation needed) → the round's candidates. (c) For
     each candidate, spawn the **3 angle-verifier subagents in parallel** (each prompt = one angle +
     the issue fields + the inlined `paperText` + "return VERIFY JSON: {refuted, angle, reason}");
     apply the same majority-refute rule. (d) Same dry/round bookkeeping, same sort + `I-NN` ids, same
     return object.
   - **Tier 3 — in-context sequential** (universal floor; use when nothing is spawnable). You role-play
     each lens **in sequence under strict isolation discipline that simulates separate contexts**: for
     each lens, (i) re-read ONLY the paper text + that lens's mandate, **deliberately treating any issue/
     verdict from an earlier lens as NON-evidence** (no contamination); (ii) enforce the verbatim-quote
     anti-skim — every issue carries an exact `evidence_quote` copied from the paper, **no quote ⇒ not
     filed**; (iii) write that lens's full ISSUE_TABLE before starting the next. ONLY after all N lenses:
     merge/dedupe, then adversarial-verify each candidate by genuinely arguing **each of the 3 angles as
     a skeptic trying to REFUTE** (not confirm) and applying the majority rule. loop-until-dry by
     consciously restarting each round from the paper (use the running `seen` set only to suppress
     duplicates at merge). Emit the identical issue structure + `5_review.io.md`. **Honest note:** Tier
     3's simulated isolation is a real floor but not equal to Tier 1/2's separate contexts — prefer Tier
     2 whenever a subagent tool exists (it almost always does, including "max tier").
3. **Triage the returned `issues`** (you, the orchestrator) into three buckets — this is the three-way
   verdict, done in-context rather than via a heavy trial:
   - **fix now** (`blocker`/`major`/cheap `minor` with a clear `close_criterion`): hand to **ts-paper-refine**
     to edit the named section so it satisfies the `close_criterion` — a *minimal* patch, binding strictly
     to that one criterion; do not over-rewrite.
   - **author-required** (needs new data, a design decision, or a claim the author must own): list it for
     the user, do not silently edit.
   - **drop** (you judge it invalid even though it survived verify): record why.
4. **Re-gate — AFTER the fixes actually land on disk (derive "green", never forecast it).** Once every
   fix-now edit is written, re-run `../ts-paper-write/scripts/draft_lint.py <workdir>` +
   `../ts-paper-cite/scripts/citations_lint.py <workdir>` and **capture each linter's JSON (`ok`,`n`) plus
   a real wall-clock stamp (`date -u`)**. A fix must not break a shape contract, a word band, a citation,
   or **notation completeness** — `draft_lint` now flags `notation_incomplete` (a symbol added to an
   equation by a fix, like a new `\psi`, must get a notation row or be renamed to a defined symbol).
   Do not proceed on a nonzero exit. In `data_aware` mode the number-audit re-runs too. **The 'OUTPUT /
   re-gated green' block of the log may be written ONLY now** — quoting the captured JSON + timestamp as
   evidence; a re-gate whose timestamp pre-dates the edited `sections/*.tex` is invalid by construction
   (this is the lean, ledger-free analogue of PaperJury computing "closed" from applied+stamped state,
   never narrating it ahead of the work).
5. **(Optional) re-review** for a thorough pass: re-run the workflow on the edited paper until a clean
   round (the workflow's own loop already does this within a run; a fresh invocation re-reviews the
   post-fix draft). Stop when no surviving `major` remains.

## What it deliberately does NOT do (kept lean)
No durable cross-session ledger, no full trial/jury/12-juror escalation, no recall-audit, no clerk, no
docx intake, no auto-mode. Those are PaperJury's heavyweight machinery for iterating a real manuscript
over many human rounds; for a single generation run the lean panel + verify is enough. (If you ever want
the full courtroom, PaperJury itself is the tool.)

## Trace
Write `logs/5_review.io.md` (linked from `logs/index.md`). The log must **mirror real state, not forecast
it** — DECISIONS may be written as the panel returns, but OUTPUT only after step 4 (above).
- **INPUT** — paper text size, resultsMode, knobs, **and which execution tier ran** (Workflow / subagents
  / in-context).
- **DECISIONS** — the issue rows **projecting the issue object** (its `severity/section/evidence_quote/
  close_criterion`) plus the orchestrator's `id` and `verdict-bucket`: `id | severity | section |
  evidence_quote` (the EXACT verbatim quote each reviewer filed — this is the anti-skim proof; an issue
  with no quote should never have been filed) `| close_criterion | verdict-bucket` (fix-now / author-
  required / drop) `| what the fix changed`; plus a header line with `rounds_run` and `refuted` /
  `dropped_no_criterion` counts (the workflow returns all of these). Each fix-now row is closed only by
  citing the landed post-fix snippet that satisfies its `close_criterion`.
- **OUTPUT** — written ONLY after the fixes land: the **captured post-fix linter JSON** (`draft_lint`
  ok/n, `citations_lint` ok/n) **+ the `date -u` timestamp** from step 4, and any author-required items.
The DECISIONS/OUTPUT contract is identical across tiers — only the recorded tier differs.
