from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from drawai.acp_agent_presets import ACP_AGENT_BY_PROVIDER_ID
from drawai.acp_agent import AcpAgentError, invoke_acp_agent_text
from drawai.codex_cli import resolve_codex_executable
from drawai.agent_cli_svg import AgentCliSvgError, invoke_agent_cli_text
from drawai.codex_python_sdk_svg import (
    CODEX_SESSION_LOG_DIRS,
    CODEX_SESSION_LOG_FILES,
    CODEX_RUNTIME_EVENT_TAIL_FILE,
    _archive_codex_session_logs,
    _codex_sdk_env,
    _isolated_codex_home,
    _load_openai_codex_sdk,
    _normalize_codex_model_name,
    _normalize_codex_reasoning_effort,
    _run_thread_with_timeout,
    _write_codex_runtime_log_tail,
    controlled_codex_config_overrides,
)
from drawai.tool_agent_runtime import (
    DEFAULT_TOOL_AGENT_MAX_ITERATIONS,
    DEFAULT_TOOL_AGENT_MAX_OUTPUT_TOKENS,
    DRAWAI_TOOL_AGENT_PROVIDER,
    DrawAIToolAgentError,
    invoke_drawai_tool_agent,
)

from .agents import (
    DEFAULT_AGENT_TIMEOUT_SECONDS,
    SVG_COMPOSE_GENERATOR_SCRIPT_OUTPUT_PATH,
    SVG_COMPOSE_GENERATOR_SCRIPT_REPO_PATH,
    AgentPrompt,
)


GENERIC_AGENT_CLI_PROVIDERS: dict[str, str] = {
    "claude_cli": "claude",
    "openclaw_cli": "openclaw",
    "hermes_cli": "hermes",
}
ACP_AGENT_PROVIDERS: dict[str, str] = {
    provider_id: preset.agent_id for provider_id, preset in ACP_AGENT_BY_PROVIDER_ID.items()
}
CODEX_FAST_SERVICE_TIER = "priority"


@dataclass(frozen=True)
class AgentExecutionRequest:
    prompt: AgentPrompt
    workdir: Path
    run_root: Path
    node_id: str
    node_type: str
    runtime_config: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AgentExecutionResult:
    provider_id: str
    prompt_path: Path
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    trace_path: Path | None = None
    session_log_path: Path | None = None
    execution_manifest_path: Path | None = None
    exit_code: int = 0


class AgentExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        prompt_path: Path | None = None,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        trace_path: Path | None = None,
        session_log_path: Path | None = None,
        execution_manifest_path: Path | None = None,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.prompt_path = prompt_path
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path
        self.trace_path = trace_path
        self.session_log_path = session_log_path
        self.execution_manifest_path = execution_manifest_path
        self.exit_code = exit_code


def execute_agent_prompt(request: AgentExecutionRequest) -> AgentExecutionResult:
    provider_id = request.prompt.provider_id
    request.workdir.mkdir(parents=True, exist_ok=True)
    _prepare_builtin_agent_scripts(request)
    prompt_path = request.workdir / "prompt.md"
    prompt_path.write_text(request.prompt.text, encoding="utf-8")
    _require_input_files(request)
    _validate_declared_output_paths(request)
    _write_execution_request_manifest(request, prompt_path)
    if provider_id == "codex_sdk":
        result = _execute_codex_sdk_agent(request, prompt_path=prompt_path)
    elif provider_id == "codex_cli":
        result = _execute_codex_cli_agent(request, prompt_path=prompt_path)
    elif provider_id == "kimi_cli":
        result = _execute_kimi_cli_agent(request, prompt_path=prompt_path)
    elif provider_id in ACP_AGENT_PROVIDERS:
        result = _execute_acp_agent(
            request,
            prompt_path=prompt_path,
            provider_id=provider_id,
            agent=ACP_AGENT_PROVIDERS[provider_id],
        )
    elif provider_id == DRAWAI_TOOL_AGENT_PROVIDER:
        result = _execute_drawai_tool_agent(request, prompt_path=prompt_path)
    elif provider_id in GENERIC_AGENT_CLI_PROVIDERS:
        result = _execute_generic_agent_cli_agent(
            request,
            prompt_path=prompt_path,
            provider_id=provider_id,
            agent=GENERIC_AGENT_CLI_PROVIDERS[provider_id],
        )
    else:
        raise AgentExecutionError(
            f"unsupported Agent provider: {provider_id}",
            prompt_path=prompt_path,
        )
    _require_declared_outputs(request)
    manifest_path = _write_execution_manifest(request, result)
    return AgentExecutionResult(
        provider_id=result.provider_id,
        prompt_path=result.prompt_path,
        stdout_path=result.stdout_path,
        stderr_path=result.stderr_path,
        trace_path=result.trace_path,
        session_log_path=result.session_log_path,
        execution_manifest_path=manifest_path,
        exit_code=result.exit_code,
    )


