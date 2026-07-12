from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import write_json
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
    if args_list and args_list[0] == "asset":
        return _asset_cli(args_list[1:])
    if args_list and args_list[0] == "compose":
        return _run_root_stage_cli(args_list[1:], stage="compose_svg")
    if args_list and args_list[0] == "export":
        return _run_root_stage_cli(args_list[1:], stage="export")
    if args_list and args_list[0] == "server":
        from .server_cli import server_cli

        return server_cli(args_list[1:])
    if args_list and args_list[0] == "workbench":
        from .server_cli import workbench_cli

        return workbench_cli(args_list[1:])
    if args_list and args_list[0] == "workflow":
        from .workflow.cli import workflow_cli

        return workflow_cli(args_list[1:])
    if args_list and args_list[0] == "tool":
        from .tooling import drawai_tool_cli

        return drawai_tool_cli(args_list[1:])

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
    from .public_stages import LEGACY_STAGE_ALIASES, PUBLIC_STAGE_ORDER

    if argv and argv[0] in {*PUBLIC_STAGE_ORDER, *LEGACY_STAGE_ALIASES, "all"}:
        return _run_public_stage_cli(argv)

    from .local_cli import run_image_cli

    return run_image_cli(argv)


def _run_public_stage_cli(argv: Sequence[str]) -> int:
    from .public_stages import LEGACY_STAGE_ALIASES, PUBLIC_STAGE_ORDER, run_public_stage

    parser = argparse.ArgumentParser(description="Run a public DrawAI pipeline stage.")
    parser.add_argument("stage", choices=[*PUBLIC_STAGE_ORDER, *LEGACY_STAGE_ALIASES, "all"], help="Public stage to run.")
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


