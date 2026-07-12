from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from drawai.page_spec_assets import materialized_asset_records, page_spec_asset_manifest


ToolRunner = Callable[[Sequence[str]], int]


@dataclass(frozen=True)
class DrawAITool:
    tool_id: str
    summary: str
    parameters: tuple[str, ...]
    examples: tuple[str, ...]
    runner: ToolRunner

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "summary": self.summary,
            "parameters": list(self.parameters),
            "examples": list(self.examples),
        }


def drawai_tool_registry() -> dict[str, DrawAITool]:
    return {
        "format": DrawAITool(
            tool_id="format",
            summary="检查并校验 DrawAI workflow 文件格式。",
            parameters=(
                "describe <format_id>: 输出已注册的格式契约。",
                "validate --format-id <format_id> --path <file>: 校验具体文件并输出 JSON。",
            ),
            examples=(
                "format describe drawai.page_spec.v1",
                "format validate --format-id drawai.page_spec.v1 --path nodes/asset_prepare/runs/001/output/page_spec.json",
            ),
            runner=_format_tool,
        ),
        "page-spec-assets": DrawAITool(
            tool_id="page-spec-assets",
            summary="列出 PageSpec element 的 materialized assets，并根据目标 SVG 目录计算可用的 SVG href。",
            parameters=(
                "--page-spec <path>: 包含 element.materialization 输出的 PageSpec JSON。",
                "--svg-dir <path>: SVG 将被写入的目录；工具用它计算相对 href。",
            ),
            examples=(
                "page-spec-assets --page-spec nodes/asset_prepare/runs/001/output/page_spec.json --svg-dir svg",
            ),
            runner=_page_spec_assets_tool,
        ),
        "page-spec-svg-draft": DrawAITool(
            tool_id="page-spec-svg-draft",
            summary=(
                "从 materialized PageSpec 和允许的 raster assets 生成 baseline semantic SVG。"
                "请求 validation 时，也会把通过校验的 draft 提升为 canonical Workbench outputs。"
            ),
            parameters=(
                "--page-spec <path>: 包含 element.materialization 输出的 materialized PageSpec JSON。",
                "--svg <path>: 要写出的 SVG 路径；通过校验的 semantic_0.svg 等 draft 会被复制到 semantic.svg。",
                "--href-base-dir <path>: 用于计算/校验 SVG href 的基础目录；最终 deliverables 使用 svg。",
                "--rendered <path>: 可选 PNG render 输出路径；通过校验的 draft 会被复制到 rendered.png。",
                "--report <path>: 可选 JSON validation report 输出路径；通过校验的 draft 会被复制到 validation_report_final.json。",
                "--iteration-log-md <path>: 可选 Markdown iteration log 输出路径。",
                "--iteration-log-jsonl <path>: 可选 JSONL iteration log 输出路径。",
            ),
            examples=(
                "page-spec-svg-draft --page-spec nodes/asset_prepare/runs/001/output/page_spec.json --svg nodes/svg_compose/runs/001/output/semantic.svg --href-base-dir svg --rendered nodes/svg_compose/runs/001/output/rendered.png --report nodes/svg_compose/runs/001/output/validation_report_final.json --iteration-log-md nodes/svg_compose/runs/001/output/iteration_log.md --iteration-log-jsonl nodes/svg_compose/runs/001/output/iteration_log.jsonl",
            ),
            runner=_page_spec_svg_draft_tool,
        ),
        "svg-validate": DrawAITool(
            tool_id="svg-validate",
            summary="使用 PageSpec 的 canvas 和 materialized asset 信息校验并渲染 semantic SVG。",
            parameters=(
                "--svg <path>: 要校验的 SVG 文件。",
                "--page-spec <path>: 用于 canvas size 和 allowed raster assets 的 PageSpec JSON。",
                "--rendered <path>: 要写出的 PNG render 路径。",
                "--report <path>: 要写出的 JSON validation report 路径。",
                "--href-base-dir <path>: 用于解析 SVG href 的基础目录；最终 deliverables 使用 svg。",
                "--allow-external-assets: 可选 escape hatch，允许非本地 assets；默认 false。",
            ),
            examples=(
                "svg-validate --svg nodes/svg_compose/runs/001/output/semantic.svg --page-spec nodes/asset_prepare/runs/001/output/page_spec.json --rendered nodes/svg_compose/runs/001/output/rendered.png --report nodes/svg_compose/runs/001/output/validation_report_final.json --href-base-dir svg",
            ),
            runner=_svg_validate_tool,
        ),
    }