def _execute_codex_sdk_agent(
    request: AgentExecutionRequest,
    *,
    prompt_path: Path,
) -> AgentExecutionResult:
    sdk = _load_openai_codex_sdk()
    options = dict(request.prompt.options)
    model_name = _normalize_codex_model_name(options.get("model"))
    reasoning_effort = _codex_sdk_reasoning_effort(options.get("reasoning_effort"))
    service_tier = _codex_service_tier(options)
    timeout_seconds = _timeout_seconds(options)
    trace_path = request.workdir / "codex_sdk_trace.jsonl"
    stdout_path = request.workdir / "codex_sdk_final_response.txt"
    stderr_path = request.workdir / "codex_sdk_error.txt"
    session_log_path = request.workdir / "codex_session_log"
    started_at = time.monotonic()
    result: Any | None = None
    archive: Mapping[str, Any] | None = None
    try:
        with _isolated_codex_home(request.workdir) as prepared_codex_home:
            try:
                with sdk.Codex(
                    sdk.CodexConfig(
                        cwd=str(_agent_cwd(request)),
                        config_overrides=controlled_codex_config_overrides(),
                        env=_codex_sdk_env(prepared_codex_home.codex_home),
                    )
                ) as codex:
                    thread = codex.thread_start(
                        approval_mode=sdk.ApprovalMode.deny_all,
                        config={"model_reasoning_effort": reasoning_effort},
                        cwd=str(_agent_cwd(request)),
                        developer_instructions=_developer_instructions(request),
                        ephemeral=True,
                        model=model_name,
                        sandbox=sdk.Sandbox.full_access,
                        service_tier=service_tier,
                    )
                    codex_inputs: list[Any] = [sdk.TextInput(request.prompt.text)]
                    image_paths = _image_input_paths(request)
                    codex_inputs.extend(
                        sdk.LocalImageInput(path=str(path))
                        for path in image_paths
                    )
                    _append_trace(
                        trace_path,
                        {
                            "type": "agent_request",
                            "provider_id": "codex_sdk",
                            "node_id": request.node_id,
                            "cwd": str(_agent_cwd(request)),
                            "prompt_path": str(prompt_path),
                            "input_paths": [str(path) for path in _input_paths(request)],
                            "image_input_paths": [str(path) for path in image_paths],
                            "declared_outputs": list(request.prompt.outputs),
                            "model": model_name or "codex-default",
                            "reasoning_effort": reasoning_effort,
                            "service_tier": service_tier,
                            "timeout_seconds": timeout_seconds,
                        },
                    )
                    mirror_stop, mirror_thread = _start_codex_session_log_mirror(
                        prepared_codex_home.codex_home,
                        session_log_path,
                        task_name=f"drawai.workflow.agent.{request.node_id}.codex_sdk",
                    )
                    try:
                        result = _run_thread_with_timeout(
                            thread,
                            codex_inputs,
                            timeout_seconds=timeout_seconds,
                            approval_mode=sdk.ApprovalMode.deny_all,
                            cwd=str(_agent_cwd(request)),
                            effort=reasoning_effort,
                            model=model_name,
                            sandbox=sdk.Sandbox.full_access,
                            service_tier=service_tier,
                        )
                    finally:
                        _stop_codex_session_log_mirror(
                            mirror_stop,
                            mirror_thread,
                            prepared_codex_home.codex_home,
                            session_log_path,
                            task_name=f"drawai.workflow.agent.{request.node_id}.codex_sdk",
                        )
                    final_response = str(getattr(result, "final_response", "") or "")
                    stdout_path.write_text(final_response, encoding="utf-8")
            except Exception as exc:
                archive = _archive_codex_session_logs(
                    prepared_codex_home.codex_home,
                    session_log_path,
                    task_name=f"drawai.workflow.agent.{request.node_id}.codex_sdk",
                    sdk_turn_result=result,
                )
                _append_trace(
                    trace_path,
                    {
                        "type": "agent_error",
                        "provider_id": "codex_sdk",
                        "node_id": request.node_id,
                        "duration_ms": int((time.monotonic() - started_at) * 1000),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "session_log_archive": archive,
                        "output_paths": [
                            str(_declared_output_path(request, output))
                            for output in request.prompt.outputs
                        ],
                    },
                )
                raise
            archive = _archive_codex_session_logs(
                prepared_codex_home.codex_home,
                session_log_path,
                task_name=f"drawai.workflow.agent.{request.node_id}.codex_sdk",
                sdk_turn_result=result,
            )
    except Exception as exc:
        stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise AgentExecutionError(
            f"Codex SDK Agent run failed: {exc}",
            prompt_path=prompt_path,
            stdout_path=stdout_path if stdout_path.exists() else None,
            stderr_path=stderr_path,
            trace_path=trace_path if trace_path.exists() else None,
            session_log_path=session_log_path if session_log_path.exists() else None,
            exit_code=1,
        ) from exc
    _append_trace(
        trace_path,
        {
            "type": "agent_response",
            "provider_id": "codex_sdk",
            "node_id": request.node_id,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "session_log_archive": archive,
            "output_paths": [str(_declared_output_path(request, output)) for output in request.prompt.outputs],
        },
    )
    return AgentExecutionResult(
        provider_id="codex_sdk",
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path if stderr_path.exists() else None,
        trace_path=trace_path,
        session_log_path=session_log_path,
    )


