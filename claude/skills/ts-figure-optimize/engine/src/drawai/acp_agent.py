from __future__ import annotations

import base64
import json
import mimetypes
import os
import queue
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import model_runtime
from .acp_agent_presets import (
    SUPPORTED_ACP_AGENTS,
    acp_agent_default_command,
    acp_agent_from_value,
    acp_agent_label,
)


ACP_AGENT_RUNNER = "acp_agent"
ACP_PROTOCOL_VERSION = 1


class AcpAgentError(RuntimeError):
    """Raised when an ACP-backed Agent cannot complete a DrawAI task."""


class AcpAgentSession:
    """Thin ACP client for local Agent servers such as `kimi acp`."""

    def __init__(
        self,
        *,
        runtime_config: Mapping[str, Any] | None = None,
        trace_path: str | Path | None = None,
        isolated_cwd: str | Path | None = None,
        additional_roots: Sequence[str | Path] = (),
    ) -> None:
        self.runtime_config = dict(runtime_config or {})
        self.trace_path = Path(trace_path) if trace_path is not None else None
        self.isolated_cwd = Path(isolated_cwd or Path.cwd()).expanduser().resolve(strict=False)
        self.timeout_seconds = model_runtime._runtime_timeout_seconds(self.runtime_config)
        self.agent = _acp_agent(self.runtime_config)
        self.additional_roots = tuple(
            Path(path).expanduser().resolve(strict=False)
            for path in additional_roots
        )

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

        result = self._run_prompt(
            image_paths=normalized_images,
            prompt=_controlled_prompt(
                prompt,
                agent=self.agent,
                workspace_dir=self.isolated_cwd,
                image_paths=normalized_images,
                output_svg_path=svg_path,
                output_response_path=response_path,
            ),
            task_name=task_name,
        )
        if response_path is not None and not response_path.exists():
            response_path.write_text(result.final_text, encoding="utf-8")
        if svg_path is not None:
            if svg_path.exists():
                svg_text = _read_output_svg_file(svg_path)
                source = "output_svg_path"
            else:
                svg_text = _svg_from_text(result.final_text)
                svg_path.write_text(svg_text, encoding="utf-8")
                source = "agent_message"
        else:
            svg_text = _svg_from_text(result.final_text)
            source = "agent_message"
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "acp_agent_response",
                "runner": ACP_AGENT_RUNNER,
                "agent": self.agent,
                "task_name": task_name,
                "duration_ms": result.duration_ms,
                "stop_reason": result.stop_reason,
                "response_chars": len(result.final_text),
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
        result = self._run_prompt(
            image_paths=normalized_images,
            prompt=_controlled_prompt(
                prompt,
                agent=self.agent,
                workspace_dir=self.isolated_cwd,
                image_paths=normalized_images,
            ),
            task_name=task_name,
        )
        return result.final_text

    def _run_prompt(
        self,
        *,
        image_paths: Sequence[Path],
        prompt: str,
        task_name: str,
    ) -> "_AcpPromptResult":
        command = _acp_agent_command(self.runtime_config, self.agent)
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "acp_agent_request",
                "runner": ACP_AGENT_RUNNER,
                "agent": self.agent,
                "task_name": task_name,
                "command": command,
                "cwd": str(self.isolated_cwd),
                "timeout_seconds": self.timeout_seconds,
                "prompt_chars": len(prompt),
                "image_paths": [str(path) for path in image_paths],
            },
        )
        client = _AcpJsonRpcClient(
            command=command,
            cwd=self.isolated_cwd,
            timeout_seconds=self.timeout_seconds,
            trace_path=self.trace_path,
            task_name=task_name,
            agent=self.agent,
            read_roots=(self.isolated_cwd, *self.additional_roots),
            write_roots=(self.isolated_cwd,),
        )
        started_at = time.monotonic()
        try:
            result = client.run_prompt(prompt=prompt, image_paths=image_paths)
        finally:
            client.close()
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "acp_text_response",
                "runner": ACP_AGENT_RUNNER,
                "agent": self.agent,
                "task_name": task_name,
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "stop_reason": result.stop_reason,
                "response_chars": len(result.final_text),
            },
        )
        return result


