---
name: ts-paper-cite
description: >
  Stage 2 of the ts-paper suite. Build a complete, REAL refs.bib for a Traitement du Signal paper —
  using the user's provided references first and Claude's native WebSearch/WebFetch only for genuine
  gaps. Every entry must have full metadata (authors, year, venue, vol(issue):pages, DOI); never a
  title-only stub; reference count is driven by real evidence, not a quota. Use when assembling or
  fixing the bibliography of a TS paper, or whenever citations must be real and complete.
---

# ts-paper-cite — real, complete citations (no fabrication)

Citations support real claims with real evidence. **Every entry in `refs.bib` is a paper that
actually exists and that you verified.** This stage replaces the original 100+-call retrieve→triage→
slot→bind→postdraft engine (which fabricated title-only stubs to hit hardcoded quotas) with a few
Claude reasoning passes + native web search.

## Procedure — broad systematic retrieval, then triage (adopt the original engine's *coverage*, keep integrity)
A TS journal paper is expected to be **well-read**: it situates itself in a full literature, not a minimal one. Do NOT stop at "just enough" — search **broadly and systematically**, then keep only the real, well-matched papers. This is the original product's strength (systematic query planning → retrieve many → triage), minus its fabrication.

0. **Reuse the idea2story seed first (if present).** If `retrieved_papers.json` exists in the workdir (written by **ts-idea2story**, which already searched the literature), ingest it as a **verified seed**: for each paper run `scripts/doi2bib.py <doi>` to upgrade it to complete BibTeX (the DOI must resolve, or drop it — Crossref is authoritative over the seed's own metadata), and use its `abstract`+`supports_claim` to place it into `claims_map.json`. This is NOT a free pass — it removes the cold-start sweep, but you still verify each, place by abstract, and gap-fill below. Then the angles you must still search are the ones the seed does NOT cover.
1. **Plan the search angles (query packs).** From the proposal + blueprint (and what the seed already covers), enumerate the angles a thorough reviewer expects covered, and write them to **`retrieval_plan.md`**:
   - the **core task** and its canonical benchmark/problem papers;
   - **each method component / technique** the paper builds on (every named module, predictor, feature, loss);
   - **every dataset and every metric** named in the experiment design;
   - **every baseline** named;
   - the **adjacent lineages** a reviewer would expect (neighbouring tasks, the families your method departs from);
   - recent **surveys / foundational** works of the area.
2. **Retrieve broadly.** Run a WebSearch/WebFetch per angle (this is many searches, not "a handful" — breadth is the point). Collect candidate papers per angle. Prefer authoritative venues; capture the DOI/arXiv id as you go.
3. **Read each candidate's ABSTRACT to triage AND to place it.** Fetch the abstract (WebFetch the venue/arXiv/Crossref page, or read the search snippet/TLDR) and use it to decide two things at once — this replaces the original engine's `abstract → family classification → section routing`:
   - **triage**: same-task / same-technical-lineage (keep) vs cross-domain / loose-overlap (reject). Surfacing many and filtering is better than finding the minimum.
   - **placement**: which section the paper belongs in and which exact claim it supports — record this as the `section` + `claim` in `claims_map.json`. Do NOT slot a paper by its title alone; the abstract is what justifies both "is it relevant" and "where does it go".
   Log kept/rejected counts per angle in `retrieval_plan.md`.
4. **Fetch complete metadata** for every kept paper via `scripts/doi2bib.py <doi>` (deterministic, ASCII-folded, no LLM). User-provided references take priority and are preserved exactly.
5. **No real paper supports a claim → don't cite it.** Soften/rephrase or drop the claim. A real paper found by broader search is the only way to raise the count — **never** a stub, never an off-topic filler.
6. **Write `refs.bib`** (complete entries only) + `claims_map.json`, then run the linter (which now enforces a coverage floor).

## Every entry must be complete and real
- Required fields: **authors, year, venue (journal/booktitle), volume(issue), page range, and DOI** (DOI or stable URL; arXiv id ok for preprints). **Title alone is not enough.**
- Use `@article`/`@inproceedings`/`@book` with all fields populated. **A bare `@misc{key, title={...}}` stub is forbidden.** If you can only find a title, the paper is not verified — do not cite it.
- Verify existence yourself: build/verify each entry through `scripts/doi2bib.py <doi>` (which actually resolves the DOI against Crossref) or a real venue/publisher/arXiv/Crossref/DBLP page. `citations_lint.py` by default only checks **structural completeness** (the fields are present) — it cannot tell a real DOI from an invented one; DOI resolution is enforced only under the opt-in `citations_lint.py <workdir> --resolve` flag (and by `doi2bib.py`), not by the default lint. Do not trust a title that only appears in your own generated text.
- One bibkey per real paper (`firstauthorYEARkeyword`, ASCII, no leading digit); reuse it everywhere; never duplicate a paper under two keys.
- **Fast path to complete metadata:** once you have a DOI, run `scripts/doi2bib.py <doi>` to fetch a fully-populated BibTeX entry from Crossref deterministically (no hand-transcription). For an **arXiv-only preprint**, give `doi2bib.py` the arXiv id instead — it takes an arXiv path (arXiv API → `eprint`/`archivePrefix`, `journal={arXiv preprint}`) so the venue field is satisfied without a Crossref DOI.
- **Existence of arXiv-only entries:** `citations_lint.py --resolve` resolves DOIs only; it **skips** entries that have an `eprint` (arXiv) and no `doi`, treating the arXiv id as its own existence signal — so a legitimate preprint is never wrongly flagged `doi_unresolved`.

## How many — coverage target met with REAL papers (not a fabrication quota), per the TEMPLATE
Coverage is **template-driven and enforced on TWO axes** by `citations_lint.py` — a global count
**and** a per-section distribution. The global floor alone is NOT sufficient: a paper can clear 40
total cites while whole body sections carry zero and related_work overflows its band. Both axes read
`template.json`'s `citations` block:
- **Global floor** (`citations.floor`; TS `ts_iieta` = **40**, target ~40–50; `neurips` = **30**) →
  `coverage_below_floor` if under.
- **Per-section bands** (`citations.per_section_coverage`, e.g. `related_work:[20,30]`,
  `introduction:[8,12]`) → an evidence-bearing body section (introduction/related_work/method/
  experiments/analysis) with **zero** cites is a **HARD error** `section_zero_citations`; a non-empty
  section **outside its band** is a **warning** `section_coverage_out_of_band` (rebalance — move/merge
  real cites; never fabricate or delete real support). Citation-free sections in a proposal
  (abstract, conclusion, future_work) are exempt from the zero-error.

A well-read paper sits at/above the floor **and** spreads its evidence across every body section. The
**only** way to satisfy both is to *search more broadly for real papers and place each in the section
whose claim it actually supports* — never to invent, pad, or dump everything into related_work.
Stub/incomplete entries hard-fail separately, so coverage can only be cleared with real, fully-specified
papers ("search harder", never "fabricate"). The seed from ts-idea2story (step 0) counts toward this
once each entry is verified.

Per-section coverage (real papers; expand the search until each is genuinely covered):
- **related_work** — the heaviest: map the *full lineage* of every theme (typically **20–30** distinct works), so a reviewer sees you command the field.
- **introduction** — solid background + every prior-method attack cited (**8–12**).
- **method** — cite **every** technique/module/predictor/feature/loss you build on or contrast (one per real predecessor).
- **experiments** — cite **every** dataset, **every** metric, and **every** baseline named.
- abstract/conclusion — none.

To reach 40–50 honestly, widen the angle set (more sub-lineages, more surveys, the foundational works behind each component, neighbouring tasks) rather than padding with off-topic papers. If after a genuinely broad search a niche topic truly has little prior work, fewer is acceptable and honest — but for a mainstream TS topic, under 40 almost always means the search was too shallow. Do **not** bloat with off-topic papers to hit the number; an off-topic cite fails `claims_map.json`'s `weak_claim_match` anyway.

## IIETA in-text style (used by the write stage)
Numeric `[n]` via natbib: the bundled `ts_iieta.sty` sets `\setcitestyle{numbers,square,comma,sort&compress}` with `\bibliographystyle{unsrtnat}`. The write stage emits `\cite{bibkey}` (or `\cite{k1,k2,k3}` for grouped) — never hand-typed `[1]`. No citations in the abstract or in headings.

## Honesty (proposal — no real results)
Cite only to support claims about prior work / datasets / methods / metrics. **Never** cite to imply your proposed method has results it doesn't, and never hang a citation on a fabricated "outperforms by X%" sentence.

## Emit `claims_map.json` (enforced claim↔citation matching)
Alongside `refs.bib`, write **`claims_map.json`** mapping every bibkey you will cite to its justification:
```json
{ "chung2016syncnet": {"claim": "lip-sync models detect audio-video offset by contrasting windows",
                       "support_label": "same_line_support", "section": "related_work"} }
```
`support_label` ∈ `{direct_core, same_line_support, context, baseline, dataset_metric, definition}`. If the honest label for a match is `off_topic`/`adjacent`/`weak`, **do not cite** — drop or rephrase the claim. This makes the one-pass claim-matching an auditable artifact instead of a trust-me step.

## Post-draft saturation sweep (REQUIRED after write/refine — it is now gated)
Citations are inserted in the write stage, so the per-section bands above are only meaningful **after
the draft exists**. Re-running `citations_lint.py` on the drafted `sections/*.tex` is mandatory: it now
fails on any evidence-bearing section left with zero cites (`section_zero_citations`) and on any
`claims_map` `section` that disagrees with where the key is actually cited
(`claims_map_section_mismatch`). Do a **positive** pass to catch citeable sentences the draft introduced
that carry no cite — without porting the product's heavyweight ledger/cluster engine (the per-section
gate distills its essential purpose deterministically).
1. **Find under-cited sections.** Scan each finalized section; flag any *factual claim about prior work /
   datasets / baselines / metrics* with no `\cite`. (Self-method, self-results, and future-work sentences
   are non-citeable — never bolt a prior-work cite onto a results sentence.)
