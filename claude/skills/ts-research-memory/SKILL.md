---
name: ts-research-memory
description: Integrate an existing Paper Wiki as optional, persistent, evidence-cited research memory for repeated work in one domain. Use to assess whether a wiki is worth building, operate it through its native workflow, or create an immutable read-only snapshot for Idea discovery. Do not build a wiki by default for one paper or treat wiki gaps as verified novelty.
---

# ts-research-memory

Read `../ts-research-lifecycle/references/bounded-execution-contract.md` and
`references/paper-wiki-integration.md`.

## Decide whether memory is justified

Use a Paper Wiki when the user requests one, the same domain will support repeated future Ideas, or a
substantial maintained corpus already exists. For an ordinary one-off paper, use the fresh science
corpus directly; building a persistent wiki adds reading and synthesis cost without guaranteed value.

Paper Wiki is an external research-memory workflow. Its `raw/` sources are append-only; cited paper,
concept, and gap pages are derived views. Operate a writable wiki only through its own `paper-wiki`
Skill or documented protocol. Do not reimplement its compiler inside this suite.

## Import read-only evidence

Before Idea discovery, snapshot an existing wiki:

```bash
python scripts/snapshot_paper_wiki.py --wiki-root <wiki-root> \
  --output <research>/memory/paper-wiki-snapshot.json
```

The snapshot records marker files, content hashes, Git identity when available, page counts, and the
exact included files. It excludes raw PDFs and never copies wiki content into lifecycle state.

The main model reviews the wiki's scope, source cutoff, corpus maturity, citation quality, and known
limitations. It may retrieve candidate papers, concepts, and gaps from the frozen snapshot, but must
verify decisive claims against primary sources and run a fresh outward search.

## Boundaries

- A wiki gap is a lead, not proof of novelty.
- Embeddings, links, and clusters retrieve patterns; they do not establish transferability.
- Wiki ideation proposes candidates; `ts-idea-discovery` selects the lifecycle Idea.
- The wiki and lifecycle have separate ownership. Never write both concurrently.
- A changed snapshot after Idea selection is new evidence and cannot silently rewrite the active Idea.

