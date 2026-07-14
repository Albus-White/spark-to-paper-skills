# spark-to-paper-skills

Fourteen composable research skills for Codex and Claude Code. The v5 architecture manages one
evidence-bound lifecycle from a literal research seed through field and venue calibration, Idea
selection, optional governed execution, manuscript construction, source-of-truth figures, actual-PDF
review, and release audit.

The suite does not promise that every Idea is novel, every hypothesis is supported, or every figure
is vectorizable. It preserves negative results, uncertainty, original evidence, and exact structures
instead of optimizing for a positive-looking paper.

## What v5 changes

- **One lifecycle and one active Idea.** A raw seed or supplied proposal becomes an evidence-grounded
  candidate set, one selection judgment, and one versioned active Idea. There is no parallel `story`
  truth or automatic novelty score.
- **Two calibrations.** A science profile reads current primary papers from leading field venues to
  learn closest work, evidence conventions, benchmarks, and writing practice. A separate frozen
  target-venue corpus measures comparable accepted papers.
- **Observed envelope, not quotas.** Venue PDFs provide distributions for pages, citations, figures,
  tables, evaluation count/kinds, evidence dimensions, and difficulty. The main model selects and
  explains publication targets; official/user constraints remain hard. There is no global citation
  floor or arithmetic-mean artifact quota.
- **Domain-neutral research programs.** Claims bind to experiments, simulations, observations,
  qualitative studies, proofs, benchmarks, or artifact evaluations. A measured dominant-cost probe
  and user resource envelope bound empirical work.
- **Governed code and iteration.** Repositories, licenses, commits, patch policy, environments, runs,
  test access, failures, and branches are recorded. Applicable benchmarks are reproduced. Negative
  hypotheses remain valid evidence; unchanged failures do not loop.
- **Source-of-truth figures.** Measured evidence is deterministic/original; observations remain
  original; exact structures use domain-native tools; only explanatory synthesis executes the real
  external PaperBanana Retriever→Planner→Stylist→Visualizer→Critic workflow. DrawAI is a conditional
  raster-to-editable tail after scientific approval.
- **Reader-facing manuscript boundary.** Internal hashes, gate ledgers, command transcripts, and audit
  inventories stay in the artifact package. They cannot be used as appendix or page filler.
- **Holistic semantic review.** The model checks logic, contradictions, method-result alignment,
  source support, terminology/notation drift, redundancy, filler, alternatives, limitations, and
  negative results. After compilation it opens the actual PDF and binds a final Publication Judgment.

See [the v5 architecture](docs/research-closed-loop-architecture.md).

## Skills

| Skill | Role |
|---|---|
| `ts-paper` | End-to-end orchestrator |
| `ts-research-lifecycle` | Single state, provenance, gates, invalidation, and release core |
| `ts-idea-discovery` | Evidence-grounded candidate generation and one Idea selection |
| `ts-research-memory` | Optional immutable Paper Wiki snapshot for repeated domain work |
| `ts-paper-cite` | Science, venue, benchmark, and manuscript source grounding |
| `ts-paper-plan` | Domain-appropriate blueprint from the frozen publication contract |
| `ts-paper-experiment` | Governed code/data acquisition, verification, bounded execution, and Idea iteration |
| `ts-paper-data` | Canonical facts, tables, plots, and manuscript value bindings |
| `ts-paper-write` | One coherent evidence-calibrated LaTeX draft |
| `ts-paper-refine` | Holistic refinement and focused review closure |
| `ts-paper-review` | Scientific, logical, consistency, redundancy, and final-PDF review |
| `ts-paper-figure` | Four source-of-truth figure routes and real PaperBanana execution |
| `ts-figure-optimize` | Optional DrawAI raster-to-editable reconstruction |
| `ts-paper-latex` | Deterministic venue-template assembly and compilation |

## Lifecycle

