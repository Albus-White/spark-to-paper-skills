from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from . import model_runtime


DRAWAI_TOOL_AGENT_PROVIDER = "drawai_tool_agent"
DEFAULT_TOOL_AGENT_MAX_ITERATIONS = 200
DEFAULT_TOOL_AGENT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_FILE_READ_LIMIT_CHARS = 20000
MAX_FILE_READ_LIMIT_CHARS = 50000
MAX_SINGLE_WRITE_CHARS = 12000
MAX_APPEND_WRITE_CHARS = 8000
MODEL_INPUT_JPEG_THRESHOLD_BYTES = 1_000_000
MODEL_INPUT_JPEG_QUALITY = 90


class DrawAIToolAgentError(RuntimeError):
    """Raised when the DrawAI-owned API tool agent cannot complete its run."""


@dataclass(frozen=True)
class ToolAgentRunResult:
    final_text: str
    iterations: int
    tool_calls: int


def invoke_drawai_tool_agent(
    *,
    prompt: str,
    image_paths: str | Path | Sequence[str | Path] = (),
    task_name: str,
    runtime_config: Mapping[str, Any],
    workspace_dir: str | Path,
    repo_root: str | Path,
    trace_path: str | Path | None = None,
    max_output_tokens: int = DEFAULT_TOOL_AGENT_MAX_OUTPUT_TOKENS,
    max_iterations: int = DEFAULT_TOOL_AGENT_MAX_ITERATIONS,
) -> ToolAgentRunResult:
    """Run DrawAI's API-backed Codex-like tool loop.

    The model is never trusted to return final artifacts directly. It must use
    file tools to create or edit declared outputs in ``workspace_dir``.
    """

    model_runtime._raise_if_running_loop()
    return asyncio.run(
        _invoke_drawai_tool_agent_async(
            prompt=prompt,
            image_paths=image_paths,
            task_name=task_name,
            runtime_config=runtime_config,
            workspace_dir=workspace_dir,
            repo_root=repo_root,
            trace_path=trace_path,
            max_output_tokens=max_output_tokens,
            max_iterations=max_iterations,
        )
    )