def _execute_drawai_tool_agent(
    request: AgentExecutionRequest,
    *,
    prompt_path: Path,
) -> AgentExecutionResult:
    options = dict(request.prompt.options)
    trace_path = request.workdir / "drawai_tool_agent_trace.jsonl"
    stdout_path = request.workdir / "drawai_tool_agent_final_response.txt"
    stderr_path = request.workdir / "drawai_tool_agent_error.txt"
    runtime_config = _drawai_tool_agent_runtime_config(request)
    try:
        result = invoke_drawai_tool_agent(
            prompt=request.prompt.text,
            image_paths=_image_input_paths(request),
            task_name=f"drawai.workflow.agent.{request.node_id}.{DRAWAI_TOOL_AGENT_PROVIDER}",
            runtime_config=runtime_config,
            workspace_dir=_agent_cwd(request),
            repo_root=_repo_root(),
            trace_path=trace_path,
            max_output_tokens=int(options.get("max_output_tokens") or DEFAULT_TOOL_AGENT_MAX_OUTPUT_TOKENS),
            max_iterations=int(options.get("max_iterations") or DEFAULT_TOOL_AGENT_MAX_ITERATIONS),
        )
    except (DrawAIToolAgentError, OSError, ValueError) as exc:
        stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise AgentExecutionError(
            f"DrawAI tool Agent run failed: {exc}",
            prompt_path=prompt_path,
            stdout_path=stdout_path if stdout_path.exists() else None,
            stderr_path=stderr_path,
            trace_path=trace_path if trace_path.exists() else None,
            exit_code=1,
        ) from exc
    stdout_path.write_text(result.final_text, encoding="utf-8")
    return AgentExecutionResult(
        provider_id=DRAWAI_TOOL_AGENT_PROVIDER,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path if stderr_path.exists() else None,
        trace_path=trace_path,
        exit_code=0,
    )
def _execute_codex_cli_agent(
    request: AgentExecutionRequest,
    *,
    prompt_path: Path,
) -> AgentExecutionResult:
    executable = resolve_codex_executable()
    if executable is None:
        raise AgentExecutionError("codex executable was not found", prompt_path=prompt_path)
    options = dict(request.prompt.options)
    command = [
        str(executable),
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--disable",
        "plugins",
        "--json",
        "-C",
        str(_agent_cwd(request)),
        "-s",
        "danger-full-access",
        "-o",
        str(request.workdir / "codex_cli_last_message.txt"),
        *(_codex_image_args(request)),
        *(_codex_cli_config_args(options)),
    ]
    model = _normalize_codex_model_name(options.get("model"))
    if model is not None:
        command.extend(["-m", model])
    command.append("-")
    session_log_path = request.workdir / "codex_cli_session_log"
    with _isolated_codex_home(request.workdir) as prepared_codex_home:
        result = _execute_subprocess_agent(
            request,
            prompt_path=prompt_path,
            provider_id="codex_cli",
            command=command,
            stdout_name="codex_cli_events.jsonl",
            stderr_name="codex_cli_stderr.txt",
            env_overrides=_codex_cli_env(prepared_codex_home.codex_home),
        )
        archive = _archive_codex_session_logs(
            prepared_codex_home.codex_home,
            session_log_path,
            task_name=f"drawai.workflow.agent.{request.node_id}.codex_cli",
        )
        _append_trace(
            result.trace_path or (request.workdir / "codex_cli_trace.jsonl"),
            {
                "type": "session_log_archive",
                "provider_id": "codex_cli",
                "node_id": request.node_id,
                "archive": archive,
            },
        )
    return AgentExecutionResult(
        provider_id=result.provider_id,
        prompt_path=result.prompt_path,
        stdout_path=result.stdout_path,
        stderr_path=result.stderr_path,
        trace_path=result.trace_path,
        session_log_path=session_log_path,
        exit_code=result.exit_code,
    )


