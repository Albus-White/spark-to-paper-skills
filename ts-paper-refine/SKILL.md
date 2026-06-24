---
name: ts-paper-refine
description: >
  Stage 4 of the ts-paper suite. One holistic pass that right-sizes each drafted section toward
  Traitement du Signal JOURNAL length (not conference page-compression), enforces cross-section
  coherence and terminology consistency, removes redundancy, and preserves all citations, equations,
  and markers. Use to polish/tighten a TS paper draft before the review stage. Do NOT over-compress.
---

# ts-paper-refine — right-size & polish (one pass)

Do this as **one reasoning pass over the whole draft** (you see every section at once, so coherence
and de-duplication are free). The original's purpose was *conference page-compression* — that is
**wrong for a journal**. Traitement du Signal papers are substantial (≈8–14 two-column pages);
**right-size, do not aggressively cut.**

## What to enforce
- **Length toward the template's targets** — the table below is the **`ts_iieta` default**; for another
  template, right-size to **its** `template.json` `sections[].words` (e.g. NeurIPS bands differ). The
  spec is authoritative (`draft_lint` reads bands from `template.json`). Expand thin sections, trim only
  genuine bloat — never compress below the floor:
  | section (ts_iieta) | final words |
  |---|---|
  | method | 2000–3000 |
  | experiments | 1000–1500 |
  | introduction | 800–1200 |
  | related_work | 800–1200 (3 themes) |
  | analysis | 900–1400 |
  | conclusion | 200–280 (1 paragraph) |
  | abstract | 150–220 (1 paragraph) |

  These bands target a substantial **~10–12 page** two-column TS article. **Expand by adding real
  substance** (more method detail/derivation, more components, deeper analysis, more ablation discussion,
  fuller related-work lineage) — never by padding, restating, or filler sentences.
- **Coherence**: the same method/component/dataset/baseline names everywhere (use the blueprint `terminology`); no contradictions between sections; intro/abstract accurately summarize what Method/Experiments actually say.
- **No redundancy**: each mechanism explained once (Method), not re-derived in Analysis; remove repeated motivation across intro/related/method.
- **Preserve exactly**: every `\cite{}`, every equation, every `\ref{}`, every table/figure label and the `--` result placeholders. Refinement changes prose, never citations/structure/math semantics.
- **Honesty intact**: still zero fabricated numbers in any sentence; results stay forward-looking; tables stay blank.
- **TS tone**: no bold in body, hedged conclusion language, no hype, no filler phrases.

