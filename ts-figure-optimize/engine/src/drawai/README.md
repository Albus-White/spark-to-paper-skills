# DrawAI Package

Python package for the standalone DrawAI reconstruction path.

Primary entrypoints:

- `drawai.public_stages.run_public_stage`
- `drawai.public_stages.run_public_pipeline`
- `drawai.pipeline.run_drawai_pipeline`
- `drawai.pipeline.run_drawai_pipeline_from_stage`
- `python -m drawai.cli run all --config <config.yaml>`

Public stages:

```text
prepare
detect_structure
detect_text
assemble_boxir
asset_plan
asset_analyze
asset_materialize
svg
export
```

`detect_structure` and `detect_text` both consume the normalized input from `prepare`.
`assemble_boxir` can merge `both`, `structure`, `text`, or `auto` sources.
`asset_analyze` runs the Codex run0 element analysis that refines element
boundaries and SVG/crop/no-background source choices before SVG generation.
`asset_materialize` runs after that refinement so final crops and no-background
assets match the adjusted element plan.
