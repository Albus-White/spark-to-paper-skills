from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import DrawAiPipelineConfig, load_drawai_config


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if args_list and args_list[0] == "setup":
        from .local_cli import setup_cli

        return setup_cli(args_list[1:])
    if args_list and args_list[0] == "doctor":
        from .local_cli import doctor_cli

        return doctor_cli(args_list[1:])
    if args_list and args_list[0] == "run":
        return _run_cli(args_list[1:])
    if args_list and args_list[0] == "server":
        from .server_cli import server_cli

        return server_cli(args_list[1:])
    if args_list and args_list[0] == "workbench":
        from .server_cli import workbench_cli

        return workbench_cli(args_list[1:])

    parser = argparse.ArgumentParser(description="Run the DrawAI SVG pipeline.")
    parser.add_argument("--config", required=True, help="Path to a DrawAI pipeline YAML config.")
    parser.add_argument(
        "--dry-run-config",
        action="store_true",
        help="Validate config schema/parseability and print a JSON summary; skips input existence, remote, and model execution.",
    )
    parser.add_argument(
        "--from-stage",
        help="Run from a persisted file-backed stage instead of starting a fresh full pipeline.",
    )
    parser.add_argument(
        "--to-stage",
        help="Optional last stage for --from-stage reruns. Defaults to svg_to_ppt_exported.",
    )
    args = parser.parse_args(argv)

    try:
        if args.dry_run_config:
            cfg = load_drawai_config(args.config, validate_input_exists=False)
            print(json.dumps(dry_run_config_summary(cfg), ensure_ascii=False, indent=2))
            return 0

        from .pipeline import run_drawai_pipeline, run_drawai_pipeline_from_stage

        if args.from_stage:
            summary = run_drawai_pipeline_from_stage(
                Path(args.config),
                args.from_stage,
                to_stage=args.to_stage,
            )
        else:
            summary = run_drawai_pipeline(Path(args.config))
        summary_path = summary.get("artifacts", {}).get("pipeline_summary")
        if summary_path:
            print(f"pipeline_summary: {summary_path}")
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary.get("status") == "ok" else 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _run_cli(argv: Sequence[str]) -> int:
    from .public_stages import PUBLIC_STAGE_ORDER

    if argv and argv[0] in {*PUBLIC_STAGE_ORDER, "all"}:
        return _run_public_stage_cli(argv)

    from .local_cli import run_image_cli

    return run_image_cli(argv)


def _run_public_stage_cli(argv: Sequence[str]) -> int:
    from .public_stages import PUBLIC_STAGE_ORDER, run_public_stage

    parser = argparse.ArgumentParser(description="Run a public DrawAI pipeline stage.")
    parser.add_argument("stage", choices=[*PUBLIC_STAGE_ORDER, "all"], help="Public stage to run.")
    parser.add_argument("--config", required=True, help="Path to a DrawAI YAML config.")
    parser.add_argument(
        "--sources",
        choices=["both", "structure", "text", "auto"],
        default="both",
        help="Sources used by assemble_boxir or all.",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="For all, run detect_structure and detect_text sequentially instead of in parallel.",
    )
    args = parser.parse_args(argv)
    try:
        summary = run_public_stage(
            Path(args.config),
            args.stage,
            sources=args.sources,
            parallel=not args.sequential,
        )
        summary_path = summary.get("artifacts", {}).get("pipeline_summary")
        if summary_path and Path(summary_path).exists():
            print(f"pipeline_summary: {summary_path}")
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary.get("status") == "ok" else 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def dry_run_config_summary(cfg: DrawAiPipelineConfig) -> dict[str, Any]:
    model_runtime = _json_safe(cfg.model_runtime)
    if isinstance(model_runtime, dict) and model_runtime.get("api_key"):
        model_runtime["api_key"] = "[redacted]"
    return {
        "schema": "drawai.pipeline_config_summary.v1",
        "status": "ok",
        "config_path": str(cfg.config_path) if cfg.config_path is not None else None,
        "input": {
            "image": str(cfg.input.image),
            "output_dir": str(cfg.input.output_dir),
            "normalization": _json_safe(cfg.input.normalization),
        },
        "sam3": {
            "base_url": cfg.sam3.base_url,
            "timeout_seconds": cfg.sam3.timeout_seconds,
            "return_overlay": cfg.sam3.return_overlay,
            "return_masks": cfg.sam3.return_masks,
            "service_merge_threshold": cfg.sam3.service_merge_threshold,
            "prompts": [_json_safe(prompt) for prompt in cfg.sam3.prompts],
        },
        "ocr": _json_safe(cfg.ocr),
        "asset_selection": _json_safe(cfg.asset_selection),
        "asset_materialization": _json_safe(cfg.asset_materialization),
        "svg": _json_safe(cfg.svg),
        "svg_to_ppt": _json_safe(cfg.svg_to_ppt),
        "model_runtime": model_runtime,
    }


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
