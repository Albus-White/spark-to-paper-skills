# Reproducible Artifact Packaging

Promoted from candidate **CAND-010**. Used inside the Code–Experiment–Paper Consistency Gate
(SKILL Step 5, `CODE_ARTIFACT_COMPLETENESS_AUDIT.md`).

Purpose: the experiment code should be preserved and organized well enough that the reported
results can be reproduced. Scratch scripts scattered across a machine are a reproducibility risk.

## Target layout (suggested, relative paths)

```
input/code/                # or the project's code location
  README.md                # how to set up and run (commands documented)
  requirements.txt|env.yml  # pinned dependencies
  configs/                  # experiment configs (one per reported setting)
  data/ or data_prep/       # preprocessing / dataset preparation code
  features/                 # feature extraction code
  models/                   # model definitions
  baselines/                # baseline definitions
  train.py / train script   # training entry point
  eval.py  / eval script    # evaluation entry point
  make_tables.py / figs     # table/figure generation from raw logs
```

## Completeness checklist (for `CODE_ARTIFACT_COMPLETENESS_AUDIT.md`)

- [ ] preprocessing code present
- [ ] feature extraction code present
- [ ] model definitions present
- [ ] baseline definitions present
- [ ] training script present
- [ ] evaluation script present
- [ ] table/figure generation script present
- [ ] config files **or** documented commands present
- [ ] seeds and data splits documented
- [ ] a README that maps "to reproduce Table/Figure X, run Y"

If code only exists as **scratch scripts**, or any of the above is missing, report a
**reproducibility risk** and list exactly what is missing and what would be needed.

## Notes

- This describes how to **assess and document** packaging for the current paper project. Do **not**
  copy the project's code, data, logs, or large artifacts into the AutoPaperFactory template repo,
  and never place code/logs in `./paper/` (manuscript files only).