def _execute_kimi_cli_agent(
    request: AgentExecutionRequest,
    *,
    prompt_path: Path,
) -> AgentExecutionResult:
    options = dict(request.prompt.options)
    command = _agent_cli_command_option(options)
    if command:
        executable = command[0]
    else:
        executable = shutil.which("kimi")
        command = [executable] if executable else []
    if not executable:
        raise AgentExecutionError("kimi executable was not found", prompt_path=prompt_path)
    command = [
        *command,
        "--work-dir",
        str(_agent_cwd(request)),
        "--print",
        "--input-format",
        "text",
        "--output-format",
        "stream-json",
    ]
    skills_dir = request.workdir / "_isolated_kimi_skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    command.extend(["--skills-dir", str(skills_dir)])
    model = str(options.get("model") or "").strip()
    if model:
        command.extend(["--model", model])
    result = _execute_subprocess_agent(
        request,
        prompt_path=prompt_path,
        provider_id="kimi_cli",
        command=command,
        stdout_name="kimi_events.jsonl",
        stderr_name="kimi_stderr.txt",
    )
    export_path = request.workdir / "kimi_session.zip"
    export_command = [executable, "export", "--output", str(export_path), "--yes"]
    completed = subprocess.run(
        export_command,
        cwd=str(request.workdir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=120,
    )
    session_log_path = export_path if completed.returncode == 0 and export_path.is_file() else None
    return AgentExecutionResult(
        provider_id=result.provider_id,
        prompt_path=result.prompt_path,
        stdout_path=result.stdout_path,
        stderr_path=result.stderr_path,
        trace_path=result.trace_path,
        session_log_path=session_log_path,
        exit_code=result.exit_code,
    )


def _execute_generic_agent_cli_agent(
    request: AgentExecutionRequest,
    *,
    prompt_path: Path,
    provider_id: str,
    agent: str,
) -> AgentExecutionResult:
    options = dict(request.prompt.options)
    stdout_path = request.workdir / f"{provider_id}_stdout.txt"
    stderr_path = request.workdir / f"{provider_id}_stderr.txt"
    trace_path = request.workdir / f"{provider_id}_trace.jsonl"
    runtime_config: dict[str, Any] = {
        "provider": "agent-cli",
        "connection_id": agent,
        "model_name": str(options.get("model") or ""),
        "reasoning_effort": str(options.get("reasoning_effort") or ""),
        "fast": _fast_mode(options),
        "timeout_seconds": _timeout_seconds(options),
        "cli": {
            "agent": agent,
            "command": _agent_cli_command_option(options),
        },
    }
    try:
        stdout = invoke_agent_cli_text(
            image_paths=_image_input_paths(request),
            prompt=request.prompt.text,
            task_name=f"drawai.workflow.agent.{request.node_id}.{provider_id}",
            runtime_config=runtime_config,
            trace_path=trace_path,
            isolated_cwd=_agent_cwd(request),
        )
    except (AgentCliSvgError, OSError, subprocess.TimeoutExpired) as exc:
        stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise AgentExecutionError(
            f"{provider_id} Agent run failed: {exc}",
            prompt_path=prompt_path,
            stdout_path=stdout_path if stdout_path.exists() else None,
            stderr_path=stderr_path,
            trace_path=trace_path if trace_path.exists() else None,
            exit_code=1,
        ) from exc
    stdout_path.write_text(stdout, encoding="utf-8")
    return AgentExecutionResult(
        provider_id=provider_id,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path if stderr_path.exists() else None,
        trace_path=trace_path,
        exit_code=0,
    )


def _execute_acp_agent(
    request: AgentExecutionRequest,
    *,
    prompt_path: Path,
    provider_id: str,
    agent: str,
) -> AgentExecutionResult:
    options = dict(request.prompt.options)
    stdout_path = request.workdir / f"{provider_id}_final_response.txt"
    stderr_path = request.workdir / f"{provider_id}_error.txt"
    trace_path = request.workdir / f"{provider_id}_trace.jsonl"
    runtime_config: dict[str, Any] = {
        "provider": "acp-agent",
        "connection_id": agent,
        "model_name": str(options.get("model") or ""),
        "reasoning_effort": str(options.get("reasoning_effort") or ""),
        "fast": _fast_mode(options),
        "timeout_seconds": _timeout_seconds(options),
        "acp": {
            "agent": agent,
            "command": _acp_agent_command_option(options),
        },
    }
    try:
        stdout = invoke_acp_agent_text(
            image_paths=_image_input_paths(request),
            prompt=request.prompt.text,
            task_name=f"drawai.workflow.agent.{request.node_id}.{provider_id}",
            runtime_config=runtime_config,
            trace_path=trace_path,
            isolated_cwd=_agent_cwd(request),
            additional_roots=(_repo_root(),),
        )
    except (AcpAgentError, OSError, subprocess.TimeoutExpired) as exc:
        stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise AgentExecutionError(
            f"{provider_id} Agent run failed: {exc}",
            prompt_path=prompt_path,
            stdout_path=stdout_path if stdout_path.exists() else None,
            stderr_path=stderr_path,
            trace_path=trace_path if trace_path.exists() else None,
            exit_code=1,
        ) from exc
    stdout_path.write_text(stdout, encoding="utf-8")
    return AgentExecutionResult(
        provider_id=provider_id,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path if stderr_path.exists() else None,
        trace_path=trace_path,
        exit_code=0,
    )


def _execute_subprocess_agent(
    request: AgentExecutionRequest,
    *,
    prompt_path: Path,
    provider_id: str,
    command: Sequence[str],
    stdout_name: str,
    stderr_name: str,
    env_overrides: Mapping[str, str | None] | None = None,
) -> AgentExecutionResult:
    stdout_path = request.workdir / stdout_name
    stderr_path = request.workdir / stderr_name
    trace_path = request.workdir / f"{provider_id}_trace.jsonl"
    timeout_seconds = _timeout_seconds(request.prompt.options)
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("CODEX_"):
            env.pop(key, None)
    if env_overrides:
        for key, value in env_overrides.items():
            env_key = str(key)
            if value is None:
                env.pop(env_key, None)
            else:
                env[env_key] = str(value)
    started_at = time.monotonic()
    _append_trace(
        trace_path,
        {
            "type": "agent_request",
            "provider_id": provider_id,
            "node_id": request.node_id,
            "cwd": str(_agent_cwd(request)),
            "prompt_path": str(prompt_path),
            "command": _redact_command(command),
            "input_paths": [str(path) for path in _input_paths(request)],
            "declared_outputs": list(request.prompt.outputs),
            "timeout_seconds": timeout_seconds,
        },
    )
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            completed = subprocess.run(
                list(command),
                input=request.prompt.text,
                text=True,
                cwd=str(_agent_cwd(request)),
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=timeout_seconds,
                check=False,
            )
            returncode = completed.returncode
    except Exception as exc:
        _append_trace(
            trace_path,
            {
                "type": "agent_error",
                "provider_id": provider_id,
                "node_id": request.node_id,
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "output_paths": [str(_declared_output_path(request, output)) for output in request.prompt.outputs],
            },
        )
        raise AgentExecutionError(
            f"{provider_id} Agent run failed: {exc}",
            prompt_path=prompt_path,
            stdout_path=stdout_path if stdout_path.exists() else None,
            stderr_path=stderr_path if stderr_path.exists() else None,
            trace_path=trace_path if trace_path.exists() else None,
            exit_code=1,
        ) from exc
    _append_trace(
        trace_path,
        {
            "type": "agent_response",
            "provider_id": provider_id,
            "node_id": request.node_id,
            "returncode": returncode,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "output_paths": [str(_declared_output_path(request, output)) for output in request.prompt.outputs],
        },
    )
    if returncode != 0:
        stderr_tail = stderr_path.read_text(encoding="utf-8")[-2000:] if stderr_path.exists() else ""
        raise AgentExecutionError(
            f"{provider_id} Agent run failed with returncode={returncode}: {stderr_tail}",
            prompt_path=prompt_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            trace_path=trace_path,
            exit_code=returncode,
        )
    return AgentExecutionResult(
        provider_id=provider_id,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        trace_path=trace_path,
        exit_code=returncode,
    )
def _write_execution_manifest(
    request: AgentExecutionRequest,
    result: AgentExecutionResult,
) -> Path:
    path = request.workdir / "agent_execution.json"
    _write_json(
        path,
        {
            "schema": "drawai.workflow_agent_execution.v1",
            "node_id": request.node_id,
            "provider_id": result.provider_id,
            "cwd": str(_agent_cwd(request)),
            "node_workdir": str(request.workdir),
            "prompt_path": _relative_or_absolute(result.prompt_path, request.run_root),
            "stdout_path": _relative_or_absolute(result.stdout_path, request.run_root),
            "stderr_path": _relative_or_absolute(result.stderr_path, request.run_root),
            "trace_path": _relative_or_absolute(result.trace_path, request.run_root),
            "session_log_path": _relative_or_absolute(result.session_log_path, request.run_root),
            "declared_inputs": [dict(item) for item in request.prompt.inputs],
            "input_paths": [
                _relative_or_absolute(path, request.run_root)
                for path in _input_paths(request)
            ],
            "image_input_paths": [
                _relative_or_absolute(path, request.run_root)
                for path in _image_input_paths(request)
            ],
            "declared_outputs": list(request.prompt.outputs),
            "actual_outputs": [
                _relative_or_absolute(_declared_output_path(request, output), request.run_root)
                for output in request.prompt.outputs
            ],
            "exit_code": result.exit_code,
        },
    )
    return path


def _write_execution_request_manifest(
    request: AgentExecutionRequest,
    prompt_path: Path,
) -> Path:
    path = request.workdir / "agent_execution_request.json"
    _write_json(
        path,
        {
            "schema": "drawai.workflow_agent_execution_request.v1",
            "node_id": request.node_id,
            "node_type": request.node_type,
            "provider_id": request.prompt.provider_id,
            "cwd": str(_agent_cwd(request)),
            "node_workdir": str(request.workdir),
            "run_root": str(request.run_root),
            "prompt_path": _relative_or_absolute(prompt_path, request.run_root),
            "declared_inputs": [dict(item) for item in request.prompt.inputs],
            "input_paths": [
                _relative_or_absolute(path_item, request.run_root)
                for path_item in _input_paths(request)
            ],
            "image_input_paths": [
                _relative_or_absolute(path_item, request.run_root)
                for path_item in _image_input_paths(request)
            ],
            "declared_outputs": list(request.prompt.outputs),
            "options": _redact_sensitive_mapping(request.prompt.options),
        },
    )
    return path


def _require_declared_outputs(request: AgentExecutionRequest) -> None:
    missing: list[str] = []
    for output in request.prompt.outputs:
        output_path = _declared_output_path(request, output)
        if not output_path.is_file():
            missing.append(str(output_path))
    if missing:
        raise AgentExecutionError(
            "Agent did not write declared output files: " + ", ".join(missing),
            prompt_path=request.workdir / "prompt.md",
        )


def _require_input_files(request: AgentExecutionRequest) -> None:
    missing: list[str] = []
    for path in _input_paths(request):
        if not path.is_file():
            missing.append(str(path))
    if missing:
        raise AgentExecutionError(
            "Agent input files do not exist: " + ", ".join(missing),
            prompt_path=request.workdir / "prompt.md",
        )


def _validate_declared_output_paths(request: AgentExecutionRequest) -> None:
    for output in request.prompt.outputs:
        _declared_output_path(request, output)


def _declared_output_path(
    request: AgentExecutionRequest,
    output: Mapping[str, Any],
) -> Path:
    raw_path = output.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise AgentExecutionError(
            "Agent declared output path must be a non-empty string",
            prompt_path=request.workdir / "prompt.md",
        )
    path = Path(raw_path)
    if path.is_absolute():
        raise AgentExecutionError(
            f"Agent declared output path must be relative to node workdir: {raw_path}",
            prompt_path=request.workdir / "prompt.md",
        )
    resolved = (request.workdir / path).resolve(strict=False)
    try:
        resolved.relative_to(request.workdir.resolve(strict=False))
    except ValueError as exc:
        raise AgentExecutionError(
            f"Agent declared output path escapes node workdir: {raw_path}",
            prompt_path=request.workdir / "prompt.md",
        ) from exc
    return resolved


def _developer_instructions(request: AgentExecutionRequest) -> str:
    return (
        "You are a DrawAI file-backed Agent node. Run inside the workflow run root, "
        "read only the connected input files, built-in script files, and DrawAI tools declared by the prompt, and write "
        "the declared output files exactly. You may also write prompt-requested auxiliary render/report/log files inside "
        "the current node output directory. The repository root is provided only so command prefixes are executable; "
        "do not inspect, import, or call DrawAI repository source code unless a concrete built-in script file is declared "
        "as an input. For DrawAI-specific behavior, use the declared CLI tools and their help/format contracts. Do not use "
        "web search, external apps, hooks, memories, or multi-agent delegation."
    )


def _start_codex_session_log_mirror(
    codex_home: Path,
    archive_dir: Path,
    *,
    task_name: str,
) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()

    def _mirror_loop() -> None:
        while not stop_event.is_set():
            try:
                _copy_codex_session_log_snapshot(codex_home, archive_dir, task_name=task_name)
            except OSError:
                pass
            stop_event.wait(2.0)

    thread = threading.Thread(
        target=_mirror_loop,
        name=f"drawai-session-log-mirror-{archive_dir.parent.name}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _stop_codex_session_log_mirror(
    stop_event: threading.Event,
    thread: threading.Thread,
    codex_home: Path,
    archive_dir: Path,
    *,
    task_name: str,
) -> None:
    stop_event.set()
    thread.join(timeout=5.0)
    try:
        _copy_codex_session_log_snapshot(codex_home, archive_dir, task_name=task_name)
    except OSError:
        pass


def _copy_codex_session_log_snapshot(
    codex_home: Path,
    archive_dir: Path,
    *,
    task_name: str,
) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    missing: list[str] = []
    errors: list[str] = []
    for name in CODEX_SESSION_LOG_DIRS:
        source = codex_home / name
        destination = archive_dir / name
        if not source.exists():
            missing.append(name)
            continue
        try:
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            elif source.is_file():
                shutil.copy2(source, destination)
            copied.append(name)
        except OSError as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    for name in CODEX_SESSION_LOG_FILES:
        source = codex_home / name
        if not source.exists() or not source.is_file():
            missing.append(name)
            continue
        try:
            shutil.copy2(source, archive_dir / name)
            copied.append(name)
        except OSError as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    runtime_tail = _write_codex_runtime_log_tail(
        codex_home / "logs_2.sqlite",
        archive_dir / CODEX_RUNTIME_EVENT_TAIL_FILE,
    )
    if runtime_tail.get("status") == "ok":
        copied.append(CODEX_RUNTIME_EVENT_TAIL_FILE)
    _write_json(
        archive_dir / "live_manifest.json",
        {
            "schema": "drawai.codex_session_log_live_snapshot.v1",
            "task_name": task_name,
            "codex_home": str(codex_home),
            "archive_dir": str(archive_dir),
            "copied": copied,
            "missing": missing,
            "errors": errors,
            "runtime_event_tail": runtime_tail,
            "updated_at": time.time(),
        },
    )


def _agent_cwd(request: AgentExecutionRequest) -> Path:
    return request.run_root.expanduser().resolve(strict=False)


def _prepare_builtin_agent_scripts(request: AgentExecutionRequest) -> None:
    if request.prompt.preset_id != "svg_generation":
        return
    if not _prompt_items_include_type(request.prompt.inputs, "page_spec"):
        return
    semantic_output = _first_prompt_item_by_type(request.prompt.outputs, "semantic_svg")
    if semantic_output is None:
        return

    source = _repo_root() / SVG_COMPOSE_GENERATOR_SCRIPT_REPO_PATH
    target = request.workdir / SVG_COMPOSE_GENERATOR_SCRIPT_OUTPUT_PATH
    declared_run_root_path = _run_root_relative_path(
        request,
        request.workdir / str(semantic_output["path"]),
    )

    template = source.read_text(encoding="utf-8")
    assignment = 'DECLARED_FINAL_SVG_RUN_ROOT_PATH = "__DRAWAI_DECLARED_FINAL_SVG_RUN_ROOT_PATH__"'
    replacement = f"DECLARED_FINAL_SVG_RUN_ROOT_PATH = {json.dumps(declared_run_root_path)}"
    if assignment not in template:
        raise AgentExecutionError(f"SVG compose generator template missing path marker: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.replace(assignment, replacement), encoding="utf-8")


def _prompt_items_include_type(items: Sequence[Mapping[str, Any]], type_name: str) -> bool:
    return _first_prompt_item_by_type(items, type_name) is not None


def _first_prompt_item_by_type(
    items: Sequence[Mapping[str, Any]],
    type_name: str,
) -> Mapping[str, Any] | None:
    for item in items:
        if item.get("type") == type_name and isinstance(item.get("path"), str) and item["path"]:
            return item
    return None


def _run_root_relative_path(request: AgentExecutionRequest, path: Path) -> str:
    run_root = request.run_root.expanduser().resolve(strict=False)
    path_abs = path.expanduser().resolve(strict=False)
    return os.path.relpath(path_abs, run_root).replace(os.sep, "/")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _drawai_tool_agent_runtime_config(request: AgentExecutionRequest) -> dict[str, Any]:
    runtime = dict(request.runtime_config or {})
    runtime["provider"] = str(runtime.get("provider") or DRAWAI_TOOL_AGENT_PROVIDER)
    runtime["connection_id"] = str(runtime.get("connection_id") or DRAWAI_TOOL_AGENT_PROVIDER)
    runtime["wire_api"] = str(runtime.get("wire_api") or "chat_completions")
    options = dict(request.prompt.options)
    model = options.get("model")
    if model:
        runtime["model_name"] = str(model)
    for key in ("base_url", "api_key", "api_key_env", "timeout_seconds", "wire_api", "extra_body"):
        value = options.get(key)
        if value not in (None, ""):
            runtime[key] = value
    return runtime


def _timeout_seconds(options: Mapping[str, Any]) -> float:
    raw = options.get("timeout_seconds", DEFAULT_AGENT_TIMEOUT_SECONDS)
    timeout = float(raw)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be positive")
    return timeout


def _input_paths(request: AgentExecutionRequest) -> tuple[Path, ...]:
    paths: list[Path] = []
    for item in request.prompt.inputs:
        path = item.get("path")
        if isinstance(path, str) and path:
            path_obj = Path(path)
            paths.append(path_obj if path_obj.is_absolute() else request.run_root / path_obj)
    return tuple(paths)


def _image_input_paths(request: AgentExecutionRequest) -> tuple[Path, ...]:
    return tuple(
        path
        for path, item in zip(_input_paths(request), request.prompt.inputs, strict=False)
        if str(item.get("type") or "") == "image" and path.is_file()
    )


def _codex_image_args(request: AgentExecutionRequest) -> list[str]:
    args: list[str] = []
    for image_path in _image_input_paths(request):
        args.extend(["-i", str(image_path)])
    return args


def _codex_cli_config_args(options: Mapping[str, Any]) -> list[str]:
    raw_effort = options.get("reasoning_effort")
    reasoning_effort = _normalize_codex_reasoning_effort(raw_effort)
    overrides = [f'model_reasoning_effort="{reasoning_effort}"']
    if _fast_mode(options):
        overrides.append(f'service_tier="{CODEX_FAST_SERVICE_TIER}"')
    args: list[str] = []
    for override in controlled_codex_config_overrides(overrides):
        args.extend(["-c", override])
    return args


def _agent_cli_command_option(options: Mapping[str, Any]) -> list[str]:
    raw = options.get("agent_cli_command")
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, Sequence):
        command = [str(item) for item in raw if str(item)]
        if command:
            return command
    raise ValueError("agent_cli_command must be a string or non-empty list")


def _acp_agent_command_option(options: Mapping[str, Any]) -> list[str]:
    raw = options.get("acp_agent_command")
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, Sequence):
        command = [str(item) for item in raw if str(item)]
        if command:
            return command
    raise ValueError("acp_agent_command must be a string or non-empty list")