async def _invoke_drawai_tool_agent_async(
    *,
    prompt: str,
    image_paths: str | Path | Sequence[str | Path],
    task_name: str,
    runtime_config: Mapping[str, Any],
    workspace_dir: str | Path,
    repo_root: str | Path,
    trace_path: str | Path | None,
    max_output_tokens: int,
    max_iterations: int,
) -> ToolAgentRunResult:
    try:
        from openai import AsyncOpenAI
    except Exception as exc:  # pragma: no cover - dependency is installed for normal runs.
        raise DrawAIToolAgentError("openai Python SDK is required for drawai_tool_agent") from exc

    runtime = dict(runtime_config)
    runtime["wire_api"] = str(runtime.get("wire_api") or "chat_completions")
    settings = model_runtime._resolve_settings(runtime)
    if settings.wire_api != "chat_completions":
        raise DrawAIToolAgentError("drawai_tool_agent requires wire_api=chat_completions")
    if not settings.model_name:
        raise DrawAIToolAgentError("drawai_tool_agent requires runtime_config.model_name")

    timeout_seconds = model_runtime._runtime_timeout_seconds(runtime)
    workspace = Path(workspace_dir).expanduser().resolve(strict=False)
    repo = Path(repo_root).expanduser().resolve(strict=False)
    trace = Path(trace_path) if trace_path is not None else None
    tool_runtime = _ToolRuntime(workspace_dir=workspace, repo_root=repo, trace_path=trace, task_name=task_name)
    normalized_images = _normalize_image_paths(image_paths)
    image_traces = [_image_trace(path) for path in normalized_images]
    messages = _initial_messages(prompt=prompt, image_paths=normalized_images)

    http_client = None
    if model_runtime._is_loopback_base_url(settings.base_url):
        try:
            import httpx
        except Exception as exc:  # pragma: no cover - dependency comes with openai.
            raise DrawAIToolAgentError("httpx is required for loopback OpenAI-compatible gateways") from exc
        http_client = httpx.AsyncClient(trust_env=False)

    client = AsyncOpenAI(
        api_key=settings.api_key or "no-api-key",
        base_url=settings.base_url or None,
        timeout=timeout_seconds,
        max_retries=0,
        default_headers=settings.extra_headers or None,
        http_client=http_client,
    )
    started_at = time.monotonic()
    tool_call_count = 0
    model_runtime._append_trace(
        trace,
        {
            "type": "tool_agent_request",
            "provider_id": DRAWAI_TOOL_AGENT_PROVIDER,
            "task_name": task_name,
            "provider": settings.provider,
            "connection_id": settings.connection_id,
            "model_name": settings.model_name,
            "wire_api": settings.wire_api,
            "workspace_dir": str(workspace),
            "repo_root": str(repo),
            "images": image_traces,
            "max_output_tokens": int(max_output_tokens),
            "max_iterations": int(max_iterations),
            "timeout_seconds": timeout_seconds,
        },
    )
    try:
        final_text = ""
        iterations = 0
        for iteration in range(1, int(max_iterations) + 1):
            iterations = iteration
            request_payload: dict[str, Any] = {
                "model": settings.model_name,
                "messages": messages,
                "tools": _tool_schemas(),
                "tool_choice": "auto",
                "max_tokens": int(max_output_tokens),
            }
            if settings.extra_body:
                request_payload["extra_body"] = settings.extra_body
            response = await client.chat.completions.create(**request_payload)
            message = (getattr(response, "choices", []) or [])[0].message
            assistant_message, tool_calls = _assistant_message_from_response(message)
            messages.append(assistant_message)
            model_runtime._append_trace(
                trace,
                {
                    "type": "tool_agent_turn",
                    "task_name": task_name,
                    "iteration": iteration,
                    "content_excerpt": str(assistant_message.get("content") or "")[:2000],
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "name": call["function"]["name"],
                        }
                        for call in tool_calls
                    ],
                },
            )
            if not tool_calls:
                final_text = str(assistant_message.get("content") or "")
                break
            finalize_text: str | None = None
            for tool_call in tool_calls:
                tool_call_count += 1
                result = tool_runtime.execute_tool_call(tool_call)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result.payload, ensure_ascii=False),
                    }
                )
                if result.followup_message is not None:
                    messages.append(result.followup_message)
                function = tool_call.get("function")
                tool_name = str(function.get("name") if isinstance(function, Mapping) else "")
                if tool_name == "finalize" and result.payload.get("ok") is True:
                    finalize_text = str(result.payload.get("summary") or "")
                auto_finalize_text = _auto_finalize_after_validation(
                    task_name=task_name,
                    tool_name=tool_name,
                    payload=result.payload,
                )
                if auto_finalize_text is not None:
                    finalize_text = auto_finalize_text
            if finalize_text is not None:
                final_text = finalize_text
                break
        else:
            raise DrawAIToolAgentError(
                f"drawai_tool_agent exceeded max_iterations={max_iterations} for task {task_name!r}"
            )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await close()

    model_runtime._append_trace(
        trace,
        {
            "type": "tool_agent_response",
            "provider_id": DRAWAI_TOOL_AGENT_PROVIDER,
            "task_name": task_name,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "iterations": iterations,
            "tool_calls": tool_call_count,
            "final_excerpt": final_text[:2000],
            "final_chars": len(final_text),
        },
    )
    return ToolAgentRunResult(final_text=final_text, iterations=iterations, tool_calls=tool_call_count)


@dataclass(frozen=True)
class _ToolExecutionResult:
    payload: Mapping[str, Any]
    followup_message: Mapping[str, Any] | None = None


