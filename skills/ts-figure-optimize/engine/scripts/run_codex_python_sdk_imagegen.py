#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.codex_python_sdk_imagegen import (  # noqa: E402
    CODEX_PYTHON_SDK_IMAGEGEN_RUNNER,
    check_codex_python_sdk_imagegen_capability,
    invoke_codex_python_sdk_image_edit,
    invoke_codex_python_sdk_imagegen,
)


def main() -> int:
    args = parse_args()
    prompt = _read_prompt(args)
    output_dir = args.output_dir.resolve()
    trace_path = args.trace.resolve() if args.trace else output_dir / "codex_python_sdk_imagegen_trace.jsonl"
    runtime_config: dict[str, object] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model

    started_at = time.time()
    summary_path = output_dir / "codex_imagegen_smoke_summary.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        "schema": "drawai.codex_python_sdk_imagegen_smoke.v1",
        "runner": CODEX_PYTHON_SDK_IMAGEGEN_RUNNER,
        "status": "running",
        "operation": "edit" if args.source_image else "generate",
        "prompt": prompt,
        "source_image": str(args.source_image.resolve()) if args.source_image else None,
        "output_dir": str(output_dir),
        "trace_path": str(trace_path),
        "model_name": args.model,
        "reasoning_effort": args.reasoning_effort,
        "timeout_seconds": args.timeout_seconds,
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    _write_json(summary_path, summary)

    if args.capability_only:
        capabilities = check_codex_python_sdk_imagegen_capability(
            timeout_seconds=args.timeout_seconds,
            isolated_cwd=args.cwd,
        )
        summary.update({"status": "ok", "capabilities": capabilities})
    else:
        if args.source_image:
            result = invoke_codex_python_sdk_image_edit(
                source_image_path=args.source_image,
                prompt=prompt,
                output_dir=output_dir,
                task_name=args.task_name,
                output_stem=args.output_stem,
                runtime_config=runtime_config,
                trace_path=trace_path,
                isolated_cwd=args.cwd,
                config_overrides=args.config_override,
            )
        else:
            result = invoke_codex_python_sdk_imagegen(
                prompt=prompt,
                output_dir=output_dir,
                task_name=args.task_name,
                output_stem=args.output_stem,
                runtime_config=runtime_config,
                trace_path=trace_path,
                isolated_cwd=args.cwd,
                config_overrides=args.config_override,
            )
        summary.update({"status": "ok", "result": result.to_dict()})

    summary.update(
        {
            "ended_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elapsed_seconds": round(time.time() - started_at, 3),
            "summary_path": str(summary_path),
        }
    )
    _write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one image through the Codex Python SDK built-in image generation tool."
    )
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Text prompt to turn into an image.")
    prompt_group.add_argument("--prompt-file", type=Path, help="UTF-8 file containing the text prompt.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "codex_sdk_imagegen",
        help="Directory for generated image, trace, and sanitized SDK archive.",
    )
    parser.add_argument("--output-stem", default="codex-sdk-imagegen", help="Output image filename stem.")
    parser.add_argument(
        "--source-image",
        type=Path,
        help="Optional local source image. When set, run built-in image edit instead of text-to-image.",
    )
    parser.add_argument("--trace", type=Path, help="Trace JSONL path. Defaults under --output-dir.")
    parser.add_argument("--cwd", type=Path, help="Codex SDK run cwd. Defaults to a temporary directory.")
    parser.add_argument("--model", default="", help="Optional Codex model override.")
    parser.add_argument(
        "--reasoning-effort",
        default="low",
        choices=["none", "minimal", "low", "medium", "high", "xhigh"],
    )
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument(
        "--task-name",
        default="drawai.codex_imagegen.text_to_image.v1",
        help="Trace/archive task name.",
    )
    parser.add_argument(
        "--config-override",
        action="append",
        default=[],
        help="Additional Codex -c key=value override for the SDK app-server.",
    )
    parser.add_argument(
        "--capability-only",
        action="store_true",
        help="Only check whether the SDK runtime reports image_generation capability.",
    )
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return args


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file is not None:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    else:
        prompt = str(args.prompt or "")
    prompt = prompt.strip()
    if not prompt:
        raise SystemExit("Prompt cannot be empty.")
    return prompt


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
