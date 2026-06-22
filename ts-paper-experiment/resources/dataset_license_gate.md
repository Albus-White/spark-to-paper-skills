# Dataset / License / Terms Gate

Mandatory gate inside SKILL Step 3, **before downloading or using any external dataset**. Purpose:
respect dataset licenses/terms, avoid surprise disk/runtime costs, and keep the user in control.

## Report before downloading/using a dataset

For each external dataset, report:

- **Dataset name**
- **Source URL**
- **Expected download size**
- **License / terms-of-use status** (name the license; note any redistribution/commercial limits)
- **Whether user confirmation is required** (yes/no, and why)
- **Disk requirement** (download + extracted)
- **Estimated runtime** (to download and to run the experiment that needs it)
- **Whether the dataset is needed for essential claims** (essential vs nice-to-have)

## Stop-and-ask rule

- **If the license / terms of use is unclear, stop and ask the user** before downloading or using
  the dataset.
- Also stop and ask if the download is large, the disk/runtime cost is high, or the dataset is not
  needed for an essential claim.
- Never bypass paywalls, login walls, or redistribution restrictions.

## Report format (include in the experiment run report)

```
## Dataset gate: <name>
- Source URL: ...
- Download size / disk: ... / ...
- License / ToU: <license> (status: clear / unclear)
- User confirmation required: yes/no — reason
- Estimated runtime: ...
- Needed for essential claims: yes/no — which claim
- Decision: proceed / stop-and-ask / skip
```

Datasets and their contents are kept under `./input/data/` or `./workspace/` and are **never**
committed to the AutoPaperFactory repo or placed in `./paper/`.
