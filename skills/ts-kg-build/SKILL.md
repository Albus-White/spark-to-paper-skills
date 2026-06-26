---
name: ts-kg-build
description: >
  Build a reusable research-PATTERN knowledge graph from a paper corpus, so ts-idea2story can
  recall prior problem→solution→story patterns. Claude does the reasoning (story-first pattern
  extraction, cluster naming + summaries); small scripts do the irreducible math (embeddings via a
  USER-SUPPLIED endpoint, clustering, graph assembly). Best-effort and honestly optional — without
  an embedding endpoint it degrades to a flat in-context "pattern shelf". Use to (re)build the KG
  for a domain, or skip it and let ts-idea2story rely on web search alone.
---

# ts-kg-build — distill a corpus into a research-pattern KG

The product mined a corpus into a graph of **research patterns** (clusters of papers reframed as a
reusable *problem → solution → story*) that recall then surfaces for a new idea. Distilled: **Claude
is the extractor and the cluster namer/summarizer; four small scripts do only the irreducible math.**
A built KG matches the product's `kg_ts/` schema, so `ts-idea2story` reads it unchanged.

> **Honesty (the user accepted this):** a *full, quality* KG needs embeddings + a crawled corpus +
> (for review-weighted edges) a reviews corpus. It is **not guaranteed great**. Build the
> extraction + lite shelf unconditionally; the embedded/clustered path activates only when a
> `TS_EMBED_*` endpoint is configured. TS already ships a built KG (`kg_ts/`) — reuse it; this skill
> is for a NEW domain/corpus.

## Inputs
- `corpus.jsonl` — one paper per line: `{paper_id, title, abstract, venue, year, doi, url, pages?,
  num_references?, keywords?, authors?, reviews?/review_score?}`.
- a `domain` label (e.g. `ts`, `cv`, `nlp`).
- optional embedding config (only for the clustered path): `TS_EMBED_MODEL / TS_EMBED_API_KEY /
  TS_EMBED_BASE_URL` (OpenAI-compatible `/embeddings`; same pattern as the figure/image config).

## Procedure

### 1. Per-paper pattern extraction (Claude — the core IP; story-FIRST)
For each paper, read the title+abstract (+reviews if present) and write the reusable pattern. Append
these fields to each record in `papers.jsonl`:
- **`base_problem`** — the underlying problem class (not this paper's specific instance).
- **`solution_pattern`** — the transferable mechanism/idea (not the implementation details).
- **`story`** — *the most important field*: the narrative reframe — *"this work reframes X from Y
  to Z"* — the angle that makes the contribution compelling. **Anti-summary rule: do NOT summarize
  the abstract; reframe it into a reusable story.** A summary ("this paper proposes a CNN for …") is
  a failure; a story ("recasts dense prediction as a retrieval problem so labels become free") is the goal.
- **`application`** — where the pattern pays off.
- **`idea`** — a one-line transferable research idea seed.
- **`domain`**, **`sub_domains`** (free-text list).
Each field self-QC: reject `<100`-char filler or generic phrasing; **never fabricate** content not
supported by the abstract.

### 2. Embed + cluster (scripts — irreducible)
Build the text to embed from the **story-first** fields (story + base_problem + solution_pattern),
NOT the raw abstract — clustering on the reframe is what groups *transferable angles*:
```
# write items.jsonl: {"id": paper_id, "text": "<story> <base_problem> <solution_pattern>"}
python3 scripts/embed.py --in items.jsonl --out kg/pattern        # needs TS_EMBED_* ; else SKIP -> lite shelf (step 4b)
python3 scripts/cluster.py --emb kg/pattern_emb.npy --meta kg/pattern_meta.jsonl --out kg/clusters.json
```
`cluster.py` returns members, per-member membership (cosine to centroid), coherence, and exemplars.

### 3. Cluster naming + enhancement (Claude)
For each cluster, read its **exemplars** (the highest-membership papers' story fields) and write
`cluster_meta.json` = `{cluster_id: {name, summary, llm_enhanced_summary, tier}}`:
- **`name`** — a distinctive **3–6 word research-STORY angle** (e.g. "labels-for-free via retrieval").
  **BANNED generic words in the name:** method, framework, model, approach, network, system, technique,
  learning, based, novel, general. Name the *angle*, not the architecture.
- **`summary`** — one inductive sentence capturing what the cluster's papers share.
- **`llm_enhanced_summary`** — a richer one-sentence-per-facet distillation (problem / solution / when-it-wins).
- **`tier`** — A/B/C by **size AND coherence** (a big but incoherent cluster is NOT tier A; respect
  `cluster.py`'s `coherence`).

### 4a. Assemble + validate (scripts)
```
python3 scripts/kg_build.py --papers papers.jsonl --clusters kg/clusters.json \
        --cluster-meta cluster_meta.json --domain <domain> --out kg/
python3 scripts/kg_lint.py kg/                                   # must be ok:true
```
Produces `kg/nodes_{paper,idea,pattern,domain}.json`, `kg/edges.json`,
`kg/knowledge_graph_stats.json` — the schema `ts-idea2story` recalls over. Copy the
`kg/pattern_emb.npy/_meta.jsonl/_manifest.json` into `kg/` too (recall uses them for the semantic
fine-rank; the manifest's model id stops recall from mixing embedding spaces).

### 4b. Lite fallback (no embedding endpoint)
If `embed.py` reports "not configured", skip clustering: write the per-paper patterns to
`kg/patterns_shelf.jsonl` and let `ts-idea2story` recall by **reading the shelf in context** (works
for small corpora like the 79-paper TS set). Label the KG `lite — recall by reading`. No fabrication
of clusters/edges you didn't compute.

## Edges (built deterministically by kg_build.py — do not hand-author)
`uses_pattern(paper→pattern, quality)`, `in_domain(paper→domain)`, `belongs_to(pattern→domain)`,
`works_well_in(pattern→domain, effectiveness = avg pattern quality − domain baseline, confidence)`.
`quality` comes from the raw `review_score` field (expected pre-normalized to ~0-1) when present, else a neutral 0.7 default.

## Integrity
- **Never fabricate** an abstract, a review score, or a pattern not grounded in the paper text.
- The **citation pool** a downstream story may cite = the **exemplar papers** of the patterns it
  used — not "all papers seen".

## Trace
Write `logs/kg_build.io.md` — INPUT (corpus size, domain, embeddings on/off), DECISIONS (extraction
self-QC rejects; cluster names + tiers + why), OUTPUT (counts from `knowledge_graph_stats.json`,
kg_lint result, lite-vs-full).