2. **Fill with real papers only**, via the same WebSearch + `doi2bib.py` + `claims_map.json` discipline;
   honesty-by-omission if no real paper fits. At most 3–4 new cites per rewritten paragraph; preserve
   every existing `\cite` exactly.
3. **Two cheap precision devices (Claude-native, no code):** (a) **name the nearest wrong neighbor** — for
   each citeable claim, name the single most-tempting *cross-domain* paper family and rule it out; (b)
   **reserve tier** — keep a "plausibly relevant but secondary" list and pull from it only if a section is
   genuinely thin, instead of hard-rejecting (reduces over-pruning).
4. **Re-run `citations_lint.py`** (the floor + claim-match gate already exists; no new linter needed).
5. **In `data_aware` mode**, treat results sentences as citeable **measurement** claims that should cite
   the dataset/baseline they report on, and **nudge the floor up slightly** (e.g. +4) — real data warrants
   a denser bibliography.

## Final integrity check (enforced, zero issues required)
Run `python scripts/citations_lint.py <workdir>`; it must report **zero** issues:
- every `\cite{key}` in `sections/*.tex` resolves to a `refs.bib` entry; no orphans; no dup keys;
- **no stub** entries (missing author/year/venue or DOI/URL) — a hard structural fail that blocks the old
  title-only fabrication path. NOTE: this is a textual completeness check; it cannot tell a real DOI from an
  invented one, so a well-formed but fabricated DOI passes the default lint. Existence is enforced by building
  each entry through `doi2bib.py` and, **when network is available, by the authoritative existence gate**
  `python scripts/citations_lint.py <workdir> --resolve` (opt-in; default OFF to keep offline/sandboxed runs
  deterministic), which flags `doi_unresolved` for any DOI that 404s.
- **every cited key has a `claims_map.json` entry** with a non-weak `support_label` (else `cite_without_claim_justification` / `weak_claim_match`), and its `section` field MUST match a section where the key is actually cited (else `claims_map_section_mismatch`);
- **per-section coverage**: no evidence-bearing body section with zero cites (`section_zero_citations`, hard), and every section within its `per_section_coverage` band (`section_coverage_out_of_band`, warning — rebalance, don't fabricate). The report's `cites_per_section` shows the live distribution.
Run it again after the write stage (cites are inserted there) — the per-section and section-mismatch gates can only be satisfied once the drafted `sections/*.tex` exist. Then write **`logs/2_cite.io.md`** — INPUT (claims needing support), DECISIONS (per-claim: provided vs Crossref-fetched vs dropped; the DOIs used), OUTPUT (refs.bib + claims_map.json summary).
