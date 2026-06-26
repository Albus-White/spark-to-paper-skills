---
name: ts-idea2story
description: >
  Turn a raw research idea into a compelling, well-grounded research STORY (an 8-field structured
  proposal) ready to feed the ts-paper pipeline. Claude does almost everything natively — idea
  packaging, recall reasoning over a knowledge graph, agentic external literature search
  (WebSearch/WebFetch), story generation, and a critique→refine→fusion loop; tiny scripts do only
  embeddings/recall math and the schema gate. Emits story.json + story_proposal.md +
  retrieved_papers.json (a citation seed the cite stage reuses, so paper-writing searches less).
  Use when the user has an idea (not yet a full proposal) and wants a paper-ready story.
---

# ts-idea2story — idea → grounded research story (the upstream of ts-paper)

Distilled from the product's idea→story link. **The idea is the PROTAGONIST; a recalled/searched
pattern is the TOOL it wields.** Claude is the packager, the recaller, the searcher, the storyteller,
and the critic — all in one context (so coherence and anti-stacking come for free). Two scripts are
irreducible: `kg_recall.py` (vector/graph retrieval) and `story_lint.py` (the gate); embeddings
(optional) reuse `../ts-kg-build/scripts/embed.py`'s `TS_EMBED_*` config.

## Inputs / Outputs
**In:** a raw idea (text); optional `kg/` dir (from `ts-kg-build`, or the bundled `kg_ts`); optional
`TS_EMBED_*` endpoint; a `retrieval_focus` dial in {trust_kg, balanced, go_search_web}.
**Out (in the workdir):**
- `story.json` — the 8 fields: `title, abstract, problem_framing, gap_pattern, solution,
  method_skeleton, innovation_claims[], experiments_plan`.
- `story_proposal.md` — the Markdown projection of the 8 fields (this is what `ts-paper-plan` reads —
  a story IS a structured proposal; **story2paper == proposal2paper**).
- `retrieved_papers.json` — the real papers found, the **citation seed** for `ts-paper-cite` (§ Reuse).
- `logs/*.io.md`, optional `novelty_report.json`.

## Procedure

### 1. Package the idea (Claude)
Write `idea_brief.json`: `motivation, problem, assumptions_explicit[], assumptions_inferred[],
constraints, retrieval_query`. **Faithfulness guard:** keep assumptions you *inferred* separate from
what the user *stated* — never fabricate user intent. The `retrieval_query` is an English,
search-friendly reformulation. Never raise on a thin idea; normalize and proceed.

### 2. Recall candidate patterns (script + Claude)
If a `kg/` exists: `python3 scripts/kg_recall.py --idea "<retrieval_query>" --kg <kg_dir> --out recall.json --topk 8`.
It returns Top-K candidate patterns (semantic+graph if embeddings configured, else **lexical-only,
labeled** — treat lexical hits as weaker). **Then YOU reason over them comparatively in one pass**,
scoring each on three independent axes (no per-pattern round-trips needed):
- **stability** — reliable skeleton, well-trodden;  **novelty** — differentiating, rare;
- **domain_distance** — how far the pattern's home domain is from the idea (sorted ASCENDING; a
  near-domain pattern transfers more safely, a far one is a riskier "storyteller" move).
