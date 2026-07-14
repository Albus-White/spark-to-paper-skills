# Manuscript and Artifact Boundary

The reader-facing manuscript contains scientific argument, methods, evidence, limitations, and the
reproducibility detail a reader needs to understand or repeat the work. It is not the lifecycle log.

Keep these in the artifact package or supplement manifest unless an official venue rule explicitly
requires them in the paper:

- raw SHA-256 tables and file inventories;
- lifecycle gate IDs, verdict ledgers, approvals, and release-audit output;
- internal artifact paths, cache locations, and orchestration state;
- exhaustive command transcripts, environment dumps, and failed-attempt logs;
- provenance included only to increase page count.

The paper may state software versions, repository releases, data accessions, meaningful commands, and
reproducibility procedures when they help a reader. The main model decides reader relevance and
scientific purpose. `manuscript_boundary_lint.py` catches only exact internal signatures; it does not
decide whether prose is useful or filler.

Before release, the whole-manuscript review explicitly checks that every section and appendix has a
scientific reader-facing purpose and that omitted internal details remain available in the artifact
package.
