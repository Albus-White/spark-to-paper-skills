# Failure handling

| Failure | Detection | Handling |
|---|---|---|
| DrawAI produced no case dir | `find_case_dir` returns None | status `FAILED`, exit 6; check `drawai/runs/.../logs/case_001.stderr.log` |
| No `semantic.svg` after a round | file missing | break loop; keep best prior round; `REVIEW_REQUIRED`/`FAILED` |
| Invalid SVG | DrawAI `svg_validation_report.json` status != ok | DrawAI fails the stage itself; orchestrator sees no/invalid svg → repair or fail |
| PPTX export failed | `svg_to_ppt_export_report.json` status != ok / no pptx | editability gate fails; status not PASS |
| Screenshot-like PPTX | `verify_pptx_editability.py` → `is_single_screenshot_like` / too few shapes/text | gate fail, exit 5; never accept as final |
| No PPTX renderer | `render_pptx.py` → `NOT_RUN` (exit 3) | record `PPTX_RENDER_CHECK=NOT_RUN`; cannot auto-PASS |
| LPIPS/MS-SSIM lib missing | import fails | metric reported `null`, excluded from combined score (honest) |
| No agent CLI for LaTeX | `latex_via_llm` returns None | formula `latex=null`, flagged for manual transcription |
| Codex/OpenAI auth missing | DrawAI SVG stage errors before generation | fix auth (`~/.codex/auth.json` or `OPENAI_API_KEY`), rerun |
| Target 0.99 not reached | budget exhausted | status `REVIEW_REQUIRED` with true best score; require manual review |
| Regression in a round | iteration history shows lower combined | best-of-round selection keeps the better earlier round |

## General principles
- Fail loud, not silent: every gate writes a JSON with the reason; reports surface failures.
- Never fabricate a passing score to satisfy the gate.
- Preserve all intermediate attempts (`drawai/`, `comparisons/*_round*.json`) for debugging.
- The source image is never modified; the manuscript/figure is never touched by this skill.
- When in doubt, return `REVIEW_REQUIRED` and defer to human approval.

## Exit codes (`run_reconstruction.py`)
`0` PASS or REVIEW_REQUIRED (ran to completion) · `2` bad input · `6` DrawAI produced nothing ·
`7` FAILED. Per-tool: `render_pptx.py` `3`=NOT_RUN/`4`=render failed; `verify_pptx_editability.py` `5`=gate fail.