Size ≠ stability (a big cluster can be incoherent — check the pattern's coherence). If no KG: skip to
search (or, with neither, generate the story from the idea alone — weakest, allowed).

### 3. Agentic external search (Claude WebSearch/WebFetch) — also seeds citations
Plan **intent-tagged query packs** (with forced minimums) and run them via native search:
`core_method`, `task_setting`, **`contrast`** (what you depart from — don't skip this), `evaluation`
(datasets/metrics/baselines). **Force-keep the literal user idea as one query.** For each kept paper,
read the abstract and extract a story-first pattern (as in ts-kg-build). **Record every real paper
into `retrieved_papers.json`** (schema in § Reuse) — this is the citation seed. Never fabricate a
paper or an abstract.

### 4. Select the seed pattern (Claude)
Pick the pattern that best fits the idea as a *stable skeleton* (prefer a near-domain, coherent KG
pattern for the first draft); hold novelty/far-domain patterns in reserve for the refine loop.

### 5. Generate the Story (Claude — the craft)
Idea = protagonist, pattern = tool. Produce the 8 fields. The non-negotiable craft:
- **Reframe, don't combine.** The `gap_pattern`/`solution` must say *"reframe X from Y to Z"* —
  recast the problem, don't staple two methods together. **Banned verbs:** combine, integrate, merge,
  stack, plug in. **Required verbs:** reframe, recast, transform, unify, exploit. Include a one-line
  rationale `why_not_straightforward_combination` inside `solution`.
- **Title:** names the *idea/insight*, not the architecture. Good: "Labels for free: dense prediction
  as retrieval". Bad: "A CNN-Transformer framework for X".
- **solution vs method_skeleton split:** `solution` is the narrative (what changes and why it works);
  `method_skeleton` is the concrete step list (≥ a few real steps). Keep them distinct.
- **Honesty:** `experiments_plan` and `innovation_claims` are forward-looking ("we evaluate… we
  expect…") — **no fabricated numbers / "beats SOTA by X%".**

### 6. Critique → refine → fuse loop (Claude, in-context; bounded ≤3 rounds)
- **Critic (blind, comparative):** judge the story against 1–2 exemplar stories with titles/authors
  STRIPPED (so prestige can't anchor you); prefer comparative better/worse over absolute scores;
  **anti-length bias** (longer ≠ better); **tie on thin evidence**. Diagnose the single WEAKEST of:
  faithfulness-to-idea, novelty, narrative organic-ness.
- **Defect → axis routing:** novelty weak → pull a *novel/rare* reserved pattern; stability/soundness
  weak → pull a *robust near-domain* pattern; storytelling flat → pull a *far domain_distance* pattern.
- **Fuse conceptually (not A+B):** weave the new pattern into the story so the two **co-evolve**
  (restructure the framing), then run a **StoryReflector** organic-ness check — reject a story that
  reads as two bolted-on ideas; do not let it self-approve over a stacking warning.
- **Calibrated pass bar (accept condition):** accept only when the story is judged better-or-equal
  to **≥2 of the N exemplar anchors on ≥2 of the 3 axes** (faithfulness, novelty, narrative). If <2
  anchors are available, fall back to a fixed bar — **each axis judged at least good (≥7/10
  equivalent)**. (Claude-native analog of the source's two-of-three-q75 + pass-score-7.0 gate.)
- **Loop control:** keep the **global best**, not the last (rollback if a round regresses); don't
  retry a pattern that already failed the same axis; stop early when the pass bar is met. **Cap at 3
  refine rounds**; if the bar is still unmet after 3 rounds, ship the **global best** and record the
  unmet axis in the log.

### 7. Novelty / anti-collision check (script when an embedding endpoint is configured)
When `TS_EMBED_*` is configured, run `python3 scripts/novelty_check.py <workdir>`: it embeds the story
text (reusing the `embed_one()` pattern), cosine-compares it against an available reference set (the
`retrieved_papers.json` abstracts embedded on the fly, else the pattern index `kg/pattern_emb.npy`),
and writes `novelty_report.json` `{max_similarity, risk_level, threshold_high, threshold_medium,
top_similar, verdict, basis}`. Act on the bands: **≥0.88 high → pivot** to a more differentiating
reserved pattern and re-tell; **≥0.82 medium → warn**; **cap pivots at 2**.
**Graceful degrade:** with no embedding endpoint the script exits 0 with a "lexical/judgement only —
**not a semantic guarantee**" note; in that case do the lexical/judgement check against the recalled
exemplars + `retrieved_papers.json` yourself. Either way `novelty_report.json` must exist (top similar
works + verdict + basis) so the check is never silently skipped.

### 8. Emit + gate
Write `story.json`, render `story_proposal.md` (the 8 fields as a proposal: Problem / Gap / Proposed
method / Evaluation plan / Contributions), and finalize `retrieved_papers.json`. Then:
`python3 scripts/story_lint.py <workdir>` — must be **ok:true** (8 fields non-empty, no schema-echo
noise, method_skeleton concrete, no fabricated numbers). **Soft requirement:** confirm
`novelty_report.json` exists (from step 7, semantic or degraded) so the novelty check was not silently
skipped. Hand `story_proposal.md` to **ts-paper-plan**.

## Reuse — `retrieved_papers.json` (cuts the cite stage's search)
Write the real papers found in steps 2–3 here; `ts-paper-cite` ingests it as a verified seed.
```json
{"source":"ts-idea2story", "papers":[
  {"paper_id":"openalex:W..","title":"..","authors":[".."],"year":2024,"venue":"..",
   "volume":"","issue":"","pages":"","doi":"10..","url":"https://..","abstract":"(real)",
   "abstract_source":"openalex|arxiv|openreview|missing",
   "relevance":"core|context|baseline|dataset_metric|contrast",
   "supports_claim":"the exact story claim this paper backs"}]}
```
Rules: **dedup** by paper_id / normalized title; on merge **keep the longest non-empty abstract/title**;
**never fabricate** an abstract (`abstract_source:"missing"`); pool = the exemplar/agentic papers the
story was derived from + the novelty candidates. The cite stage still verifies each via `doi2bib`,
places it by abstract, gap-fills missing angles, and enforces its coverage floor — the seed just
removes the cold-start sweep.

## Integrity & trace
This is a proposal — no real results anywhere. Keep explicit-vs-inferred assumptions honest. Write
`logs/idea2story.io.md` — INPUT (idea, retrieval_focus, kg on/off, embeddings on/off), DECISIONS
(packaged brief, recalled patterns + 3-axis scores, search packs + kept/rejected, seed pattern, each
critique round: weakest axis → pattern pulled → fuse result, novelty verdict), OUTPUT (story.json
summary, story_lint result, retrieved_papers count).