## De-AI pass (this is AI-written prose — scrub the tells)
Every section was drafted by an LLM, so it is prone to AI tells. Read each section and **rewrite where
it improves** (don't churn natural sentences). Scan for and replace:
- **Prose flow (the #1 fix).** Turn any bare-comma *comma soup* into connected prose: punctuate an
  appositive/enumeration with a **colon or em-dash**, not a bare comma — "a pipeline: retrieval, planning"
  or "a pipeline — retrieval, planning — in which …", NOT "a pipeline, retrieval, planning, … in which …"
  (that comma soup is what reads as fragmented "碎句子"). A legitimate appositive em-dash is GOOD and
  encouraged; only remove em-dash *abuse* (dramatic-pause dashes). Vary sentence length; each paragraph
  must read as a flowing whole, not a clause list. Avoid the recipe rhythm of "X does A [cite], Y does B
  [cite]" in related work — synthesize across papers.
- **Tell words/phrases:** leverage, delve, utilize, showcase, underscore, intricate, pivotal, seamless,
  holistic, nuanced, realm, tapestry, testament, "it is worth noting", "plays a crucial role", "in order
  to" (→ "to"), rule-of-three triplets, connective *stacks* (firstly/moreover/furthermore — a single
  appropriate transition is fine), empty "-ing" wind-ups, vague attribution ("studies show"),
  "not only … but also" overuse.
- **Translationese** (these drafts trend that way): stacked attributive chains ("the … of the … of the
  …"), gratuitous passive voice, hollow rhetoric (paradigm shift, disruptive, profound, in essence).
Prefer plain, precise words; keep `\cite`/`\ref`/math intact; add no new emphasis.
`draft_lint` **code-enforces** (hard-fails, `ai_tell`) ONLY the CONTEXT-FREE canned phrases — tapestry,
testament, "plays a crucial role", "it is worth noting", "delve into", "realm of", "paradigm shift",
"navigating the landscape", "ever-evolving", … plus `in order to` — those MUST be gone. The
CONTEXT-DEPENDENT cohesion tells — **em-dashes, sentence-initial `firstly/moreover/furthermore/additionally,`,
`not only … but also`, rule-of-three triplets, `leverage`/`utilize`** — are deliberately NOT gated (a regex
would kill the good appositive em-dash along with the abuse — precisely what produced the comma soup): you
remove the *abuse* by judgment while keeping legitimate uses. (Source: PaperJury writing-toolkit `de-ai`.)

## Logic self-check (after each edit, narrow self-gate — not a reviewer)
After you change a passage, re-read ONLY that passage for a **show-stopper introduced by the edit**: a
logic contradiction, an undeclared terminology switch (a term silently renamed), or severe Chinglish.
Fix it; do not raise style nits here (the de-AI pass owns those). This is the in-pass honesty check;
the adversarial peer-review (**ts-paper-review**, stage 5, runs by default) is the heavier, separate
hardening loop that runs after this stage and routes its fix-now issues back here in **Review-fix mode**.

## DATA-AWARE branch (only when `template.results_mode == "data_aware"`)
When the paper reports **real results** (data-aware — see **ts-paper-data**), the "remove unbacked
numbers" instinct **inverts** for numbers that trace to `results.facts.json`:
- **Do NOT** convert real numbers to forward-looking language; **do NOT** remove real numbers from running
  text; **do NOT** flag real (traceable) numbers as hallucinations.
- **Verify cross-section number consistency** — the same metric formatted identically everywhere; the
  abstract/conclusion headline numbers equal the filled result-table values.
- **Preserve the filled result tables and the evidence sentences**; preserve ablation deltas; enforce
  definitive **past tense**; apply the **TBD silence rule** (no claim about a `"TBD"` metric).
- Keep every number consistent with `results.facts.json` (the number-audit re-runs after refine).
Everything else (length right-sizing, coherence, de-duplication, tone) is as in proposal mode.

## Match the template's venue type
If the active template is a **journal** (e.g. `ts_iieta`), strip any leaked conference framing ("to fit
the page limit / 8-page / camera-ready") and don't over-compress — journals are substantial. If the
template is a **conference** style (e.g. `neurips`), respect its tighter conventions instead. Let the
template's word bands — not a fixed venue habit — decide length.

## After refining (enforced)
Re-run `python ../ts-paper-write/scripts/draft_lint.py <workdir>` — it now **fails the build** on any section outside its `template.json` word band and on any broken shape contract, so "right-sized" is verified in code, not by eye. Drive every `word_band` violation to zero by **expanding thin sections with real substance** (more method detail, more discussion, a deeper failure analysis) — never by padding. Then re-run `python ../ts-paper-cite/scripts/citations_lint.py <workdir>` to confirm citations survived. Re-run both until they exit 0 (`ok:true`); **do not hand off on a nonzero exit.** Then run **`python ../ts-paper-write/scripts/reflow_tex.py <workdir>`** so every `sections/*.tex` is one logical line per paragraph (your de-AI rewrites may have re-wrapped them; idempotent, PDF-neutral). Then write **`logs/4_refine.io.md`** (INPUT: pre-refine word counts; DECISIONS: per-section deltas + what was added/cut; OUTPUT: post-refine counts, all in band). Hand off to **ts-paper-review** (stage 5, the default next stage): it returns a triaged issue list, and for each fix-now issue the orchestrator re-invokes THIS skill in **Review-fix mode** (below). Only after review is dry/closed does the chain proceed to **ts-paper-figure** then **ts-paper-latex**. If the user explicitly opted out of review, hand directly to **ts-paper-figure**.

## Review-fix mode (ONLY when invoked with a single review issue — NOT a full pass)
This mode is triggered **only** when the orchestrator hands you one `ts-paper-review` issue
`{section, severity, evidence_quote, close_criterion}` to close. It is a separate entry path: do **not**
run it on a normal stage-4 invocation, and do **not** run the holistic right-size / de-AI pass here. The
default full-pass behavior above is unchanged.
- Make the **minimal** edit to the **named section only** that makes that one `close_criterion` true. Bind
  strictly to that criterion; do not touch other sections and do not over-rewrite.
- **Preserve exactly**: every `\cite{}`, equation, `\ref{}`, table/figure label, the `--` placeholders,
  and the section's `template.json` word band (stay in band — no compression below the floor).
- **If the fix touches an equation, it must keep notation complete:** any symbol the edit introduces into
  an equation has to be added to the notation table (or the fix renamed to an already-defined symbol) **in
  the same edit** — `draft_lint` now hard-fails `notation_incomplete` (this is exactly the path that let a
  stray `\psi` into the central equation), so an unmatched new symbol will block the re-gate below.
- Re-run `python ../ts-paper-write/scripts/draft_lint.py <workdir>` AND
  `python ../ts-paper-cite/scripts/citations_lint.py <workdir>` until both exit 0 (`ok:true`) to confirm
  nothing broke (including `notation_incomplete`); do not return a fix on a nonzero exit.
- Append the fix (issue id, section, what changed, close_criterion met) to **`logs/5_review.io.md`**
  (the review log — **not** `4_refine.io.md`).
- Return control to the orchestrator for the next issue, or to advance to figure once review is dry.
