#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.codex_python_sdk_svg import (  # noqa: E402
    CODEX_PYTHON_SDK_RUNNER,
    invoke_codex_python_sdk_svg_text,
)
from drawai.config import load_drawai_config  # noqa: E402
from drawai.pipeline import _svg_generation_prompt  # noqa: E402
from drawai.svg_generation_loop import (  # noqa: E402
    SvgGenerationError,
    run_svg_generation_loop,
)


def main() -> int:
    args = parse_args()
    case_dir = args.case_dir.resolve() if args.case_dir else find_latest_completed_case_dir()
    config_path = args.config.resolve() if args.config else config_path_for_case(case_dir)
    cfg = load_drawai_config(config_path)
    output_dir = args.output_dir.resolve() if args.output_dir else default_output_dir(case_dir)
    trace_path = output_dir / "trace" / "codex_python_sdk_svg.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path.parent.mkdir(parents=True, exist_ok=True)

    box_ir = read_json(case_dir / "box_ir" / "box_ir.json")
    asset_manifest = read_json(case_dir / "svg_to_ppt" / "assets" / "asset_manifest.json")
    template_ir = read_json(case_dir / "svg" / "svg_template_ir.json")
    runtime_config = cfg.model_runtime.to_runtime_dict()
    if args.model:
        runtime_config["model_name"] = args.model

    def invoker(**kwargs: Any) -> str:
        prompt_kwargs = dict(kwargs)
        prompt_kwargs["file_context_mode"] = True
        prompt_kwargs["workspace_dir"] = case_dir
        prompt = _svg_generation_prompt(prompt_kwargs)
        prompt_path = kwargs.get("prompt_path")
        if prompt_path is not None:
            prompt_output = Path(prompt_path)
            prompt_output.parent.mkdir(parents=True, exist_ok=True)
            prompt_output.write_text(prompt, encoding="utf-8")
        phase = str(kwargs.get("phase") or "single")
        return invoke_codex_python_sdk_svg_text(
            image_paths=[Path(kwargs["figure_path"]), Path(kwargs["reference_image_path"])],
            prompt=prompt,
            task_name=f"box_ir_semantic_svg.{phase}.v1",
            runtime_config=runtime_config,
            trace_path=trace_path,
            isolated_cwd=case_dir,
            output_svg_path=Path(kwargs["output_svg_path"]),
            output_response_path=Path(kwargs["output_response_path"]),
            config_overrides=args.config_override,
        )

    started_at = time.time()
    summary: dict[str, Any] = {
        "schema": "drawai.codex_python_sdk_svg_stage_smoke.v1",
        "runner": CODEX_PYTHON_SDK_RUNNER,
        "status": "running",
        "case_dir": str(case_dir),
        "config_path": str(config_path),
        "output_dir": str(output_dir),
        "trace_path": str(trace_path),
        "model_name": str(runtime_config.get("model_name") or ""),
        "staged_generation": not args.no_staged_generation,
        "max_attempts": args.max_attempts,
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    summary_path = output_dir / "codex_python_sdk_svg_stage_summary.json"
    write_json(summary_path, summary)
    try:
        result = run_svg_generation_loop(
            box_ir=box_ir,
            figure_path=case_dir / "svg" / "svg_generation_reference.png",
            reference_image_path=case_dir / "svg" / "template_reference.png",
            asset_manifest=asset_manifest,
            output_dir=output_dir,
            max_attempts=args.max_attempts,
            invoker=invoker,
            runtime_config=runtime_config,
            staged_generation=not args.no_staged_generation,
            visual_review_rounds=tuple(args.visual_review_rounds),
            template_ir=template_ir,
            text_rendering=cfg.svg.text_rendering,
        )
    except SvgGenerationError as exc:
        summary.update(
            {
                "status": "failed",
                "error": str(exc),
                "error_metadata": exc.metadata,
            }
        )
    else:
        summary.update({"status": "ok", "result": result})
    summary.update(
        {
            "ended_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elapsed_seconds": round(time.time() - started_at, 3),
            "summary_path": str(summary_path),
        }
    )
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "ok" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run only the DrawAI SVG generation stage with the controlled Codex Python SDK adapter."
    )
    parser.add_argument("--case-dir", type=Path, help="Existing DrawAI case output directory with box_ir/svg/assets artifacts.")
    parser.add_argument("--config", type=Path, help="Case config path. Defaults to case_manifest.json config_path.")
    parser.add_argument("--output-dir", type=Path, help="Output directory for the SVG-stage smoke artifacts.")
    parser.add_argument("--model", default="", help="Override Codex model name for this smoke run.")
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--no-staged-generation", action="store_true", help="Run single-shot SVG generation instead of staged SVG generation.")
    parser.add_argument(
        "--visual-review-round",
        dest="visual_review_rounds",
        action="append",
        default=[],
        help="Visual review round to run. Repeatable. Defaults to the case config rounds.",
    )
    parser.add_argument(
        "--config-override",
        action="append",
        default=[],
        help="Additional Codex -c key=value override for the SDK app-server.",
    )
    parsed = parser.parse_args()
    if parsed.max_attempts <= 0:
        parser.error("--max-attempts must be positive")
    if not parsed.visual_review_rounds:
        parsed.visual_review_rounds = ["text_style"]
    return parsed


def find_latest_completed_case_dir() -> Path:
    summaries = sorted((REPO_ROOT / "runs").glob("**/reports/run_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for summary_path in summaries:
        payload = read_json(summary_path)
        for case in payload.get("cases") or []:
            if not isinstance(case, Mapping) or case.get("status") != "completed":
                continue
            semantic_svg = case.get("semantic_svg")
            if not isinstance(semantic_svg, str) or not semantic_svg:
                continue
            case_dir = Path(semantic_svg).resolve().parents[1]
            if required_case_artifacts_exist(case_dir):
                return case_dir
    raise SystemExit("No completed case with required SVG-stage artifacts was found under runs/.")


def required_case_artifacts_exist(case_dir: Path) -> bool:
    required = (
        case_dir / "box_ir" / "box_ir.json",
        case_dir / "svg_to_ppt" / "assets" / "asset_manifest.json",
        case_dir / "svg" / "svg_template_ir.json",
        case_dir / "svg" / "svg_generation_reference.png",
        case_dir / "svg" / "template_reference.png",
        case_dir / "case_manifest.json",
    )
    return all(path.exists() for path in required)


def config_path_for_case(case_dir: Path) -> Path:
    manifest_path = case_dir / "case_manifest.json"
    manifest = read_json(manifest_path)
    config_path = manifest.get("config_path")
    if not isinstance(config_path, str) or not config_path:
        raise SystemExit(f"case manifest does not contain config_path: {manifest_path}")
    return Path(config_path)


def default_output_dir(case_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return case_dir / f"svg_codex_python_sdk_smoke_{stamp}"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