def _asset_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Manage DrawAI v2 asset packages.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    process = subparsers.add_parser("process", help="Process a single v2 element asset.")
    process.add_argument("run_dir", help="Path to a v2 run directory.")
    process.add_argument("element_id", help="Element id to process.")
    process.add_argument("--processor", required=True, help="Processor type to run.")

    activate = subparsers.add_parser("activate", help="Activate an existing asset result.")
    activate.add_argument("run_dir", help="Path to a v2 run directory.")
    activate.add_argument("element_id", help="Element id to update.")
    activate.add_argument("result_id", help="Result id to activate.")

    args = parser.parse_args(argv)
    root = Path(args.run_dir)
    if not _ensure_v2_root(root):
        return 2

    try:
        if args.command == "process":
            package = _process_single_asset(root, args.element_id, args.processor)
            print(json.dumps(package, ensure_ascii=False, indent=2))
            return 0
        if args.command == "activate":
            package = _activate_asset_result(root, args.element_id, args.result_id)
            print(json.dumps(package, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    raise AssertionError(f"Unsupported asset command: {args.command}")


def _run_root_stage_cli(argv: Sequence[str], *, stage: str) -> int:
    parser = argparse.ArgumentParser(description=f"Run DrawAI v2 {stage} for an existing run directory.")
    parser.add_argument("run_dir", help="Path to a v2 run directory.")
    parser.add_argument("--config", help="Optional DrawAI YAML config. Defaults to package metadata config_path.")
    args = parser.parse_args(argv)
    root = Path(args.run_dir)
    if not _ensure_v2_root(root):
        return 2
    try:
        from .pipeline import run_drawai_pipeline_from_stage

        cfg = _config_for_run_root(root, config_path=Path(args.config) if args.config else None)
        summary = run_drawai_pipeline_from_stage(cfg, stage, to_stage=stage)
        summary_path = summary.get("artifacts", {}).get("pipeline_summary")
        if summary_path:
            print(f"pipeline_summary: {summary_path}")
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary.get("status") == "ok" else 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _ensure_v2_root(root: Path) -> bool:
    from .v2.packages import classify_run_root

    classification = classify_run_root(root)
    if classification.mode == "v2":
        return True
    print(
        f"DrawAI run root is {classification.mode}; v2 asset commands require a v2 run.",
        file=sys.stderr,
    )
    return False


def _process_single_asset(root: Path, element_id: str, processor_type: str) -> dict[str, Any]:
    from .v2.packages import element_dir
    from .v2.processors import processor_for_type
    from .v2.schema import ProcessingIntent
    from .v2.stages import _plan_from_payload

    root = root.expanduser().resolve()
    element_path = element_dir(root, element_id)
    plan_payload = _read_json(element_path / "element.json")
    plan = _plan_from_payload(plan_payload)
    if plan.element_id != element_id:
        raise ValueError(
            f"element plan id {plan.element_id!r} does not match requested element_id {element_id!r}"
        )
    plan = replace(
        plan,
        processing_intent=ProcessingIntent(
            object_type=plan.processing_intent.object_type,
            processing_type=processor_type,
            parameters=dict(plan.processing_intent.parameters),
        ),
    )
    processor = processor_for_type(processor_type, providers={})
    try:
        package = processor.process(root, plan, source_image_path=_source_image_for_run(root))
    except Exception:
        failed_package_path = element_path / "asset_package.json"
        if failed_package_path.is_file():
            _sync_asset_package_into_run_package(root, _read_json(failed_package_path))
        raise
    payload = package.to_dict()
    _sync_asset_package_into_run_package(root, payload)
    return payload


def _activate_asset_result(root: Path, element_id: str, result_id: str) -> dict[str, Any]:
    from .v2.packages import read_asset_package

    root = root.expanduser().resolve()
    payload = read_asset_package(root, element_id)
    results = payload.get("all_results")
    if not isinstance(results, list):
        raise ValueError("asset package all_results must be a list")
    active_result = next(
        (result for result in results if isinstance(result, Mapping) and result.get("result_id") == result_id),
        None,
    )
    if active_result is None:
        raise ValueError(f"asset result not found: {result_id}")
    payload["active_result"] = dict(active_result)
    payload["status"] = str(active_result.get("status") or payload.get("status") or "ok")
    if payload["status"] == "ok":
        payload["failure"] = None
    write_json(root / "elements" / element_id / "asset_package.json", payload)
    _sync_asset_package_into_run_package(root, payload)
    return payload


def _sync_asset_package_into_run_package(root: Path, package_payload: Mapping[str, Any]) -> None:
    run_package_path = root / "drawai_package.json"
    run_package = _read_json(run_package_path)
    asset_packages = run_package.get("asset_packages")
    if not isinstance(asset_packages, list):
        asset_packages = []
    updated: list[Any] = []
    replaced_existing = False
    package_element_id = package_payload.get("element_id")
    package_asset_id = package_payload.get("asset_id")
    for item in asset_packages:
        if (
            isinstance(item, Mapping)
            and (item.get("element_id") == package_element_id or item.get("asset_id") == package_asset_id)
        ):
            updated.append(dict(package_payload))
            replaced_existing = True
        else:
            updated.append(item)
    if not replaced_existing:
        updated.append(dict(package_payload))
    run_package["asset_packages"] = updated
    write_json(run_package_path, run_package)


def _config_for_run_root(root: Path, *, config_path: Path | None) -> DrawAiPipelineConfig:
    root = root.expanduser().resolve()
    run_package = _read_json(root / "drawai_package.json")
    metadata = run_package.get("metadata") if isinstance(run_package.get("metadata"), Mapping) else {}
    raw_config_path = config_path
    if raw_config_path is None:
        metadata_config_path = metadata.get("config_path")
        if isinstance(metadata_config_path, str) and metadata_config_path and metadata_config_path != "None":
            raw_config_path = Path(metadata_config_path)
    source_image = _source_image_for_run(root)
    if raw_config_path is None:
        raise ValueError("v2 run root does not record a config_path; pass --config for compose/export")
    resolved_config_path = raw_config_path.expanduser().resolve()
    if not resolved_config_path.exists():
        raise FileNotFoundError(
            f"v2 run config is unavailable: {resolved_config_path}; pass --config for compose/export"
        )
    cfg = load_drawai_config(resolved_config_path, validate_input_exists=False)
    return replace(
        cfg,
        input=replace(cfg.input, image=source_image, output_dir=root),
    )


def _source_image_for_run(root: Path) -> Path:
    run_package = _read_json(root / "drawai_package.json")
    raw_source = run_package.get("source_image")
    if isinstance(raw_source, str) and raw_source:
        source = Path(raw_source)
        return source if source.is_absolute() else root / source
    fallback = root / "inputs" / "figure.png"
    if fallback.exists():
        return fallback
    return root / "inputs" / "original.png"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


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
        "v2": _json_safe(cfg.v2),
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
