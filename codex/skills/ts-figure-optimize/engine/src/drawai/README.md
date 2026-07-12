# DrawAI Package

Python package for the standalone DrawAI reconstruction path.

Primary entrypoints:

- `drawai.public_stages.run_public_stage`
- `drawai.public_stages.run_public_pipeline`
- `drawai.pipeline.run_drawai_pipeline`
- `drawai.pipeline.run_drawai_pipeline_from_stage`
- `python -m drawai.cli run all --config <config.yaml>`
- `python -m drawai.cli asset process <run_dir> <element_id> --processor <type>`
- `python -m drawai.cli compose <run_dir>`
- `python -m drawai.cli export <run_dir>`

Public stages:

```text
prepare
parse_elements
fuse_elements
refine_elements
plan_assets
process_assets
compose_svg
export
package_run
```

Legacy public stage aliases such as `detect_structure`, `detect_text`,
`assemble_boxir`, `asset_plan`, `asset_analyze`, `asset_materialize`, and `svg`
are accepted by the CLI and mapped onto the v2 stages above.

`parse_elements` normalizes parser output from SAM3, OCR, or additional parser
adapters into a shared element-candidate schema. `fuse_elements` applies the
configured fusion rules and writes the first `drawai_package.json`.
`refine_elements` optionally invokes an Agent-backed refiner, currently Codex by
default, to correct element position, size, and type. `plan_assets` and
`process_assets` create per-element packages under `elements/<element_id>/`.
`compose_svg`, `export`, and `package_run` attach render and export outputs back
to the run package.

Important v2 config switches:

```yaml
v2:
  parser:
    sam3_enabled: true
    ocr_enabled: true
  fusion:
    duplicate_iou_threshold: 0.85
  refine:
    enabled: true
    provider: codex_element_refiner
  processor:
    enabled: true
  compose:
    enabled: true
```

Set `v2.refine.enabled: false` for deterministic parser/fusion packaging
without Agent refinement. Set `v2.compose.enabled: false` when you want to stop
after data-package creation and skip SVG generation/export recomposition.