def _codex_cli_env(codex_home: Path) -> dict[str, str | None]:
    env: dict[str, str | None] = {
        key: None for key in os.environ if key.startswith("CODEX_")
    }
    env["CODEX_HOME"] = str(codex_home)
    env["HOME"] = str(codex_home.parent)
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if openai_api_key:
        env["OPENAI_API_KEY"] = openai_api_key
    return env


def _codex_sdk_reasoning_effort(value: Any) -> str:
    reasoning_effort = _normalize_codex_reasoning_effort(value)
    if reasoning_effort == "minimal":
        return "low"
    return reasoning_effort


def _codex_service_tier(options: Mapping[str, Any]) -> str | None:
    return CODEX_FAST_SERVICE_TIER if _fast_mode(options) else None


def _fast_mode(options: Mapping[str, Any]) -> bool:
    raw = options.get("fast")
    if raw in (None, ""):
        return False
    if isinstance(raw, bool):
        return raw
    raise ValueError("fast must be a boolean")


def _append_trace(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _redact_sensitive_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        normalized = key_text.lower().replace("-", "_")
        redacted[key_text] = "[redacted]" if "api_key" in normalized else item
    return redacted


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative_or_absolute(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    resolved = path.expanduser().resolve(strict=False)
    try:
        return resolved.relative_to(root.expanduser().resolve(strict=False)).as_posix()
    except ValueError:
        return str(resolved)


def _redact_command(command: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            redacted.append(item)
            skip_next = False
            continue
        redacted.append(str(item))
        if item in {"-i", "-C", "-o", "-m", "-s", "-c", "--model", "--work-dir", "--output"}:
            skip_next = True
    return redacted
