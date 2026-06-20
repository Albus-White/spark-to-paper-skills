# DrawAI adapter

This skill uses DrawAI as its reconstruction engine. **DrawAI's source is VENDORED inside this skill at
`engine/`** (~5 MB: `src/drawai`, `scripts/`, `configs/`, `pyproject.toml`, `uv.lock`, `LICENSE`) — the
skill is self-contained for code. The heavy runtime (models + venv) is provisioned by
`scripts/setup_drawai.py`, never vendored. The orchestrator resolves the engine via `--drawai-repo` /
`$DRAWAI_REPO`, else the vendored `engine/`, else an upward search for `src/drawai`.

## Vendored version + the MPS fix (already applied)
- **Vendored from:** the commit recorded in `engine/ENGINE_VERSION.txt` (base `df01f19` + working-tree
  edits at vendor time).
- **MPS guard fix is already IN the vendored source** (`engine/src/drawai/local_runtime.py`,
  `_empty_torch_cache`): it guards `torch.mps.empty_cache()` with `_torch_mps_available(torch)` so runs
  don't crash on CPU/Linux with `RuntimeError: Cannot execute emptyCache() without MPS backend`. **No
  patching needed — it ships in `engine/`.**

## Updating DrawAI (MANUAL, by design)
To take a newer DrawAI: re-copy `src/ scripts/ configs/ pyproject.toml uv.lock LICENSE` from the upstream
checkout into `engine/`, re-apply the MPS guard if upstream hasn't merged it, bump
`engine/ENGINE_VERSION.txt`, then `python scripts/setup_drawai.py --check-only` and run the skill's tests.
The integration surface is tiny (`run_reconstruction.py:collect()`/`find_case_dir()` + the output paths),
so upstream refactors rarely need more than this.

Record the exact commit you validated against in the run report. If DrawAI is later moved to its own
repo, pin it as a git submodule/subtree at this commit and keep this adapter as the only integration
point.

## Two ways to call DrawAI

### 1. CLI (primary; used by `run_reconstruction.py`)
```bash
uv run --frozen drawai run <abs_image> --local --run-name <name> --out <drawai_runs> --device cpu
```
The CLI handles the venv re-exec into the local runtime (`.local/drawai_runtime/.venv`, which has
SAM3/PaddleOCR/RMBG/torch). Output: `<drawai_runs>/<date>/<time>_<name>/outputs/case_001_<slug>/`.

Repair (SVG re-generation + PPTX re-export only, reading existing IR/assets from disk):
```bash
uv run --frozen drawai --config <case_dir>/../../configs/case_001.yaml \
  --from-stage svg_generated --to-stage svg_to_ppt_exported
```

> `--frozen` is required: a plain `uv run` re-resolves dependencies and fails to find the
> `openai-codex` prerelease in this environment. See **Environment workarounds**.

### 2. Library API (alternative; must run inside the runtime venv)
```python
from drawai.config import load_drawai_config
from drawai.public_stages import run_public_stage   # stage="all"
# or: from drawai.pipeline import run_drawai_pipeline_from_stage  # targeted reruns
summary = run_public_stage(case_config_path, "all", sources="both", parallel=False)
```
The library path needs SAM3/PaddleOCR/RMBG importable, i.e. it must run under
`.local/drawai_runtime/.venv`. The CLI path is preferred because it manages that automatically.

## Outputs consumed by the skill
| DrawAI artifact | skill copy |
|---|---|
| `box_ir/box_ir.json` | `ir/box_ir.json` |
| `sam3/raw_regions.json` | `ir/regions.json` |
| `ocr/ocr_boxes.json` | `ir/ocr_boxes.json` |
| `svg/semantic.svg` | `svg/semantic.svg` |
| `svg/rendered.png` | `svg/rendered_svg.png` |
| `svg_to_ppt/semantic.svg_to_ppt.pptx` | `pptx/editable.pptx` |
| `reports/*.json` | `drawai/*.json` |

## Environment workarounds (this machine / proxy)
- **`uv run --frozen`** everywhere (prerelease `openai-codex` not resolvable via plain `uv run`).
- **PaddlePaddle** install: the bootstrap's hardcoded `paddlepaddle.org.cn` index is unreachable behind
  the proxy; install `paddlepaddle==3.2.0` from PyPI. The full manual runtime-venv completion (torch CPU,
  paddleocr/paddlex/transformers, `openai-codex` via `--index-url https://pypi.org/simple/`, SAM3 editable,
  `triton`) is documented in `docs/DRAWAI_METHOD_OVERVIEW_SPIKE_REPORT.md` §2.
- **No Chrome** → SVG validation/preview falls back to cairosvg (fine).
- **No LibreOffice** here → PPTX render is `NOT_RUN`; provide `soffice` (or set `$DRAWAI_SOFFICE`) to
  enable the PPTX render gate.
- **GPU**: shared/near-full H100s + bleeding-edge CUDA → use `--device cpu` for reliability (quality is
  identical, only slower).

## Raster assets & waveforms (interaction with the visual-quality gates)
- DrawAI's run0/materialization already emits **transparent `_nobg.png` crops** (RMBG + edge cleanup) for
  many assets, and may inline some as **base64 data-URIs** in `semantic.svg`. Hrefs are relative to the
  **case `svg/` dir** (e.g. `../svg_to_ppt/assets/crops/run0_refined/R0_*.png`), so the visual-quality
  fixers run against the case SVG (where hrefs resolve), write `*_bgfix.png` beside the originals (or rewrite
  the data-URI in place), then the PPTX is re-exported with `drawai --from-stage svg_to_ppt_exported`.
- `RASTER_BACKGROUND_MATCH` therefore mostly catches the residual **opaque/mismatched** crops DrawAI did not
  make transparent; transparent-bordered crops pass immediately.
- DrawAI generates waveforms as part of its global SVG; it has no waveform-shape control knob, so the
  `WAVEFORM_STYLE` gate + `waveform_primitive.py` post-repair are how the bar-style standard is enforced
  without modifying DrawAI source. (A future upstream option: add the bar-style waveform rule to DrawAI's
  scientific-SVG profile prompt.)

## Don'ts
- Do not copy `.local/drawai_runtime/` (models, ~4 GB) or `runs/` into the skill or commit them.
- Do not commit API keys / `~/.codex/auth.json`.
