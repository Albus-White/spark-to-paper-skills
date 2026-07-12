from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .agent_execution import AgentExecutionRequest, execute_agent_prompt
from .agents import agent_preset_by_id, default_agent_provider_registry, render_agent_prompt
from .templates import (
    copy_builtin_template_to_workspace,
    list_workflow_templates,
    load_workflow_template,
    load_workflow_template_by_id,
)
from .validation import validate_workflow_template
from drawai.tooling import resolve_drawai_tool_command_prefix


def workflow_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage DrawAI workflow DAG templates and runs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    templates = subparsers.add_parser("templates", help="List built-in and local workflow templates.")
    templates.add_argument("--workspace", type=Path, default=Path("."), help="Workspace containing .drawai/workflows.")

    copy_template = subparsers.add_parser("copy-template", help="Copy a built-in workflow template into the workspace.")
    copy_template.add_argument("template_id", help="Built-in template id to copy.")
    copy_template.add_argument("--name", required=True, help="Name for the editable local template.")
    copy_template.add_argument("--workspace", type=Path, default=Path("."), help="Workspace containing .drawai/workflows.")
    copy_template.add_argument("--no-overwrite", action="store_true", help="Fail if the target template already exists.")

    validate = subparsers.add_parser("validate", help="Validate a workflow template.")
    validate.add_argument("path", nargs="?", type=Path, help="Workflow template JSON path.")
    validate.add_argument("--template", help="Template id to load from built-ins or the workspace.")
    validate.add_argument("--workspace", type=Path, default=Path("."), help="Workspace containing .drawai/workflows.")

    providers = subparsers.add_parser("providers", help="List Agent providers.")
    providers.set_defaults(command="providers")

    prompt = subparsers.add_parser("prompt", help="Render an Agent node prompt preview.")
    prompt.add_argument("preset_id", help="Agent preset id.")
    prompt.add_argument("--input-manifest", type=Path, help="input_manifest.json from a node run.")
    prompt.add_argument("--config", type=Path, help="Agent node config JSON.")
    prompt.add_argument("--provider", help="Provider override, for example codex_sdk or kimi_cli.")

    inspect = subparsers.add_parser("inspect-node-run", help="Inspect the latest or selected node_run.json.")
    inspect.add_argument("run_root", type=Path, help="Workflow run root.")
    inspect.add_argument("node_id", help="Node id.")
    inspect.add_argument("--attempt", help="Attempt id. Defaults to the latest numeric run.")

    run_agent = subparsers.add_parser("run-agent", help="Run one file-backed Agent node.")
    run_agent.add_argument("preset_id", help="Agent preset id.")
    run_agent.add_argument("--run-root", type=Path, required=True, help="Workflow run root used to resolve relative input paths.")
    run_agent.add_argument("--workdir", type=Path, required=True, help="Agent node work directory. Prompt, logs, and outputs are written here.")
    run_agent.add_argument("--input-manifest", type=Path, required=True, help="JSON file with an inputs array used to render the prompt.")
    run_agent.add_argument("--config", type=Path, help="Agent node config JSON.")
    run_agent.add_argument("--provider", help="Provider override, for example codex_sdk, codex_cli, or kimi_cli.")
    run_agent.add_argument("--node-id", default="agent", help="Node id for prompt/log metadata.")

    args = parser.parse_args(argv)
    try:
        if args.command == "templates":
            return _templates_command(args)
        if args.command == "copy-template":
            return _copy_template_command(args)
        if args.command == "validate":
            return _validate_command(args)
        if args.command == "providers":
            return _providers_command()
        if args.command == "prompt":
            return _prompt_command(args)
        if args.command == "inspect-node-run":
            return _inspect_node_run_command(args)
        if args.command == "run-agent":
            return _run_agent_command(args)
    except Exception as exc:  # CLI boundary.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"Unsupported workflow command: {args.command}")


def _templates_command(args: argparse.Namespace) -> int:
    _print_json(
        {
            "templates": [
                template.to_dict()
                for template in list_workflow_templates(args.workspace)
            ],
        }
    )
    return 0


