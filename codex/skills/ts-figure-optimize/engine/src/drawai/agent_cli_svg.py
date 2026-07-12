from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import model_runtime


AGENT_CLI_RUNNER = "agent_cli"
SUPPORTED_AGENT_CLI_AGENTS = frozenset({"kimi", "claude", "codex", "openclaw", "hermes", "custom"})
CODEX_FAST_SERVICE_TIER = "priority"


class AgentCliSvgError(RuntimeError):
    """Raised when a direct agent CLI cannot complete a DrawAI task."""


class AgentCliSvgSession:
    """Thin adapter around file-editing agent CLIs such as Kimi, Claude, or Codex."""

    def __init__(
        self,
        *,
        runtime_config: Mapping[str, Any] | None = None,
        trace_path: str | Path | None = None,
        isolated_cwd: str | Path | None = None,
    ) -> None:
        self.runtime_config = dict(runtime_config or {})
        self.trace_path = Path(trace_path) if trace_path is not None else None
        self.isolated_cwd = Path(isolated_cwd or Path.cwd()).expanduser().resolve(strict=False)
        self.timeout_seconds = model_runtime._runtime_timeout_seconds(self.runtime_config)
        self.agent = _agent_cli_agent(self.runtime_config)

    def invoke(
        self,
        *,
        image_paths: str | Path | Sequence[str | Path],
        prompt: str,
        task_name: str,
        output_svg_path: str | Path | None = None,
        output_response_path: str | Path | None = None,
    ) -> str:
        normalized_images = _normalize_image_paths(image_paths)
        svg_path = (
            _normalize_workspace_output_path(output_svg_path, self.isolated_cwd)
            if output_svg_path is not None
            else None
        )
        response_path = (
            _normalize_workspace_output_path(output_response_path, self.isolated_cwd)
            if output_response_path is not None
            else None
        )
        if svg_path is not None:
            svg_path.parent.mkdir(parents=True, exist_ok=True)
            if svg_path.exists():
                svg_path.unlink()
        if response_path is not None:
            response_path.parent.mkdir(parents=True, exist_ok=True)
            if response_path.exists():
                response_path.unlink()

        controlled_prompt = _controlled_prompt(
            prompt,
            agent=self.agent,
            workspace_dir=self.isolated_cwd,
            image_paths=normalized_images,
            output_svg_path=svg_path,
            output_response_path=response_path,
        )
        result = self._run(
            image_paths=normalized_images,
            prompt=controlled_prompt,
            task_name=task_name,
        )
        if response_path is not None and not response_path.exists():
            response_path.write_text(result.stdout.strip() + "\n", encoding="utf-8")
        if svg_path is not None:
            if svg_path.exists():
                svg_text = _read_output_svg_file(svg_path)
                source = "output_svg_path"
            else:
                svg_text = _svg_from_text(result.stdout)
                svg_path.write_text(svg_text, encoding="utf-8")
                source = "stdout"
        else:
            svg_text = _svg_from_text(result.stdout)
            source = "stdout"
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "agent_cli_response",
                "runner": AGENT_CLI_RUNNER,
                "agent": self.agent,
                "task_name": task_name,
                "returncode": result.returncode,
                "duration_ms": result.duration_ms,
                "stdout_chars": len(result.stdout),
                "stderr_chars": len(result.stderr),
                "source": source,
                "output_svg_path": str(svg_path) if svg_path is not None else None,
                "output_response_path": str(response_path) if response_path is not None else None,
            },
        )
        return svg_text

    def invoke_text(
        self,
        *,
        image_paths: str | Path | Sequence[str | Path],
        prompt: str,
        task_name: str,
    ) -> str:
        normalized_images = _normalize_image_paths(image_paths)
        controlled_prompt = _controlled_prompt(
            prompt,
            agent=self.agent,
            workspace_dir=self.isolated_cwd,
            image_paths=normalized_images,
        )
        result = self._run(
            image_paths=normalized_images,
            prompt=controlled_prompt,
            task_name=task_name,
        )
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "agent_cli_text_response",
                "runner": AGENT_CLI_RUNNER,
                "agent": self.agent,
                "task_name": task_name,
                "returncode": result.returncode,
                "duration_ms": result.duration_ms,
                "stdout_chars": len(result.stdout),
                "stderr_chars": len(result.stderr),
            },
        )
        return result.stdout

    def _run(
        self,
        *,
        image_paths: Sequence[Path],
        prompt: str,
        task_name: str,
    ) -> "_AgentCliResult":
        invocation = _agent_cli_invocation(
            self.runtime_config,
            work_dir=self.isolated_cwd,
            image_paths=image_paths,
            prompt=prompt,
        )
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "agent_cli_request",
                "runner": AGENT_CLI_RUNNER,
                "agent": self.agent,
                "task_name": task_name,
                "command": _trace_command(invocation.command, prompt),
                "cwd": str(self.isolated_cwd),
                "timeout_seconds": self.timeout_seconds,
                "prompt_chars": len(prompt),
                "stdin_chars": len(invocation.stdin or ""),
                "image_paths": [str(path) for path in image_paths],
            },
        )
        started_at = time.monotonic()
        try:
            completed = subprocess.run(
                invocation.command,
                input=invocation.stdin,
                cwd=self.isolated_cwd,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            model_runtime._append_trace(
                self.trace_path,
                {
                    "type": "agent_cli_error",
                    "runner": AGENT_CLI_RUNNER,
                    "agent": self.agent,
                    "task_name": task_name,
                    "duration_ms": duration_ms,
                    "error_type": "TimeoutExpired",
                    "error": f"Agent CLI exceeded timeout_seconds={self.timeout_seconds:g}",
                    "stdout_tail": _tail(exc.stdout),
                    "stderr_tail": _tail(exc.stderr),
                },
            )
            raise AgentCliSvgError(f"Agent CLI exceeded timeout_seconds={self.timeout_seconds:g}") from exc

        duration_ms = int((time.monotonic() - started_at) * 1000)
        result = _AgentCliResult(
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            returncode=completed.returncode,
            duration_ms=duration_ms,
        )
        if completed.returncode != 0:
            model_runtime._append_trace(
                self.trace_path,
                {
                    "type": "agent_cli_error",
                    "runner": AGENT_CLI_RUNNER,
                    "agent": self.agent,
                    "task_name": task_name,
                    "duration_ms": duration_ms,
                    "returncode": completed.returncode,
                    "stdout_tail": _tail(result.stdout),
                    "stderr_tail": _tail(result.stderr),
                },
            )
            raise AgentCliSvgError(
                f"Agent CLI failed with returncode={completed.returncode}. "
                f"stderr tail: {_tail(result.stderr)}"
            )
        return result


class _AgentCliResult:
    def __init__(self, *, stdout: str, stderr: str, returncode: int, duration_ms: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.duration_ms = duration_ms


class _AgentCliInvocation:
    def __init__(self, *, command: list[str], stdin: str | None) -> None:
        self.command = command
        self.stdin = stdin


def invoke_agent_cli_svg_text(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: Mapping[str, Any] | None = None,
    trace_path: str | Path | None = None,
    isolated_cwd: str | Path | None = None,
    output_svg_path: str | Path | None = None,
    output_response_path: str | Path | None = None,
) -> str:
    session = AgentCliSvgSession(
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=isolated_cwd,
    )
    return session.invoke(
        image_paths=image_paths,
        prompt=prompt,
        task_name=task_name,
        output_svg_path=output_svg_path,
        output_response_path=output_response_path,
    )


def invoke_agent_cli_text(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: Mapping[str, Any] | None = None,
    trace_path: str | Path | None = None,
    isolated_cwd: str | Path | None = None,
) -> str:
    session = AgentCliSvgSession(
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=isolated_cwd,
    )
    return session.invoke_text(
        image_paths=image_paths,
        prompt=prompt,
        task_name=task_name,
    )


def _agent_cli_command(
    runtime_config: Mapping[str, Any],
    *,
    work_dir: Path,
    image_paths: Sequence[Path] = (),
) -> list[str]:
    return _agent_cli_invocation(
        runtime_config,
        work_dir=work_dir,
        image_paths=image_paths,
        prompt="",
    ).command


def _agent_cli_invocation(
    runtime_config: Mapping[str, Any],
    *,
    work_dir: Path,
    image_paths: Sequence[Path] = (),
    prompt: str,
) -> _AgentCliInvocation:
    agent = _agent_cli_agent(runtime_config)
    raw = _agent_cli_command_raw(runtime_config, agent)
    command = _parse_command(raw)
    model_name = str(runtime_config.get("model_name") or "").strip()
    fast = _runtime_fast(runtime_config)
    if agent == "kimi":
        return _kimi_invocation(command, model_name=model_name, prompt=prompt)
    if agent == "claude":
        return _AgentCliInvocation(command=_claude_command(command, model_name=model_name, fast=fast), stdin=prompt)
    if agent == "codex":
        return _AgentCliInvocation(
            command=_codex_command(command, model_name=model_name, work_dir=work_dir, image_paths=image_paths, fast=fast),
            stdin=prompt,
        )
    if agent == "openclaw":
        return _AgentCliInvocation(
            command=_openclaw_command(command, runtime_config=runtime_config, prompt=prompt),
            stdin=None,
        )
    if agent == "hermes":
        return _AgentCliInvocation(
            command=_hermes_command(command, model_name=model_name, image_paths=image_paths, prompt=prompt),
            stdin=None,
        )
    return _AgentCliInvocation(command=command, stdin=prompt)


def _agent_cli_agent(runtime_config: Mapping[str, Any]) -> str:
    cli = runtime_config.get("cli")
    agent = ""
    if isinstance(cli, Mapping):
        agent = str(cli.get("agent") or "").strip().lower()
    if not agent:
        provider = str(runtime_config.get("provider") or "").strip().lower()
        connection_id = str(runtime_config.get("connection_id") or "").strip().lower()
        if provider in {"kimi-cli"} or connection_id in {"kimi", "kimi-cli"}:
            agent = "kimi"
        elif provider in {"claude-cli"} or connection_id in {"claude", "claude-cli"}:
            agent = "claude"
        elif provider in {"codex-cli"} or connection_id in {"codex", "codex-cli"}:
            agent = "codex"
        elif provider in {"openclaw-cli"} or connection_id in {"openclaw", "openclaw-cli"}:
            agent = "openclaw"
        elif provider in {"hermes-cli"} or connection_id in {"hermes", "hermes-cli"}:
            agent = "hermes"
        else:
            agent = "kimi"
    if agent not in SUPPORTED_AGENT_CLI_AGENTS:
        supported = ", ".join(sorted(SUPPORTED_AGENT_CLI_AGENTS))
        raise AgentCliSvgError(f"Unsupported agent CLI preset: {agent!r}. Expected one of: {supported}")
    return agent


def _agent_cli_command_raw(runtime_config: Mapping[str, Any], agent: str) -> Any:
    cli = runtime_config.get("cli")
    if isinstance(cli, Mapping) and cli.get("command"):
        return cli.get("command")
    env_command = os.environ.get("DRAWAI_AGENT_CLI_COMMAND")
    if env_command:
        return env_command
    if agent == "kimi":
        return ("kimi",)
    if agent == "claude":
        return ("claude",)
    if agent == "codex":
        return ("codex", "exec")
    if agent == "openclaw":
        return ("openclaw", "agent")
    if agent == "hermes":
        return ("hermes", "chat")
    raise AgentCliSvgError("model_runtime.cli.command is required for custom agent CLI")


def _parse_command(raw: Any) -> list[str]:
    if isinstance(raw, str):
        command = shlex.split(raw)
    elif isinstance(raw, Sequence):
        command = [str(item) for item in raw]
    else:
        raise AgentCliSvgError("runtime_config.cli.command must be a string or list of strings")
    if not command:
        raise AgentCliSvgError("runtime_config.cli.command must not be empty")
    return command


def _kimi_invocation(command: list[str], *, model_name: str, prompt: str) -> _AgentCliInvocation:
    if model_name and "--model" not in command and "-m" not in command:
        command.extend(["--model", model_name])
    if "--output-format" not in command:
        command.extend(["--output-format", "text"])
    if not _has_any_flag(command, ("--prompt", "-p")):
        command.extend(["--prompt", prompt])
    return _AgentCliInvocation(command=command, stdin=None)


def _claude_command(command: list[str], *, model_name: str, fast: bool = False) -> list[str]:
    if model_name and "--model" not in command:
        command.extend(["--model", model_name])
    if fast and "--bare" not in command:
        command.append("--bare")
    if "--print" not in command and "-p" not in command:
        command.append("--print")
    if "--permission-mode" not in command and "--dangerously-skip-permissions" not in command:
        command.extend(["--permission-mode", "bypassPermissions"])
    if "--output-format" not in command:
        command.extend(["--output-format", "text"])
    if "--input-format" not in command:
        command.extend(["--input-format", "text"])
    return command


def _codex_command(
    command: list[str],
    *,
    model_name: str,
    work_dir: Path,
    image_paths: Sequence[Path],
    fast: bool = False,
) -> list[str]:
    if model_name and "--model" not in command and "-m" not in command:
        command.extend(["--model", model_name])
    if "--cd" not in command and "-C" not in command:
        command.extend(["--cd", str(work_dir)])
    if "--skip-git-repo-check" not in command:
        command.append("--skip-git-repo-check")
    if "--dangerously-bypass-approvals-and-sandbox" not in command and "--sandbox" not in command:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    if "--color" not in command:
        command.extend(["--color", "never"])
    if fast and not _has_codex_service_tier(command):
        command.extend(["-c", f'service_tier="{CODEX_FAST_SERVICE_TIER}"'])
    for image_path in image_paths:
        command.extend(["-i", str(image_path)])
    if "-" not in command:
        command.append("-")
    return command


def _openclaw_command(command: list[str], *, runtime_config: Mapping[str, Any], prompt: str) -> list[str]:
    _ensure_subcommand(command, "agent")
    if "--local" not in command:
        command.append("--local")
    if not _has_any_flag(command, ("--agent", "--session-id", "--to", "-t")):
        command.extend(["--agent", "main"])
    if not _has_any_flag(command, ("--message", "-m")):
        command.extend(["--message", prompt])
    if "--json" not in command:
        command.append("--json")
    if "--timeout" not in command:
        timeout_seconds = model_runtime._runtime_timeout_seconds(runtime_config)
        command.extend(["--timeout", _format_timeout_seconds(timeout_seconds)])
    if "--thinking" not in command:
        thinking = _openclaw_thinking_level(runtime_config.get("reasoning_effort"))
        if thinking:
            command.extend(["--thinking", thinking])
    return command


def _hermes_command(
    command: list[str],
    *,
    model_name: str,
    image_paths: Sequence[Path],
    prompt: str,
) -> list[str]:
    _ensure_subcommand(command, "chat")
    if model_name and not _has_any_flag(command, ("--model", "-m")):
        command.extend(["--model", model_name])
    if not _has_any_flag(command, ("--query", "-q")):
        command.extend(["--query", prompt])
    if not _has_any_flag(command, ("--quiet", "-Q")):
        command.append("--quiet")
    if "--yolo" not in command:
        command.append("--yolo")
    if "--source" not in command:
        command.extend(["--source", "drawai"])
    if image_paths and "--image" not in command:
        command.extend(["--image", str(image_paths[0])])
    return command


def _ensure_subcommand(command: list[str], subcommand: str) -> None:
    if subcommand not in command[1:]:
        command.append(subcommand)


def _has_any_flag(command: Sequence[str], flags: Sequence[str]) -> bool:
    return any(flag in command for flag in flags)


def _has_codex_service_tier(command: Sequence[str]) -> bool:
    return any("service_tier" in item or "serviceTier" in item for item in command)


def _runtime_fast(runtime_config: Mapping[str, Any]) -> bool:
    raw = runtime_config.get("fast")
    if raw in (None, ""):
        return False
    if isinstance(raw, bool):
        return raw
    raise AgentCliSvgError("runtime_config.fast must be a boolean")


def _format_timeout_seconds(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _openclaw_thinking_level(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value == "none":
        return "off"
    if value in {"minimal", "low", "medium", "high", "xhigh"}:
        return value
    return ""


def _controlled_prompt(
    prompt: str,
    *,
    agent: str,
    workspace_dir: Path,
    image_paths: Sequence[Path],
    output_svg_path: Path | None = None,
    output_response_path: Path | None = None,
) -> str:
    label = _agent_label(agent)
    image_block = "\n".join(f"- {path}" for path in image_paths) or "- none"
    if output_svg_path is None:
        return (
            f"Internal DrawAI {label} task.\n"
            f"Workspace root: {workspace_dir}\n"
            f"Use {label}'s own file, shell, and media-reading tools directly inside this workspace. "
            "Do not use MCP tools, apps, web search, memories, hooks, or multi-agent delegation. "
            "Write DrawAI outputs only inside the workspace root unless this prompt explicitly names another output path.\n\n"
            "Local image paths available for visual inspection:\n"
            f"{image_block}\n\n"
            f"{prompt}"
        )
    response_line = (
        f"- If useful, write brief notes to: {output_response_path}\n"
        if output_response_path is not None
        else ""
    )
    return (
        f"Internal DrawAI {label} SVG generation task.\n"
        f"Workspace root: {workspace_dir}\n"
        f"Use {label}'s own file, shell, and media-reading tools directly inside this workspace. "
        "Do not use MCP tools, apps, web search, memories, hooks, or multi-agent delegation. "
        "Write DrawAI outputs only inside the workspace root unless this prompt explicitly names another output path.\n\n"
        "Local image paths available for visual inspection:\n"
        f"{image_block}\n\n"
        "Write the SVG file yourself. Output contract:\n"
        f"- Required SVG output path: {output_svg_path}\n"
        f"{response_line}"
        "- The SVG output file must contain exactly one complete SVG document, starting with <svg and ending with </svg>.\n"
        "- Keep the final chat response short; the SVG file is the source of truth.\n\n"
        f"{prompt}"
    )


def _agent_label(agent: str) -> str:
    if agent == "kimi":
        return "Kimi CLI"
    if agent == "claude":
        return "Claude CLI"
    if agent == "codex":
        return "Codex CLI"
    if agent == "openclaw":
        return "OpenClaw CLI"
    if agent == "hermes":
        return "Hermes CLI"
    return "Agent CLI"


def _trace_command(command: Sequence[str], prompt: str) -> list[str]:
    redacted = []
    replacement = f"<prompt:{len(prompt)} chars>"
    for item in command:
        redacted.append(replacement if item == prompt else item)
    return redacted


def _normalize_workspace_output_path(path_value: str | Path, workspace_dir: Path) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = workspace_dir / path
    resolved = path.resolve(strict=False)
    if not _is_relative_to(resolved, workspace_dir):
        raise AgentCliSvgError(f"output path must be inside agent CLI workspace root: {resolved}")
    return resolved


def _read_output_svg_file(path: Path) -> str:
    if not path.exists():
        raise AgentCliSvgError(f"Agent CLI did not write required SVG output file: {path}")
    if not path.is_file():
        raise AgentCliSvgError(f"Agent CLI SVG output path is not a file: {path}")
    svg_text = path.read_text(encoding="utf-8").strip()
    if not svg_text.startswith("<svg") or not svg_text.endswith("</svg>"):
        raise AgentCliSvgError(f"Agent CLI SVG output file is not a complete SVG document: {path}")
    return svg_text


def _svg_from_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("<svg") and stripped.endswith("</svg>"):
        return stripped
    match = re.search(r"(<svg\b.*?</svg>)", stripped, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    raise AgentCliSvgError("Agent CLI final response did not contain a complete SVG document")


def _normalize_image_paths(image_paths: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(image_paths, (str, Path)):
        return [Path(image_paths)]
    return [Path(path) for path in image_paths]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _tail(value: Any, *, max_chars: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return text[-max_chars:]