@dataclass(frozen=True)
class _AcpPromptResult:
    final_text: str
    stop_reason: str
    duration_ms: int


@dataclass
class _TerminalSession:
    process: subprocess.Popen[str]
    output_byte_limit: int
    output: str = ""
    truncated: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, text: str) -> None:
        with self.lock:
            self.output += text
            encoded = self.output.encode("utf-8")
            if len(encoded) > self.output_byte_limit:
                self.truncated = True
                retained = encoded[-self.output_byte_limit :]
                self.output = retained.decode("utf-8", errors="ignore")

    def snapshot(self) -> tuple[str, bool]:
        with self.lock:
            return self.output, self.truncated


class _AcpJsonRpcClient:
    def __init__(
        self,
        *,
        command: Sequence[str],
        cwd: Path,
        timeout_seconds: float,
        trace_path: Path | None,
        task_name: str,
        agent: str,
        read_roots: Sequence[Path],
        write_roots: Sequence[Path],
    ) -> None:
        self.command = list(command)
        self.cwd = cwd
        self.timeout_seconds = float(timeout_seconds)
        self.trace_path = trace_path
        self.task_name = task_name
        self.agent = agent
        self.read_roots = tuple(path.resolve(strict=False) for path in read_roots)
        self.write_roots = tuple(path.resolve(strict=False) for path in write_roots)
        self._messages: queue.Queue[Any] = queue.Queue()
        self._stderr_parts: list[str] = []
        self._process: subprocess.Popen[str] | None = None
        self._request_id = 0
        self._session_id = ""
        self._agent_capabilities: Mapping[str, Any] = {}
        self._final_chunks: list[str] = []
        self._terminals: dict[str, _TerminalSession] = {}
        self._terminal_index = 0

    def run_prompt(self, *, prompt: str, image_paths: Sequence[Path]) -> _AcpPromptResult:
        started_at = time.monotonic()
        deadline = started_at + self.timeout_seconds
        self._start_process()
        initialize = self._request(
            "initialize",
            {
                "protocolVersion": ACP_PROTOCOL_VERSION,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                },
                "clientInfo": {"name": "drawai", "version": "0"},
            },
            deadline,
        )
        self._agent_capabilities = _mapping(initialize.get("agentCapabilities"))
        protocol_version = int(initialize.get("protocolVersion") or 0)
        if protocol_version != ACP_PROTOCOL_VERSION:
            raise AcpAgentError(
                f"ACP protocol version mismatch: agent returned {protocol_version}, expected {ACP_PROTOCOL_VERSION}"
            )
        session_params: dict[str, Any] = {"cwd": str(self.cwd), "mcpServers": []}
        additional = [str(path) for path in self.read_roots[1:]]
        if additional and _session_capability(self._agent_capabilities, "additionalDirectories"):
            session_params["additionalDirectories"] = additional
        session = self._request("session/new", session_params, deadline)
        self._session_id = str(session.get("sessionId") or "")
        if not self._session_id:
            raise AcpAgentError("ACP agent did not return a sessionId")
        response = self._request(
            "session/prompt",
            {
                "sessionId": self._session_id,
                "prompt": _prompt_blocks(
                    prompt,
                    image_paths=image_paths,
                    image_capability=_prompt_capability(self._agent_capabilities, "image"),
                ),
            },
            deadline,
        )
        stop_reason = str(response.get("stopReason") or "")
        if stop_reason != "end_turn":
            raise AcpAgentError(f"ACP agent stopped with stopReason={stop_reason!r}")
        return _AcpPromptResult(
            final_text="".join(self._final_chunks),
            stop_reason=stop_reason,
            duration_ms=int((time.monotonic() - started_at) * 1000),
        )

    def close(self) -> None:
        for terminal_id in tuple(self._terminals):
            terminal = self._terminals.pop(terminal_id)
            if terminal.process.poll() is None:
                terminal.process.terminate()
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            if self._session_id and _session_capability(self._agent_capabilities, "close"):
                try:
                    self._request(
                        "session/close",
                        {"sessionId": self._session_id},
                        time.monotonic() + 5,
                    )
                except AcpAgentError:
                    pass
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def _start_process(self) -> None:
        self._process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self._process.stdout is None or self._process.stdin is None:
            raise AcpAgentError("ACP subprocess did not expose stdio pipes")
        stdout_thread = threading.Thread(target=self._read_stdout, name="drawai-acp-stdout", daemon=True)
        stdout_thread.start()
        if self._process.stderr is not None:
            stderr_thread = threading.Thread(target=self._read_stderr, name="drawai-acp-stderr", daemon=True)
            stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                self._messages.put(json.loads(stripped))
            except json.JSONDecodeError as exc:
                self._messages.put(_AcpReaderError(f"ACP stdout emitted invalid JSON: {exc}: {stripped[:500]}"))
        self._messages.put(_AcpEof())

    def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        for line in self._process.stderr:
            self._stderr_parts.append(line)
            if len(self._stderr_parts) > 200:
                self._stderr_parts = self._stderr_parts[-200:]

    def _request(self, method: str, params: Mapping[str, Any], deadline: float) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "acp_request",
                "agent": self.agent,
                "task_name": self.task_name,
                "id": request_id,
                "method": method,
            },
        )
        while time.monotonic() < deadline:
            message = self._read_message(deadline)
            if isinstance(message, _AcpNoMessage):
                continue
            if isinstance(message, _AcpReaderError):
                raise AcpAgentError(str(message))
            if isinstance(message, _AcpEof):
                raise AcpAgentError(f"ACP agent exited before responding to {method}; stderr tail: {self._stderr_tail()}")
            if "method" in message and "id" in message:
                self._handle_agent_request(message, deadline)
                continue
            if "method" in message:
                self._handle_notification(message)
                continue
            if message.get("id") != request_id:
                model_runtime._append_trace(
                    self.trace_path,
                    {
                        "type": "acp_unmatched_response",
                        "agent": self.agent,
                        "task_name": self.task_name,
                        "id": message.get("id"),
                    },
                )
                continue
            if "error" in message:
                error = _mapping(message.get("error"))
                raise AcpAgentError(
                    f"ACP {method} failed: {error.get('message') or error}; stderr tail: {self._stderr_tail()}"
                )
            result = message.get("result")
            model_runtime._append_trace(
                self.trace_path,
                {
                    "type": "acp_response",
                    "agent": self.agent,
                    "task_name": self.task_name,
                    "id": request_id,
                    "method": method,
                },
            )
            return dict(_mapping(result))
        self._cancel_prompt()
        raise AcpAgentError(f"ACP request {method} exceeded timeout_seconds={self.timeout_seconds:g}")

    def _send(self, payload: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise AcpAgentError(f"ACP subprocess is not running; stderr tail: {self._stderr_tail()}")
        process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        process.stdin.flush()

    def _read_message(self, deadline: float) -> Any:
        remaining = max(0.0, deadline - time.monotonic())
        timeout = min(0.2, remaining)
        if timeout <= 0:
            return _AcpReaderError("ACP request deadline expired")
        try:
            return self._messages.get(timeout=timeout)
        except queue.Empty:
            process = self._process
            if process is not None and process.poll() is not None:
                return _AcpEof()
            return _AcpReaderError("ACP request deadline expired") if time.monotonic() >= deadline else _AcpNoMessage()

    def _handle_agent_request(self, message: Mapping[str, Any], deadline: float) -> None:
        method = str(message.get("method") or "")
        request_id = message.get("id")
        params = _mapping(message.get("params"))
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "acp_client_method",
                "agent": self.agent,
                "task_name": self.task_name,
                "method": method,
                "id": request_id,
            },
        )
        try:
            if method == "fs/read_text_file":
                result = self._fs_read_text_file(params)
            elif method == "fs/write_text_file":
                result = self._fs_write_text_file(params)
            elif method == "session/request_permission":
                result = self._select_permission(params)
            elif method == "terminal/create":
                result = self._terminal_create(params)
            elif method == "terminal/output":
                result = self._terminal_output(params)
            elif method == "terminal/wait_for_exit":
                result = self._terminal_wait_for_exit(params, deadline)
            elif method == "terminal/kill":
                result = self._terminal_kill(params)
            elif method == "terminal/release":
                result = self._terminal_release(params)
            else:
                self._send_error(request_id, -32601, f"unsupported ACP client method: {method}")
                return
        except Exception as exc:
            self._send_error(request_id, -32603, str(exc))
            return
        self._send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _handle_notification(self, message: Mapping[str, Any]) -> None:
        method = str(message.get("method") or "")
        params = _mapping(message.get("params"))
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "acp_notification",
                "agent": self.agent,
                "task_name": self.task_name,
                "method": method,
            },
        )
        if method != "session/update":
            return
        update = _mapping(params.get("update"))
        session_update = str(update.get("sessionUpdate") or "")
        if session_update != "agent_message_chunk":
            return
        content = _mapping(update.get("content"))
        if content.get("type") == "text":
            self._final_chunks.append(str(content.get("text") or ""))

    def _send_error(self, request_id: Any, code: int, message: str) -> None:
        self._send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def _fs_read_text_file(self, params: Mapping[str, Any]) -> dict[str, str]:
        path = _resolve_allowed_path(params.get("path"), self.read_roots, "read")
        if not path.is_file():
            raise AcpAgentError(f"file does not exist: {path}")
        content = path.read_text(encoding="utf-8")
        line = params.get("line")
        limit = params.get("limit")
        if line is not None or limit is not None:
            lines = content.splitlines(keepends=True)
            start = max(0, int(line or 1) - 1)
            end = None if limit is None else start + max(0, int(limit))
            content = "".join(lines[start:end])
        return {"content": content}

    def _fs_write_text_file(self, params: Mapping[str, Any]) -> None:
        path = _resolve_allowed_path(params.get("path"), self.write_roots, "write")
        content = params.get("content")
        if not isinstance(content, str):
            raise AcpAgentError("fs/write_text_file content must be a string")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return None

    def _select_permission(self, params: Mapping[str, Any]) -> dict[str, Any]:
        options = params.get("options")
        if not isinstance(options, Sequence) or isinstance(options, (str, bytes)) or not options:
            return {"outcome": {"outcome": "cancelled"}}
        selected = None
        for option in options:
            option_data = _mapping(option)
            if str(option_data.get("kind") or "").startswith("allow"):
                selected = option_data
                break
        if selected is None:
            selected = _mapping(options[0])
        option_id = str(selected.get("optionId") or "")
        if not option_id:
            return {"outcome": {"outcome": "cancelled"}}
        return {"outcome": {"outcome": "selected", "optionId": option_id}}

    def _terminal_create(self, params: Mapping[str, Any]) -> dict[str, str]:
        command = str(params.get("command") or "")
        if not command:
            raise AcpAgentError("terminal/create command is required")
        args_raw = params.get("args") or []
        if not isinstance(args_raw, Sequence) or isinstance(args_raw, (str, bytes)):
            raise AcpAgentError("terminal/create args must be a list")
        cwd_raw = params.get("cwd") or str(self.cwd)
        cwd = _resolve_allowed_path(cwd_raw, self.read_roots, "terminal cwd")
        env = os.environ.copy()
        for item in params.get("env") or []:
            data = _mapping(item)
            name = str(data.get("name") or "")
            if name:
                env[name] = str(data.get("value") or "")
        output_byte_limit = int(params.get("outputByteLimit") or 1_048_576)
        process = subprocess.Popen(
            [command, *[str(arg) for arg in args_raw]],
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._terminal_index += 1
        terminal_id = f"term_{self._terminal_index}"
        terminal = _TerminalSession(process=process, output_byte_limit=output_byte_limit)
        self._terminals[terminal_id] = terminal
        threading.Thread(
            target=_read_terminal_output,
            args=(terminal,),
            name=f"drawai-acp-terminal-{self._terminal_index}",
            daemon=True,
        ).start()
        return {"terminalId": terminal_id}

    def _terminal_output(self, params: Mapping[str, Any]) -> dict[str, Any]:
        terminal = self._require_terminal(params)
        output, truncated = terminal.snapshot()
        result: dict[str, Any] = {"output": output, "truncated": truncated}
        status = _terminal_exit_status(terminal.process)
        if status is not None:
            result["exitStatus"] = status
        return result

    def _terminal_wait_for_exit(self, params: Mapping[str, Any], deadline: float) -> dict[str, Any]:
        terminal = self._require_terminal(params)
        while terminal.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        status = _terminal_exit_status(terminal.process)
        if status is None:
            raise AcpAgentError("terminal/wait_for_exit exceeded ACP prompt timeout")
        return status

    def _terminal_kill(self, params: Mapping[str, Any]) -> dict[str, Any]:
        terminal = self._require_terminal(params)
        if terminal.process.poll() is None:
            terminal.process.terminate()
        return {}

    def _terminal_release(self, params: Mapping[str, Any]) -> dict[str, Any]:
        terminal_id = str(params.get("terminalId") or "")
        terminal = self._terminals.pop(terminal_id, None)
        if terminal is None:
            raise AcpAgentError(f"unknown terminalId: {terminal_id}")
        if terminal.process.poll() is None:
            terminal.process.terminate()
        return {}

    def _require_terminal(self, params: Mapping[str, Any]) -> _TerminalSession:
        terminal_id = str(params.get("terminalId") or "")
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            raise AcpAgentError(f"unknown terminalId: {terminal_id}")
        return terminal

    def _cancel_prompt(self) -> None:
        if self._session_id:
            try:
                self._send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": self._session_id}})
            except AcpAgentError:
                pass

    def _stderr_tail(self) -> str:
        return "".join(self._stderr_parts)[-4000:]


class _AcpReaderError:
    def __init__(self, message: str) -> None:
        self.message = message

    def __str__(self) -> str:
        return self.message


class _AcpEof:
    pass


class _AcpNoMessage:
    pass


def invoke_acp_agent_svg_text(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: Mapping[str, Any] | None = None,
    trace_path: str | Path | None = None,
    isolated_cwd: str | Path | None = None,
    output_svg_path: str | Path | None = None,
    output_response_path: str | Path | None = None,
    additional_roots: Sequence[str | Path] = (),
) -> str:
    session = AcpAgentSession(
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=isolated_cwd,
        additional_roots=additional_roots,
    )
    return session.invoke(
        image_paths=image_paths,
        prompt=prompt,
        task_name=task_name,
        output_svg_path=output_svg_path,
        output_response_path=output_response_path,
    )


def invoke_acp_agent_text(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: Mapping[str, Any] | None = None,
    trace_path: str | Path | None = None,
    isolated_cwd: str | Path | None = None,
    additional_roots: Sequence[str | Path] = (),
) -> str:
    session = AcpAgentSession(
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=isolated_cwd,
        additional_roots=additional_roots,
    )
    return session.invoke_text(
        image_paths=image_paths,
        prompt=prompt,
        task_name=task_name,
    )


def _prompt_blocks(prompt: str, *, image_paths: Sequence[Path], image_capability: bool) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if not image_capability:
        return blocks
    for image_path in image_paths:
        resolved = image_path.expanduser().resolve(strict=False)
        image_bytes = resolved.read_bytes()
        mime_type = mimetypes.guess_type(resolved.name)[0] or "image/png"
        blocks.append(
            {
                "type": "image",
                "mimeType": mime_type,
                "data": base64.b64encode(image_bytes).decode("ascii"),
                "uri": resolved.as_uri(),
            }
        )
    return blocks


def _acp_agent(runtime_config: Mapping[str, Any]) -> str:
    acp = runtime_config.get("acp")
    agent = ""
    if isinstance(acp, Mapping):
        raw_agent = str(acp.get("agent") or "")
        agent = acp_agent_from_value(raw_agent) or raw_agent.strip().lower()
    if not agent:
        provider = str(runtime_config.get("provider") or "")
        connection_id = str(runtime_config.get("connection_id") or "")
        agent = acp_agent_from_value(connection_id) or acp_agent_from_value(provider) or "kimi"
    if agent not in SUPPORTED_ACP_AGENTS:
        supported = ", ".join(sorted(SUPPORTED_ACP_AGENTS))
        raise AcpAgentError(f"Unsupported ACP agent preset: {agent!r}. Expected one of: {supported}")
    return agent


def _acp_agent_command(runtime_config: Mapping[str, Any], agent: str) -> list[str]:
    acp = runtime_config.get("acp")
    raw: Any = None
    if isinstance(acp, Mapping):
        raw = acp.get("command")
    if not raw:
        raw = os.environ.get("DRAWAI_ACP_AGENT_COMMAND")
    if not raw and agent != "custom":
        raw = acp_agent_default_command(agent)
    if not raw:
        raise AcpAgentError("model_runtime.acp.command is required for custom ACP agents")
    if isinstance(raw, str):
        command = shlex.split(raw)
    elif isinstance(raw, Sequence):
        command = [str(item) for item in raw]
    else:
        raise AcpAgentError("runtime_config.acp.command must be a string or list of strings")
    if not command:
        raise AcpAgentError("runtime_config.acp.command must not be empty")
    if _runtime_fast(runtime_config) and agent == "qwen" and "--bare" not in command:
        command.append("--bare")
    return command


def _runtime_fast(runtime_config: Mapping[str, Any]) -> bool:
    raw = runtime_config.get("fast")
    if raw in (None, ""):
        return False
    if isinstance(raw, bool):
        return raw
    raise AcpAgentError("runtime_config.fast must be a boolean")


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
            f"Use the ACP client filesystem and terminal capabilities directly inside this workspace. "
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
        f"Use the ACP client filesystem and terminal capabilities directly inside this workspace. "
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
    return acp_agent_label(agent)


def _normalize_workspace_output_path(path_value: str | Path, workspace_dir: Path) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = workspace_dir / path
    resolved = path.resolve(strict=False)
    if not _is_relative_to(resolved, workspace_dir):
        raise AcpAgentError(f"output path must be inside ACP workspace root: {resolved}")
    return resolved


def _read_output_svg_file(path: Path) -> str:
    if not path.exists():
        raise AcpAgentError(f"ACP agent did not write required SVG output file: {path}")
    if not path.is_file():
        raise AcpAgentError(f"ACP SVG output path is not a file: {path}")
    svg_text = path.read_text(encoding="utf-8").strip()
    if not svg_text.startswith("<svg") or not svg_text.endswith("</svg>"):
        raise AcpAgentError(f"ACP SVG output file is not a complete SVG document: {path}")
    return svg_text


def _svg_from_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("<svg") and stripped.endswith("</svg>"):
        return stripped
    match = re.search(r"(<svg\b.*?</svg>)", stripped, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    raise AcpAgentError("ACP final response did not contain a complete SVG document")


def _normalize_image_paths(image_paths: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(image_paths, (str, Path)):
        return [Path(image_paths)]
    return [Path(path) for path in image_paths]


def _resolve_allowed_path(raw: Any, roots: Sequence[Path], operation: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise AcpAgentError(f"ACP {operation} path must be an absolute string")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise AcpAgentError(f"ACP {operation} path must be absolute: {raw}")
    resolved = path.resolve(strict=False)
    if not any(_is_relative_to(resolved, root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise AcpAgentError(f"ACP {operation} path is outside allowed roots: {resolved}; allowed: {allowed}")
    return resolved


def _mapping(raw: Any) -> Mapping[str, Any]:
    return raw if isinstance(raw, Mapping) else {}


def _prompt_capability(capabilities: Mapping[str, Any], name: str) -> bool:
    prompt = capabilities.get("promptCapabilities")
    return bool(_mapping(prompt).get(name))


def _session_capability(capabilities: Mapping[str, Any], name: str) -> bool:
    session = capabilities.get("sessionCapabilities")
    return name in _mapping(session)


def _terminal_exit_status(process: subprocess.Popen[str]) -> dict[str, Any] | None:
    returncode = process.poll()
    if returncode is None:
        return None
    if returncode < 0:
        return {"exitCode": None, "signal": str(-returncode)}
    return {"exitCode": returncode, "signal": None}


def _read_terminal_output(terminal: _TerminalSession) -> None:
    if terminal.process.stdout is None:
        return
    for line in terminal.process.stdout:
        terminal.append(line)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