def _copy_template_command(args: argparse.Namespace) -> int:
    template = copy_builtin_template_to_workspace(
        args.workspace,
        args.template_id,
        name=args.name,
        overwrite=not args.no_overwrite,
    )
    _print_json({"template": template.to_dict()})
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    if args.template and args.path:
        raise ValueError("use either --template or path, not both")
    if args.template:
        template = load_workflow_template_by_id(args.workspace, args.template)
    elif args.path:
        template = load_workflow_template(args.path)
    else:
        raise ValueError("validate requires --template or a JSON path")
    result = validate_workflow_template(template)
    _print_json(result.to_dict())
    return 0 if result.ok else 1


def _providers_command() -> int:
    _print_json(
        {
            "providers": [
                provider.to_dict()
                for provider in default_agent_provider_registry().values()
            ],
        }
    )
    return 0


def _prompt_command(args: argparse.Namespace) -> int:
    config = _read_json_object(args.config) if args.config else {}
    if args.provider:
        config["provider_id"] = args.provider
    manifest = _read_json_object(args.input_manifest) if args.input_manifest else {"inputs": []}
    inputs = manifest.get("inputs", [])
    if not isinstance(inputs, list):
        raise ValueError("input manifest inputs must be an array")
    prompt = render_agent_prompt(
        agent_preset_by_id(args.preset_id),
        inputs=tuple(item for item in inputs if isinstance(item, dict)),
        node_config=config,
    )
    _print_json(prompt.to_dict())
    return 0


def _run_agent_command(args: argparse.Namespace) -> int:
    run_root = args.run_root.expanduser().resolve(strict=False)
    workdir = args.workdir.expanduser().resolve(strict=False)
    config = _read_json_object(args.config) if args.config else {}
    if args.provider:
        config["provider_id"] = args.provider
    config["node_id"] = args.node_id
    manifest = _read_json_object(args.input_manifest)
    inputs = manifest.get("inputs", [])
    if not isinstance(inputs, list):
        raise ValueError("input manifest inputs must be an array")
    workdir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[3]
    prompt = render_agent_prompt(
        agent_preset_by_id(args.preset_id),
        inputs=tuple(item for item in inputs if isinstance(item, dict)),
        node_config=config,
        runtime_context={
            "workflow_run_root": run_root,
            "node_workdir": workdir,
            "agent_cwd": run_root,
            "repo_root": repo_root,
            "attempt_id": workdir.name,
            "drawai_tool_command_prefix": resolve_drawai_tool_command_prefix(repo_root, cwd=run_root),
        },
    )
    result = execute_agent_prompt(
        AgentExecutionRequest(
            prompt=prompt,
            workdir=workdir,
            run_root=run_root,
            node_id=args.node_id,
            node_type="agent",
        )
    )
    _print_json(
        {
            "provider_id": result.provider_id,
            "prompt_path": _relative_or_absolute(result.prompt_path, run_root),
            "stdout_path": _relative_or_absolute(result.stdout_path, run_root),
            "stderr_path": _relative_or_absolute(result.stderr_path, run_root),
            "trace_path": _relative_or_absolute(result.trace_path, run_root),
            "session_log_path": _relative_or_absolute(result.session_log_path, run_root),
            "execution_manifest_path": _relative_or_absolute(result.execution_manifest_path, run_root),
            "exit_code": result.exit_code,
        }
    )
    return 0


def _inspect_node_run_command(args: argparse.Namespace) -> int:
    run_root = args.run_root.expanduser().resolve(strict=False)
    runs_dir = run_root / "nodes" / args.node_id / "runs"
    attempt = args.attempt or _latest_attempt_id(runs_dir)
    payload = _read_json_object(runs_dir / attempt / "node_run.json")
    _print_json(payload)
    return 0


def _latest_attempt_id(runs_dir: Path) -> str:
    if not runs_dir.is_dir():
        raise FileNotFoundError(f"node runs directory not found: {runs_dir}")
    attempts = sorted(path.name for path in runs_dir.iterdir() if path.is_dir() and path.name.isdigit())
    if not attempts:
        raise FileNotFoundError(f"node run attempts not found: {runs_dir}")
    return attempts[-1]


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _relative_or_absolute(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    resolved = path.expanduser().resolve(strict=False)
    try:
        return resolved.relative_to(root.expanduser().resolve(strict=False)).as_posix()
    except ValueError:
        return str(resolved)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