class _ToolRuntime:
    def __init__(
        self,
        *,
        workspace_dir: Path,
        repo_root: Path,
        trace_path: Path | None,
        task_name: str,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.repo_root = repo_root
        self.trace_path = trace_path
        self.task_name = task_name

    def execute_tool_call(self, tool_call: Mapping[str, Any]) -> _ToolExecutionResult:
        function = tool_call.get("function")
        name = str(function.get("name") if isinstance(function, Mapping) else "")
        raw_arguments = function.get("arguments") if isinstance(function, Mapping) else ""
        started_at = time.monotonic()
        try:
            arguments = _json_object(raw_arguments)
            if name == "open_file":
                result = self._open_file(arguments)
                followup = None
            elif name == "open_image":
                result, followup = self._open_image(arguments)
            elif name == "list_files":
                result = self._list_files(arguments)
                followup = None
            elif name == "copy_file":
                result = self._copy_file(arguments)
                followup = None
            elif name == "write_file":
                result = self._write_file(arguments)
                followup = None
            elif name == "append_file":
                result = self._append_file(arguments)
                followup = None
            elif name == "edit_file":
                result = self._edit_file(arguments)
                followup = None
            elif name == "run_drawai_tool":
                result = self._run_drawai_tool(arguments)
                followup = None
            elif name == "finalize":
                result = {"ok": True, "summary": str(arguments.get("summary") or "")}
                followup = None
            else:
                result = {"ok": False, "error": f"unknown tool: {name}"}
                followup = None
        except (OSError, UnicodeDecodeError, ValueError, subprocess.TimeoutExpired) as exc:
            result = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
            followup = None
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "tool_agent_tool_result",
                "task_name": self.task_name,
                "tool": name,
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "result": result,
            },
        )
        return _ToolExecutionResult(payload=result, followup_message=followup)

    def _open_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        path = self._resolve_workspace_path(arguments.get("path"))
        limit = _bounded_int(arguments.get("limit"), default=DEFAULT_FILE_READ_LIMIT_CHARS, maximum=MAX_FILE_READ_LIMIT_CHARS)
        offset = max(0, _bounded_int(arguments.get("offset"), default=0, maximum=10_000_000))
        text = path.read_text(encoding="utf-8")
        chunk = text[offset : offset + limit]
        next_offset = offset + len(chunk)
        return {
            "ok": True,
            "path": self._workspace_relative(path),
            "chars": len(text),
            "offset": offset,
            "limit": limit,
            "content": chunk,
            "next_offset": next_offset if next_offset < len(text) else None,
        }

    def _open_image(self, arguments: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        path = self._resolve_workspace_path(arguments.get("path"))
        data_url, metadata = _image_data_url(path)
        message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Image opened from tool path {self._workspace_relative(path)}.",
                },
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
        return (
            {
                "ok": True,
                "path": self._workspace_relative(path),
                **metadata,
                "delivered_as_followup_image": True,
            },
            message,
        )

    def _list_files(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        raw_path = arguments.get("path") or "."
        path = self._resolve_workspace_path(raw_path)
        if not path.is_dir():
            raise ValueError(f"not a directory: {self._workspace_relative(path)}")
        pattern = str(arguments.get("glob") or "*")
        limit = _bounded_int(arguments.get("limit"), default=200, maximum=1000)
        entries: list[dict[str, Any]] = []
        for child in sorted(path.glob(pattern)):
            resolved = child.resolve(strict=False)
            self._ensure_workspace_path(resolved)
            entries.append(
                {
                    "path": self._workspace_relative(resolved),
                    "type": "dir" if child.is_dir() else "file",
                    "bytes": child.stat().st_size if child.is_file() else None,
                }
            )
            if len(entries) >= limit:
                break
        return {"ok": True, "path": self._workspace_relative(path), "glob": pattern, "entries": entries}

    def _copy_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        source = self._resolve_workspace_path(arguments.get("source"))
        path = self._resolve_workspace_path(arguments.get("path"))
        if not source.is_file():
            raise ValueError(f"source is not a file: {self._workspace_relative(source)}")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
        data = path.read_bytes()
        result: dict[str, Any] = {
            "ok": True,
            "source": self._workspace_relative(source),
            "path": self._workspace_relative(path),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "next_steps": (
                "The declared output file now exists. If you do not have an exact small old_text/new_text edit ready, "
                "run the required DrawAI validation tool on this output path now, then call finalize after validation is ok. "
                "Do not spend another turn rewriting the whole copied file."
            ),
        }
        if "page_spec_refine" in self.task_name and path.name == "page_spec.json":
            result["auto_validation"] = self._run_drawai_tool(
                {
                    "tool_id": "format",
                    "args": [
                        "validate",
                        "--format-id",
                        "drawai.page_spec.v1",
                        "--path",
                        self._workspace_relative(path),
                    ],
                }
            )
        return result

    def _write_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        path = self._resolve_workspace_path(arguments.get("path"))
        content = str(arguments.get("content") or "")
        if len(content) > MAX_SINGLE_WRITE_CHARS:
            return {
                "ok": False,
                "path": self._workspace_relative(path),
                "error": (
                    f"write_file content is {len(content)} chars, above the {MAX_SINGLE_WRITE_CHARS} char "
                    "single-call limit. Create or truncate the file with write_file content='', then use "
                    f"append_file chunks of at most {MAX_APPEND_WRITE_CHARS} chars."
                ),
                "error_type": "ContentTooLarge",
                "chars": len(content),
                "max_chars": MAX_SINGLE_WRITE_CHARS,
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "path": self._workspace_relative(path),
            "chars": len(content),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }

    def _append_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        path = self._resolve_workspace_path(arguments.get("path"))
        content = str(arguments.get("content") or "")
        if len(content) > MAX_APPEND_WRITE_CHARS:
            return {
                "ok": False,
                "path": self._workspace_relative(path),
                "error": (
                    f"append_file content is {len(content)} chars, above the {MAX_APPEND_WRITE_CHARS} char "
                    "chunk limit. Split the content into smaller append_file calls."
                ),
                "error_type": "ContentTooLarge",
                "chars": len(content),
                "max_chars": MAX_APPEND_WRITE_CHARS,
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
        total = path.read_text(encoding="utf-8")
        return {
            "ok": True,
            "path": self._workspace_relative(path),
            "appended_chars": len(content),
            "chars": len(total),
            "sha256": hashlib.sha256(total.encode("utf-8")).hexdigest(),
        }

    def _edit_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        path = self._resolve_workspace_path(arguments.get("path"))
        old_text = str(arguments.get("old_text") or "")
        new_text = str(arguments.get("new_text") or "")
        expected = _bounded_int(arguments.get("expected_replacements"), default=1, maximum=1000)
        if not old_text:
            raise ValueError("old_text must be non-empty")
        content = path.read_text(encoding="utf-8")
        actual = content.count(old_text)
        if actual != expected:
            raise ValueError(f"expected {expected} replacement(s), found {actual}")
        updated = content.replace(old_text, new_text, expected)
        path.write_text(updated, encoding="utf-8")
        return {
            "ok": True,
            "path": self._workspace_relative(path),
            "replacements": expected,
            "chars": len(updated),
            "sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
        }

    def _run_drawai_tool(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        tool_id = str(arguments.get("tool_id") or "").strip()
        if not tool_id:
            raise ValueError("tool_id is required")
        raw_args = arguments.get("args")
        if not isinstance(raw_args, list):
            raise ValueError("args must be an array of strings")
        args = [str(item) for item in raw_args]
        self._validate_drawai_tool_args(args)
        timeout = _bounded_int(arguments.get("timeout_seconds"), default=120, maximum=900)
        command = [sys.executable, "-m", "drawai.cli", "tool", tool_id, *args]
        env = os.environ.copy()
        env["PYTHONPATH"] = _prepend_pythonpath(self.repo_root / "src", env.get("PYTHONPATH"))
        completed = subprocess.run(
            command,
            cwd=str(self.workspace_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "command": _redact_command(command),
            "tool_id": tool_id,
            "args": args,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-8000:],
        }

    def _resolve_workspace_path(self, raw_path: Any) -> Path:
        path_text = str(raw_path or "").strip()
        if not path_text:
            raise ValueError("path is required")
        path = Path(path_text)
        resolved = path.expanduser().resolve(strict=False) if path.is_absolute() else (self.workspace_dir / path).resolve(strict=False)
        self._ensure_workspace_path(resolved)
        return resolved

    def _ensure_workspace_path(self, path: Path) -> None:
        try:
            path.relative_to(self.workspace_dir)
        except ValueError as exc:
            raise ValueError(f"path escapes workspace: {path}") from exc

    def _validate_drawai_tool_args(self, args: Sequence[str]) -> None:
        for arg in args:
            if not arg or arg.startswith("-"):
                continue
            candidate = Path(arg)
            if candidate.is_absolute():
                self._ensure_workspace_path(candidate.expanduser().resolve(strict=False))
            elif ".." in candidate.parts:
                raise ValueError(f"DrawAI tool path argument escapes workspace: {arg}")

    def _workspace_relative(self, path: Path) -> str:
        try:
            return path.resolve(strict=False).relative_to(self.workspace_dir).as_posix()
        except ValueError:
            return str(path)


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        _function_tool(
            "open_file",
            "Read a UTF-8 text file from the DrawAI workflow workspace with bounded chunking.",
            {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_FILE_READ_LIMIT_CHARS},
            },
            ["path"],
        ),
        _function_tool(
            "open_image",
            "Open an image file from the DrawAI workflow workspace and attach it as visual context for the next turn.",
            {"path": {"type": "string"}},
            ["path"],
        ),
        _function_tool(
            "list_files",
            "List files under a workspace directory using a glob pattern.",
            {
                "path": {"type": "string"},
                "glob": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            ["path"],
        ),
        _function_tool(
            "copy_file",
            (
                "Copy an existing workspace file to another workspace path. Use this for outputs derived from an "
                "input file, especially large PageSpec JSON files: copy the connected input to the declared output, "
                "then use edit_file for small targeted changes and run validation."
            ),
            {
                "source": {"type": "string"},
                "path": {"type": "string"},
            },
            ["source", "path"],
        ),
        _function_tool(
            "write_file",
            (
                "Write or truncate a short UTF-8 text file inside the workflow workspace. "
                f"Use this for declared outputs up to {MAX_SINGLE_WRITE_CHARS} chars. "
                "For larger JSON/SVG/log artifacts, first call write_file with content='' and then append_file in chunks."
            ),
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            ["path", "content"],
        ),
        _function_tool(
            "append_file",
            (
                "Append one UTF-8 text chunk to a workspace file. Use this for large declared outputs after "
                f"truncating the file with write_file content=''. Keep each chunk at or below {MAX_APPEND_WRITE_CHARS} chars."
            ),
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            ["path", "content"],
        ),
        _function_tool(
            "edit_file",
            "Edit a UTF-8 text file by replacing exact text. Use open_file first unless you know the exact old_text.",
            {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "expected_replacements": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            ["path", "old_text", "new_text"],
        ),
        _function_tool(
            "run_drawai_tool",
            "Run an approved DrawAI CLI tool from the workflow workspace.",
            {
                "tool_id": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
            },
            ["tool_id", "args"],
        ),
        _function_tool(
            "finalize",
            "Signal that declared output files have been written and summarize the work.",
            {"summary": {"type": "string"}},
            ["summary"],
        ),
    ]


def _function_tool(
    name: str,
    description: str,
    properties: Mapping[str, Any],
    required: Sequence[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": dict(properties),
                "required": list(required),
            },
        },
    }


def _initial_messages(*, prompt: str, image_paths: Sequence[Path]) -> list[dict[str, Any]]:
    system_prompt = (
        "You are DrawAI's API-backed file tool agent. Work like a small Codex-like runtime: "
        "inspect files and images with tools, write or edit the declared output files with tools, "
        "and run DrawAI tools when validation or format contracts are needed. "
        "Do not put final SVG/JSON artifacts only in your assistant message. The harness consumes files, not prose. "
        "When an output is a refined version of a connected input file, prefer copy_file to create the output first, "
        "then use edit_file only for exact small targeted changes and validate it immediately. A validated copy is an "
        "acceptable completion when a full rewrite would delay or risk the run. "
        "For PageSpec refine tasks, copy the connected PageSpec to the declared output before reading the full file; "
        "only inspect chunks later if you already know a targeted edit is needed. "
        f"For large JSON, SVG, or logs, do not put the whole artifact in one write_file call. Use write_file with content='' "
        f"to create/truncate the file, then append_file chunks no larger than {MAX_APPEND_WRITE_CHARS} chars until complete. "
        "Use final text only for a short completion summary after all declared outputs exist."
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image_path in image_paths:
        data_url, _metadata = _image_data_url(image_path)
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def _assistant_message_from_response(message: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tool_calls: list[dict[str, Any]] = []
    for call in getattr(message, "tool_calls", []) or []:
        function = getattr(call, "function", None)
        tool_calls.append(
            {
                "id": str(getattr(call, "id", "") or ""),
                "type": "function",
                "function": {
                    "name": str(getattr(function, "name", "") or ""),
                    "arguments": str(getattr(function, "arguments", "") or "{}"),
                },
            }
        )
    assistant: dict[str, Any] = {"role": "assistant", "content": getattr(message, "content", None) or ""}
    if tool_calls:
        assistant["tool_calls"] = tool_calls
    return assistant, tool_calls


def _json_object(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw
    parsed = json.loads(str(raw or "{}"))
    if not isinstance(parsed, Mapping):
        raise ValueError("tool arguments must decode to a JSON object")
    return parsed


def _auto_finalize_after_validation(
    *,
    task_name: str,
    tool_name: str,
    payload: Mapping[str, Any],
) -> str | None:
    if "page_spec_refine" in task_name:
        if tool_name == "copy_file" and payload.get("ok") is True:
            validation = payload.get("auto_validation")
            if isinstance(validation, Mapping) and _format_validation_ok(validation, "drawai.page_spec.v1"):
                return "validated copied drawai.page_spec.v1 output"
            return None
        if tool_name != "run_drawai_tool" or payload.get("ok") is not True:
            return None
        if payload.get("tool_id") != "format":
            return None
        args = [str(item) for item in payload.get("args") or ()]
        if "validate" not in args or "drawai.page_spec.v1" not in args:
            return None
        if _format_validation_ok(payload, "drawai.page_spec.v1"):
            return "validated drawai.page_spec.v1 output"
        return None
    if tool_name != "run_drawai_tool" or payload.get("ok") is not True:
        return None
    if "svg" not in task_name:
        return None
    args = [str(item) for item in payload.get("args") or ()]
    if payload.get("tool_id") == "page-spec-svg-draft" and _page_spec_svg_draft_validation_ok(payload):
        if _targets_final_semantic_svg(args) or _page_spec_svg_draft_finalized_output(payload):
            return "validated page-spec semantic SVG draft output"
        return None
    if not _targets_final_semantic_svg(args):
        return None
    if payload.get("tool_id") == "svg-validate" and _svg_validation_ok(payload):
        return "validated semantic SVG output"
    return None


def _format_validation_ok(payload: Mapping[str, Any], format_id: str) -> bool:
    args = [str(item) for item in payload.get("args") or ()]
    if "validate" not in args or format_id not in args:
        return False
    try:
        validation = json.loads(str(payload.get("stdout") or "{}"))
    except json.JSONDecodeError:
        return False
    return isinstance(validation, Mapping) and validation.get("ok") is True


def _page_spec_svg_draft_validation_ok(payload: Mapping[str, Any]) -> bool:
    draft = _json_stdout_object(payload)
    if draft is None:
        return False
    validation = draft.get("validation")
    return isinstance(validation, Mapping) and validation.get("status") == "ok"


def _page_spec_svg_draft_finalized_output(payload: Mapping[str, Any]) -> bool:
    draft = _json_stdout_object(payload)
    if draft is None:
        return False
    outputs = draft.get("finalized_outputs")
    if not isinstance(outputs, Mapping):
        return False
    for key in ("semantic_svg", "declared_semantic_svg"):
        semantic_svg = str(outputs.get(key) or "").replace("\\", "/")
        if _is_final_semantic_svg_path(semantic_svg):
            return True
    return False


def _svg_validation_ok(payload: Mapping[str, Any]) -> bool:
    validation = _json_stdout_object(payload)
    return isinstance(validation, Mapping) and validation.get("status") == "ok"


def _json_stdout_object(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    try:
        parsed = json.loads(str(payload.get("stdout") or "{}"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _targets_final_semantic_svg(args: Sequence[str]) -> bool:
    for index, arg in enumerate(args):
        if arg != "--svg" or index + 1 >= len(args):
            continue
        target = args[index + 1].replace("\\", "/")
        return _is_final_semantic_svg_path(target)
    return False


def _is_final_semantic_svg_path(path: str) -> bool:
    return path.endswith("/output/semantic.svg") or path == "output/semantic.svg" or path.endswith(
        "/output/semantic_svg.svg"
    ) or path == "output/semantic_svg.svg"


def _normalize_image_paths(image_paths: str | Path | Sequence[str | Path]) -> tuple[Path, ...]:
    if isinstance(image_paths, (str, Path)):
        return (Path(image_paths),)
    return tuple(Path(path) for path in image_paths)


def _image_trace(path: Path) -> Mapping[str, Any]:
    image_bytes = path.read_bytes()
    return {
        "image_path": str(path),
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "image_bytes": len(image_bytes),
    }


def _image_data_url(path: Path) -> tuple[str, Mapping[str, Any]]:
    image_bytes = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    image_bytes, mime_type, encoding = _maybe_compress_image(path, image_bytes, mime_type)
    with Image.open(path) as image:
        width, height = image.size
    return (
        f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}",
        {
            "width_px": width,
            "height_px": height,
            "mime_type": mime_type,
            "bytes": len(image_bytes),
            "encoding": encoding,
        },
    )


def _maybe_compress_image(path: Path, original_bytes: bytes, original_mime_type: str) -> tuple[bytes, str, str]:
    if len(original_bytes) <= MODEL_INPUT_JPEG_THRESHOLD_BYTES:
        return original_bytes, original_mime_type, "original"
    try:
        with Image.open(path) as image:
            rgb_image = _image_to_rgb(image)
            from io import BytesIO

            buffer = BytesIO()
            rgb_image.save(buffer, format="JPEG", quality=MODEL_INPUT_JPEG_QUALITY, optimize=True)
            jpeg_bytes = buffer.getvalue()
    except OSError:
        return original_bytes, original_mime_type, "original"
    if len(jpeg_bytes) >= len(original_bytes):
        return original_bytes, original_mime_type, "original"
    return jpeg_bytes, "image/jpeg", "jpeg_quality_90"


def _image_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def _bounded_int(value: Any, *, default: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    parsed = int(value)
    if parsed < 0:
        raise ValueError("integer value must be non-negative")
    return min(parsed, maximum)


def _prepend_pythonpath(path: Path, existing: str | None) -> str:
    value = str(path)
    if existing:
        return value + os.pathsep + existing
    return value


def _redact_command(command: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            redacted.append("[redacted]")
            skip_next = False
            continue
        lowered = item.lower()
        redacted.append(item)
        if lowered in {"--api-key", "--token", "--authorization"}:
            skip_next = True
    return redacted