```text
user policy + literal seed + resource envelope
        |
        +--> science profile: current primary field literature
        +--> venue profile: frozen comparable accepted-paper PDFs
        +--> optional Paper Wiki snapshot + fresh delta search
        |
Idea candidates --> selection judgment --> one active Idea
        |
claims + benchmark decision + feasibility probe
        |
frozen claim-linked research program
        |
proposal -------------------------------+
empirical --> code/env locks --> baseline/review/tests
          --> pilot --> bounded confirmation --> diagnosis
          --> Idea decision --> claim/fact reconciliation
                                             |
observed publication envelope --> model-selected contract
        |
citations --> blueprint --> data bindings --> write --> refine --> review
        |
source-of-truth figures --> LaTeX --> actual-PDF judgment --> release audit
```

Scientific or semantic changes return to the lifecycle and invalidate dependents. Editorial changes
do not erase compatible empirical evidence.

## Figure routes

```text
measured_evidence      -> deterministic/domain plot or original evidence + fact IDs
original_observation   -> registered original artifact + faithful processing
exact_structure        -> TikZ/Graphviz/CAD/GIS/chemistry/domain-native renderer
explanatory_synthesis  -> external PaperBanana five-stage execution
                          -> approved raster
                          -> DrawAI only when preflight succeeds and no born-vector source exists
```

PaperBanana is an external runtime dependency for explanatory synthesis and must be a pinned checkout.
Its repository contains Apache-2.0 source licensing and a README notice about workflow patents and
third-party commercial use; review `ts-paper-figure/references/PAPERBANANA_NOTICE.md` before use.

## Distributions

The project keeps quality-equivalent host distributions in one repository:

```text
codex/.codex-plugin/plugin.json
codex/skills/ts-*/

claude/.claude-plugin/plugin.json
claude/skills/ts-*/
```

Shared Skill instructions, scripts, references, schemas, examples, and tests are mirrored. Codex-only
`agents/openai.yaml` metadata remains under `codex/`.

## Install

### Codex standalone skills

```bash
for skill in codex/skills/ts-*; do
  rsync -a --delete "$skill/" "${CODEX_HOME:-$HOME/.codex}/skills/$(basename "$skill")/"
done
```

Remove retired skill directories such as `ts-idea2story` and `ts-kg-build` when upgrading from v4,
then open a new Codex session.

### Claude Code plugin

```bash
claude --plugin-dir ./claude
```

Standalone Claude skills can be mirrored to `$HOME/.claude/skills/` in the same way.

## Runtime requirements

- Python 3.10+ and the system tools used by selected stages (`git`, LaTeX, `pdfinfo`, `pdftotext`,
  renderers, and domain tools as applicable).
- Official/user-provided venue template assets for a real submission.
- Network access for fresh literature and metadata retrieval.
- A pinned PaperBanana checkout and its configured model providers only when explanatory-synthesis
  figures are planned.
- DrawAI perception/runtime dependencies only when raster reconstruction is required and preflight
  succeeds.
- Local or SSH-accessible research compute for empirical runs. Credentials remain in environment,
  SSH agent, or external secret storage and are never copied into lifecycle state.

## Invoke

```text
Use $ts-paper on this research seed and target venue.
Use $ts-paper-experiment to execute the frozen research program.
Use $ts-paper-review to review this complete manuscript against its evidence.
```

## Verification

```bash
python3 tests/run_skill_tests.py $(find codex/skills -path '*/tests/test_*.py' -o -path '*/scripts/tests/test_*.py' | sort)
python3 -m unittest discover -s codex/skills/ts-research-lifecycle/tests -p 'test_*.py'
python3 tests/check_platform_parity.py
python3 tests/check_release_hygiene.py
python3 tests/check_bounded_execution.py
```

Exact checks prove only what they can observe: artifact identity, lineage, limits, values, citation
wiring, image bindings, and compilation. Model judgments remain responsible for scientific and
semantic correctness.
