# Methodology Core

A concise knowledge base of authoritative scientific-writing methodology used by the
`ts-paper-experiment` skill. It distills several source families into actionable principles. It is
guidance, not a substitute for the target journal's own instructions.

---

## 1. Claude Code Skills structure

- A **skill** is a reusable task capability for Claude Code.
- The entry file is `SKILL.md` inside `.claude/skills/<skill-name>/`.
- A skill can be supported by **resources** (reference knowledge) and **scripts** (small
  deterministic helpers).
- Keep `SKILL.md` focused on *workflow*; push reference material into `resources/`.

## 2. MIT Communication Lab principles

- Every paper needs a **clear main message** — one sentence the reader should remember.
- **Organization and structure** are essential; readers follow structure, not effort.
- The **introduction** should establish: background → gap → problem → contribution.
- Write for the reader's needs, not the order in which you did the work.

## 3. Nature Masterclasses / scientific-writing principles

- A research paper needs a **clear structure and narrative arc**.
- **Title and abstract are finalized last**, after the paper logic and results are clear.
- **Results report findings; Discussion explains meaning.** Keep them separate.
- Scientific style should be **clear, precise, and cautious** — avoid hype and absolute claims.

## 4. IMRaD principle

- **Introduction** — why the problem matters and what gap exists.
- **Methods** — what was done (reproducibly).
- **Results** — what was found (observations only).
- **Discussion** — what the findings mean (interpretation, limits, implications).

## 5. EQUATOR / reporting guidelines

- Use **reporting guidelines** to improve completeness and transparency.
- Route the paper type to the relevant checklist when applicable (see
  `reporting_guideline_router.md`).
- Reporting guidelines reduce missing information and selective reporting.

## 6. PRISMA / STROBE / CONSORT high-level routing

- **Systematic review / meta-analysis → PRISMA.**
- **Observational study → STROBE.**
- **Randomized trial → CONSORT.**
- For general **ML / engineering** papers, borrow the reporting *spirit*: clearly report data,
  method, evaluation protocol, results, limitations, and reproducibility details (seeds, splits,
  hardware, hyperparameters).

## 7. ICMJE / publication ethics and AI use

- **AI tools cannot be authors.**
- **Human authors remain responsible** for accuracy, originality, attribution, and disclosure.
- **Do not fabricate** results, citations, or data.
- **AI-generated content must be reviewed by humans** and disclosed as required by the journal.

---

## Operating implications for paper repair

- **Diagnose before polishing.** Fix the research logic before the prose.
- **Evidence first, writing second.** Numbers come from runs/logs/data, never from invention.
- **Traceability is mandatory.** Each table/figure maps to a concrete artifact.
- **Cautious language by default.** Strength of wording must match strength of evidence.
- **Abstract last.** Finalize it only after results and logic are settled.