def drawai_tool_cli(argv: Sequence[str] | None = None) -> int:
    args = list(argv or ())
    registry = drawai_tool_registry()
    if not args:
        return _tool_list(registry, json_output=False)
    if args[0] == "list":
        parser = argparse.ArgumentParser(prog="drawai tool list", description="List DrawAI tools.")
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        parsed = parser.parse_args(args[1:])
        return _tool_list(registry, json_output=parsed.json)
    if args[0] == "help":
        parser = argparse.ArgumentParser(prog="drawai tool help", description="Show one DrawAI tool contract.")
        parser.add_argument("tool_id")
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        parsed = parser.parse_args(args[1:])
        tool = _required_tool(registry, parsed.tool_id)
        if parsed.json:
            _print_json(tool.to_dict())
        else:
            print(drawai_tool_help_text(tool))
        return 0
    tool = _required_tool(registry, args[0])
    return tool.runner(args[1:])


def drawai_tool_help_text(tool: DrawAITool) -> str:
    lines = [f"DrawAI tool: {tool.tool_id}", "", tool.summary, "", "Parameters:"]
    lines.extend(f"- {parameter}" for parameter in tool.parameters)
    if tool.examples:
        lines.extend(["", "Examples:"])
        lines.extend(f"- drawai tool {example}" for example in tool.examples)
    return "\n".join(lines)


def render_drawai_tool_prompt_section(
    tool_ids: Sequence[str],
    *,
    command_prefix: str,
    invocation: Literal["cli", "tool_call"] = "cli",
) -> str:
    registry = drawai_tool_registry()
    selected = [_required_tool(registry, tool_id) for tool_id in _ordered_unique(tool_ids)]
    if invocation == "tool_call":
        return _render_drawai_tool_call_prompt_section(selected)
    lines = [
        "## DrawAI 工具",
        "只能使用下面列出的 DrawAI tools。它们是 CLI 产品接口，不是直接调用的 Python 内部函数。",
        f"Agent cwd 下的精确命令前缀：`{command_prefix}`",
        "使用不熟悉的工具参数前，先运行 `<command prefix> help <tool_id>` 查看完整契约。",
    ]
    for tool in selected:
        lines.extend(
            [
                "",
                f"### Tool `{tool.tool_id}`",
                tool.summary,
                "参数：",
            ]
        )
        lines.extend(f"- {parameter}" for parameter in tool.parameters)
        if tool.examples:
            lines.append("示例：")
            lines.extend(f"- `{command_prefix} {example}`" for example in tool.examples)
    return "\n".join(lines)


def _render_drawai_tool_call_prompt_section(tools: Sequence[DrawAITool]) -> str:
    lines = [
        "## DrawAI 工具",
        "只能使用下面列出的 DrawAI tools。它们是通过 `run_drawai_tool` API tool 暴露的产品接口，不是 shell commands。",
        "调用 `run_drawai_tool` 时传入 `tool_id` 和 `args` string array。使用不熟悉的工具前，先调用 `tool_id: \"help\"` 和 `args: [\"<tool_id>\"]` 查看契约。",
    ]
    for tool in tools:
        lines.extend(
            [
                "",
                f"### Tool `{tool.tool_id}`",
                tool.summary,
                "参数：",
            ]
        )
        lines.extend(f"- {parameter}" for parameter in tool.parameters)
        if tool.examples:
            lines.append("示例：")
            for example in tool.examples:
                invocation = _tool_call_example(example)
                lines.append(f"- `{invocation}`")
    return "\n".join(lines)


def _tool_call_example(example: str) -> str:
    parts = shlex.split(example)
    if not parts:
        return 'run_drawai_tool({"tool_id": "", "args": []})'
    return "run_drawai_tool(" + json.dumps(
        {"tool_id": parts[0], "args": parts[1:]},
        ensure_ascii=False,
    ) + ")"


def resolve_drawai_tool_command_prefix(repo_root: str | Path, *, cwd: str | Path) -> str:
    repo = Path(repo_root).expanduser().resolve(strict=False)
    src_dir = repo / "src"
    command = [sys.executable, "-m", "drawai.cli", "tool", "list", "--json"]
    env = os.environ.copy()
    env["PYTHONPATH"] = _prepend_pythonpath(src_dir, env.get("PYTHONPATH"))
    completed = subprocess.run(
        command,
        cwd=str(Path(cwd).expanduser().resolve(strict=False)),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "DrawAI tool CLI is not executable from the workflow run root: "
            + completed.stderr.strip()
        )
    return " ".join(
        [
            "env",
            f"PYTHONPATH={shlex.quote(str(src_dir))}",
            shlex.quote(sys.executable),
            "-m",
            "drawai.cli",
            "tool",
        ]
    )


def _format_tool(argv: Sequence[str]) -> int:
    from drawai.workflow.formats import default_format_registry, validate_format_file

    parser = argparse.ArgumentParser(prog="drawai tool format", description="Inspect and validate DrawAI formats.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    describe = subparsers.add_parser("describe", help="Describe a format contract.")
    describe.add_argument("format_id")
    validate = subparsers.add_parser("validate", help="Validate a file against a format.")
    validate.add_argument("--format-id", required=True)
    validate.add_argument("--path", required=True, type=Path)
    args = parser.parse_args(list(argv))
    registry = default_format_registry()
    if args.command == "describe":
        spec = registry.get(args.format_id)
        if spec is None:
            raise SystemExit(f"unknown format: {args.format_id}")
        _print_json(
            {
                "format_id": spec.format_id,
                "label": spec.label,
                "media_type": spec.media_type,
                "artifact_type": spec.artifact_type,
                "description": spec.description,
            }
        )
        return 0
    if args.command == "validate":
        result = validate_format_file(args.format_id, args.path, registry=registry)
        _print_json(result.to_dict())
        return 0 if result.ok else 1
    raise AssertionError(f"unsupported format tool command: {args.command}")


def _page_spec_assets_tool(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="drawai tool page-spec-assets",
        description="List materialized PageSpec assets and SVG hrefs.",
    )
    parser.add_argument("--page-spec", required=True, type=Path)
    parser.add_argument("--svg-dir", required=True, type=Path)
    args = parser.parse_args(list(argv))
    _print_json(
        {
            "schema": "drawai.tool.page_spec_assets.v1",
            "page_spec": str(args.page_spec),
            "svg_dir": str(args.svg_dir),
            "assets": materialized_asset_records(args.page_spec, svg_dir=args.svg_dir),
        }
    )
    return 0


def _page_spec_svg_draft_tool(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="drawai tool page-spec-svg-draft",
        description="Generate a baseline semantic SVG from a materialized PageSpec.",
    )
    parser.add_argument("--page-spec", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--href-base-dir", type=Path)
    parser.add_argument("--rendered", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--iteration-log-md", type=Path)
    parser.add_argument("--iteration-log-jsonl", type=Path)
    args = parser.parse_args(list(argv))

    from drawai.page_spec_svg import draft_semantic_svg_from_page_spec

    href_base_dir = args.href_base_dir or args.svg.parent
    href_base_dir.mkdir(parents=True, exist_ok=True)
    result = draft_semantic_svg_from_page_spec(
        args.page_spec,
        args.svg,
        href_base_dir=href_base_dir,
    )
    if args.report is not None or args.rendered is not None:
        if args.report is None or args.rendered is None:
            raise SystemExit("--rendered and --report must be provided together")
        from drawai.svg_validation import validate_svg_file

        page_spec = json.loads(args.page_spec.read_text(encoding="utf-8"))
        if not isinstance(page_spec, Mapping):
            raise ValueError("PageSpec must be a JSON object")
        canvas = page_spec.get("canvas") if isinstance(page_spec.get("canvas"), Mapping) else {}
        canvas_payload = {
            "width": canvas.get("width_px", canvas.get("width")),
            "height": canvas.get("height_px", canvas.get("height")),
        }
        asset_manifest = page_spec_asset_manifest(args.page_spec, svg_dir=href_base_dir)
        report = validate_svg_file(
            args.svg,
            canvas_payload,
            asset_manifest,
            args.rendered,
            reference_dir=href_base_dir,
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["validation"] = report
        if report.get("status") == "ok":
            _finalize_page_spec_svg_draft_outputs(
                result,
                svg_path=args.svg,
                rendered_path=args.rendered,
                report_path=args.report,
            )
    _write_page_spec_svg_draft_logs(result, args.iteration_log_md, args.iteration_log_jsonl)
    _print_json(result)
    validation = result.get("validation")
    if isinstance(validation, Mapping) and validation.get("status") != "ok":
        return 1
    return 0


def _svg_validate_tool(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="drawai tool svg-validate",
        description="Validate/render a semantic SVG with PageSpec materialization constraints.",
    )
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--page-spec", required=True, type=Path)
    parser.add_argument("--rendered", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--href-base-dir", type=Path)
    parser.add_argument("--allow-external-assets", action="store_true")
    args = parser.parse_args(list(argv))
    from drawai.svg_validation import validate_svg_file

    page_spec = json.loads(args.page_spec.read_text(encoding="utf-8"))
    if not isinstance(page_spec, Mapping):
        raise ValueError("PageSpec must be a JSON object")
    canvas = page_spec.get("canvas") if isinstance(page_spec.get("canvas"), Mapping) else {}
    canvas_payload = {
        "width": canvas.get("width_px", canvas.get("width")),
        "height": canvas.get("height_px", canvas.get("height")),
    }
    href_base_dir = args.href_base_dir or args.svg.parent
    asset_manifest = page_spec_asset_manifest(args.page_spec, svg_dir=href_base_dir)
    report = validate_svg_file(
        args.svg,
        canvas_payload,
        asset_manifest,
        args.rendered,
        allow_external_assets=args.allow_external_assets,
        reference_dir=href_base_dir,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_json(report)
    return 0 if report.get("status") == "ok" else 1


def _finalize_page_spec_svg_draft_outputs(
    result: dict[str, Any],
    *,
    svg_path: Path,
    rendered_path: Path,
    report_path: Path,
) -> None:
    final_svg = svg_path.with_name("semantic.svg")
    declared_svg = svg_path.with_name("semantic_svg.svg")
    final_rendered = rendered_path.with_name("rendered.png")
    final_report = report_path.with_name("validation_report_final.json")

    _copy_if_different(svg_path, final_svg)
    _copy_if_different(svg_path, declared_svg)
    _copy_if_different(rendered_path, final_rendered)
    _copy_if_different(report_path, final_report)

    result["finalized_outputs"] = {
        "semantic_svg": str(final_svg),
        "declared_semantic_svg": str(declared_svg),
        "rendered_png": str(final_rendered),
        "validation_report": str(final_report),
    }


def _copy_if_different(source: Path, destination: Path) -> None:
    source_resolved = source.expanduser().resolve(strict=False)
    destination_resolved = destination.expanduser().resolve(strict=False)
    if source_resolved == destination_resolved:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _write_page_spec_svg_draft_logs(
    result: Mapping[str, Any],
    iteration_log_md: Path | None,
    iteration_log_jsonl: Path | None,
) -> None:
    if iteration_log_md is not None:
        iteration_log_md.parent.mkdir(parents=True, exist_ok=True)
        validation = result.get("validation")
        status = validation.get("status") if isinstance(validation, Mapping) else "not_run"
        iteration_log_md.write_text(
            "\n".join(
                [
                    "# SVG Iteration Log",
                    "",
                    "- run: page-spec-svg-draft",
                    f"- svg: {result.get('svg')}",
                    f"- rendered_elements: {result.get('rendered_elements')}",
                    f"- asset_images: {result.get('asset_images')}",
                    f"- editable_text: {result.get('editable_text')}",
                    f"- editable_vectors: {result.get('editable_vectors')}",
                    f"- validation_status: {status}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    if iteration_log_jsonl is not None:
        iteration_log_jsonl.parent.mkdir(parents=True, exist_ok=True)
        iteration_log_jsonl.write_text(json.dumps(dict(result), ensure_ascii=False) + "\n", encoding="utf-8")


def _tool_list(registry: Mapping[str, DrawAITool], *, json_output: bool) -> int:
    if json_output:
        _print_json({"tools": [tool.to_dict() for tool in registry.values()]})
    else:
        for tool in registry.values():
            print(f"{tool.tool_id}\t{tool.summary}")
    return 0


def _required_tool(registry: Mapping[str, DrawAITool], tool_id: str) -> DrawAITool:
    tool = registry.get(tool_id)
    if tool is None:
        available = ", ".join(sorted(registry))
        raise SystemExit(f"unknown DrawAI tool {tool_id!r}; available tools: {available}")
    return tool


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if not clean or clean in seen:
            continue
        ordered.append(clean)
        seen.add(clean)
    return tuple(ordered)


def _prepend_pythonpath(src_dir: Path, current: str | None) -> str:
    src = str(src_dir)
    if not current:
        return src
    parts = current.split(os.pathsep)
    if src in parts:
        return current
    return os.pathsep.join([src, current])


def _print_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), ensure_ascii=False, indent=2))
