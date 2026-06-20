from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from . import model_runtime
from .codex_python_sdk_svg import (
    CODEX_SDK_SESSION_EVENT_SCHEMA,
    CODEX_SDK_TURN_RESULT_SCHEMA,
    _codex_sdk_env,
    _codex_sdk_jsonable,
    _isolated_codex_home,
    _load_openai_codex_sdk,
    _normalize_codex_model_name,
    _normalize_codex_reasoning_effort,
    _run_thread_with_timeout,
    _safe_error_text,
    controlled_codex_config_overrides,
)


CODEX_PYTHON_SDK_IMAGEGEN_RUNNER = "codex_python_sdk_imagegen"
CODEX_IMAGEGEN_RESULT_SCHEMA = "drawai.codex_python_sdk_imagegen_result.v1"
CODEX_IMAGEGEN_DEFAULT_REASONING_EFFORT = "low"
CODEX_IMAGEGEN_DEFAULT_TIMEOUT_SECONDS = 300.0


class CodexPythonSdkImageGenError(RuntimeError):
    """Raised when the controlled Codex Python SDK imagegen runner cannot produce an image."""


@dataclass(frozen=True)
class CodexGeneratedImage:
    image_id: str
    status: str
    path: Path
    source_path: str
    revised_prompt: str
    mime_type: str
    width: int
    height: int
    bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "status": self.status,
            "path": str(self.path),
            "source_path": self.source_path,
            "revised_prompt": self.revised_prompt,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "bytes": self.bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class CodexImageGenResult:
    schema: str
    runner: str
    task_name: str
    prompt: str
    final_response: str
    output_dir: Path
    trace_path: Path | None
    archive_dir: Path
    images: tuple[CodexGeneratedImage, ...]
    operation: str = "generate"
    source_image_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "runner": self.runner,
            "task_name": self.task_name,
            "operation": self.operation,
            "prompt": self.prompt,
            "source_image_path": str(self.source_image_path) if self.source_image_path is not None else None,
            "final_response": self.final_response,
            "output_dir": str(self.output_dir),
            "trace_path": str(self.trace_path) if self.trace_path is not None else None,
            "archive_dir": str(self.archive_dir),
            "images": [image.to_dict() for image in self.images],
        }


def invoke_codex_python_sdk_imagegen(
    *,
    prompt: str,
    output_dir: str | Path,
    task_name: str = "drawai.codex_imagegen.text_to_image.v1",
    output_stem: str = "codex-imagegen",
    runtime_config: Mapping[str, Any] | None = None,
    trace_path: str | Path | None = None,
    isolated_cwd: str | Path | None = None,
    config_overrides: Sequence[str] | None = None,
) -> CodexImageGenResult:
    return _invoke_codex_python_sdk_image_tool(
        operation="generate",
        prompt=prompt,
        source_image_path=None,
        output_dir=output_dir,
        task_name=task_name,
        output_stem=output_stem,
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=isolated_cwd,
        config_overrides=config_overrides,
    )


def invoke_codex_python_sdk_image_edit(
    *,
    source_image_path: str | Path,
    prompt: str,
    output_dir: str | Path,
    task_name: str = "drawai.codex_imagegen.edit.v1",
    output_stem: str = "codex-image-edit",
    runtime_config: Mapping[str, Any] | None = None,
    trace_path: str | Path | None = None,
    isolated_cwd: str | Path | None = None,
    config_overrides: Sequence[str] | None = None,
) -> CodexImageGenResult:
    source_path = _normalize_source_image_path(source_image_path)
    return _invoke_codex_python_sdk_image_tool(
        operation="edit",
        prompt=prompt,
        source_image_path=source_path,
        output_dir=output_dir,
        task_name=task_name,
        output_stem=output_stem,
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=isolated_cwd,
        config_overrides=config_overrides,
    )


def _invoke_codex_python_sdk_image_tool(
    *,
    operation: str,
    prompt: str,
    source_image_path: Path | None,
    output_dir: str | Path,
    task_name: str,
    output_stem: str,
    runtime_config: Mapping[str, Any] | None,
    trace_path: str | Path | None,
    isolated_cwd: str | Path | None,
    config_overrides: Sequence[str] | None,
) -> CodexImageGenResult:
    normalized_prompt = _normalize_prompt(prompt)
    output_root = Path(output_dir).expanduser().resolve(strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    trace = Path(trace_path).expanduser().resolve(strict=False) if trace_path is not None else None
    if trace is not None:
        trace.parent.mkdir(parents=True, exist_ok=True)

    runtime_settings = _imagegen_runtime_settings(runtime_config)
    model_name = _normalize_codex_model_name(runtime_settings.get("model_name"))
    reasoning_effort = _normalize_codex_reasoning_effort(
        runtime_settings.get("reasoning_effort", runtime_settings.get("model_reasoning_effort"))
    )
    timeout_seconds = model_runtime._runtime_timeout_seconds(runtime_settings)
    sdk = _load_openai_codex_sdk()

    with _imagegen_run_cwd(isolated_cwd) as run_cwd:
        with _isolated_codex_home(run_cwd) as prepared_codex_home:
            overrides = controlled_codex_config_overrides(
                ("features.image_generation=true", *(config_overrides or ()))
            )
            with sdk.Codex(
                sdk.CodexConfig(
                    cwd=str(run_cwd),
                    config_overrides=overrides,
                    env=_codex_sdk_env(prepared_codex_home.codex_home),
                )
            ) as codex:
                capabilities = _read_model_provider_capabilities(codex)
                if not _capability_enabled(capabilities, "image_generation"):
                    raise CodexPythonSdkImageGenError(
                        "Codex SDK model provider does not report image_generation capability"
                    )
                thread = codex.thread_start(
                    approval_mode=sdk.ApprovalMode.deny_all,
                    config={"model_reasoning_effort": reasoning_effort},
                    cwd=str(run_cwd),
                    developer_instructions=_imagegen_developer_instructions(operation),
                    ephemeral=True,
                    model=model_name,
                    sandbox=sdk.Sandbox.full_access,
                )
                thread_id = str(getattr(thread, "id", "") or "")
                model_runtime._append_trace(
                    trace,
                    {
                        "type": "codex_python_sdk_imagegen_request",
                        "runner": CODEX_PYTHON_SDK_IMAGEGEN_RUNNER,
                        "task_name": task_name,
                        "thread_id": thread_id or None,
                        "model_name": model_name or "codex-default",
                        "reasoning_effort": reasoning_effort,
                        "timeout_seconds": timeout_seconds,
                        "operation": operation,
                        "prompt_chars": len(normalized_prompt),
                        "prompt_sha256": hashlib.sha256(normalized_prompt.encode("utf-8")).hexdigest(),
                        "source_image_path": str(source_image_path) if source_image_path is not None else None,
                        "output_dir": str(output_root),
                        "isolated_cwd": str(run_cwd),
                        "codex_home": prepared_codex_home.to_trace(),
                        "config_overrides": list(overrides),
                        "capabilities": capabilities,
                    },
                )

                started_at = time.monotonic()
                result: Any | None = None
                try:
                    result = _run_thread_with_timeout(
                        thread,
                        _imagegen_turn_input(
                            sdk,
                            operation=operation,
                            prompt=normalized_prompt,
                            source_image_path=source_image_path,
                        ),
                        timeout_seconds=timeout_seconds,
                        approval_mode=sdk.ApprovalMode.deny_all,
                        cwd=str(run_cwd),
                        effort=reasoning_effort,
                        model=model_name,
                        sandbox=sdk.Sandbox.full_access,
                    )
                except CodexPythonSdkImageGenError as exc:
                    _append_imagegen_error_trace(trace, task_name=task_name, started_at=started_at, exc=exc)
                    raise
                except Exception as exc:
                    _append_imagegen_error_trace(trace, task_name=task_name, started_at=started_at, exc=exc)
                    raise CodexPythonSdkImageGenError(
                        f"Codex Python SDK image {operation} failed: {_safe_error_text(str(exc))}"
                    ) from exc

                image_items = _image_generation_items(getattr(result, "items", []) or [])
                if not image_items:
                    exc = CodexPythonSdkImageGenError(
                        "Codex SDK turn did not produce an imageGeneration item"
                    )
                    _append_imagegen_error_trace(trace, task_name=task_name, started_at=started_at, exc=exc)
                    raise exc

                images = tuple(
                    _materialize_image_item(
                        item,
                        output_dir=output_root,
                        output_stem=output_stem,
                        index=index,
                    )
                    for index, item in enumerate(image_items, start=1)
                )
                archive_dir = output_root / "codex_session_log"
                _write_imagegen_turn_archive(
                    result,
                    archive_dir,
                    task_name=task_name,
                )
                final_response = str(getattr(result, "final_response", "") or "")
                imagegen_result = CodexImageGenResult(
                    schema=CODEX_IMAGEGEN_RESULT_SCHEMA,
                    runner=CODEX_PYTHON_SDK_IMAGEGEN_RUNNER,
                    task_name=task_name,
                    prompt=normalized_prompt,
                    final_response=final_response,
                    output_dir=output_root,
                    trace_path=trace,
                    archive_dir=archive_dir,
                    images=images,
                    operation=operation,
                    source_image_path=source_image_path,
                )
                summary_path = output_root / "codex_imagegen_result.json"
                summary_path.write_text(
                    json.dumps(imagegen_result.to_dict(), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                model_runtime._append_trace(
                    trace,
                    {
                        "type": "codex_python_sdk_imagegen_response",
                        "runner": CODEX_PYTHON_SDK_IMAGEGEN_RUNNER,
                        "task_name": task_name,
                        "thread_id": thread_id or None,
                        "operation": operation,
                        "duration_ms": int((time.monotonic() - started_at) * 1000),
                        "final_response_excerpt": final_response[:2000],
                        "image_count": len(images),
                        "images": [image.to_dict() for image in images],
                        "archive_dir": str(archive_dir),
                        "summary_path": str(summary_path),
                    },
                )
                return imagegen_result


def check_codex_python_sdk_imagegen_capability(
    *,
    timeout_seconds: float = 45.0,
    isolated_cwd: str | Path | None = None,
) -> dict[str, Any]:
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise CodexPythonSdkImageGenError("timeout_seconds must be positive")
    sdk = _load_openai_codex_sdk()
    with _imagegen_run_cwd(isolated_cwd) as run_cwd:
        with _isolated_codex_home(run_cwd) as prepared_codex_home:
            with sdk.Codex(
                sdk.CodexConfig(
                    cwd=str(run_cwd),
                    config_overrides=controlled_codex_config_overrides(
                        ("features.image_generation=true",)
                    ),
                    env=_codex_sdk_env(prepared_codex_home.codex_home),
                )
            ) as codex:
                started_at = time.monotonic()
                capabilities = _read_model_provider_capabilities(codex)
                capabilities["probe_duration_ms"] = int((time.monotonic() - started_at) * 1000)
                return capabilities


@contextmanager
def _imagegen_run_cwd(path: str | Path | None):
    if path is not None:
        run_cwd = Path(path).expanduser().resolve(strict=False)
        run_cwd.mkdir(parents=True, exist_ok=True)
        yield run_cwd
        return
    with tempfile.TemporaryDirectory(
        prefix="drawai-codex-imagegen-cwd-",
        ignore_cleanup_errors=True,
    ) as temporary_dir:
        yield Path(temporary_dir).resolve(strict=True)


def _imagegen_runtime_settings(runtime_config: Mapping[str, Any] | None) -> dict[str, Any]:
    settings = dict(runtime_config or {})
    settings.setdefault("timeout_seconds", CODEX_IMAGEGEN_DEFAULT_TIMEOUT_SECONDS)
    settings.setdefault("reasoning_effort", CODEX_IMAGEGEN_DEFAULT_REASONING_EFFORT)
    return settings


def _normalize_prompt(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        raise CodexPythonSdkImageGenError("prompt is required")
    return text


def _normalize_source_image_path(path: str | Path) -> Path:
    source_path = Path(path).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise CodexPythonSdkImageGenError(f"source_image_path does not exist or is not a file: {source_path}")
    return source_path


def _read_model_provider_capabilities(codex: Any) -> dict[str, Any]:
    sdk = _load_openai_codex_sdk()
    response_model = sdk.generated.v2_all.ModelProviderCapabilitiesReadResponse
    capabilities = codex._client.request(
        "modelProvider/capabilities/read",
        {},
        response_model=response_model,
    )
    payload = _codex_sdk_jsonable(capabilities)
    if not isinstance(payload, Mapping):
        raise CodexPythonSdkImageGenError("Codex capabilities response must be an object")
    return dict(payload)


def _capability_enabled(capabilities: Mapping[str, Any], python_name: str) -> bool:
    camel_name = re.sub(r"_([a-z])", lambda match: match.group(1).upper(), python_name)
    return capabilities.get(python_name) is True or capabilities.get(camel_name) is True


def _imagegen_developer_instructions(operation: str) -> str:
    if operation == "edit":
        return (
            "Internal DrawAI image editing runner.\n"
            "When the user provides an image input and edit prompt, use the built-in image generation tool exactly once "
            "to edit the supplied image. Do not treat filesystem paths written in text as image inputs. "
            "Do not call OpenAI Images API manually, do not use shell commands, do not use web search, "
            "and do not use MCP tools or multi-agent delegation. The imageGeneration thread item is the source of truth. "
            "After the tool finishes, reply with compact JSON only."
        )
    return (
        "Internal DrawAI text-to-image runner.\n"
        "When the user provides an image prompt, use the built-in image generation tool exactly once. "
        "Do not call OpenAI Images API manually, do not use shell commands, do not use web search, "
        "and do not use MCP tools or multi-agent delegation. The imageGeneration thread item is the source of truth. "
        "After the tool finishes, reply with compact JSON only."
    )


def _imagegen_turn_input(
    sdk: Any,
    *,
    operation: str,
    prompt: str,
    source_image_path: Path | None,
) -> list[Any]:
    if operation == "edit":
        if source_image_path is None:
            raise CodexPythonSdkImageGenError("source_image_path is required for image edit")
        return [
            sdk.LocalImageInput(str(source_image_path)),
            sdk.TextInput(_image_edit_user_prompt(prompt)),
        ]
    return [sdk.TextInput(_imagegen_user_prompt(prompt))]


def _imagegen_user_prompt(prompt: str) -> str:
    return (
        "Generate one image from this prompt using the built-in image generation tool.\n\n"
        f"Image prompt:\n{prompt}\n\n"
        'Final response contract: reply only {"generated": true}.'
    )


def _image_edit_user_prompt(prompt: str) -> str:
    return (
        "Edit the supplied image using the built-in image generation tool.\n\n"
        f"Edit prompt:\n{prompt}\n\n"
        'Final response contract: reply only {"edited": true}.'
    )


def _image_generation_items(items: Sequence[Any]) -> list[Any]:
    image_items: list[Any] = []
    for item in items:
        payload = item.root if hasattr(item, "root") else item
        item_type = getattr(payload, "type", None)
        item_type_value = getattr(item_type, "value", item_type)
        if item_type_value == "imageGeneration":
            image_items.append(payload)
    return image_items


def _materialize_image_item(
    item: Any,
    *,
    output_dir: Path,
    output_stem: str,
    index: int,
) -> CodexGeneratedImage:
    image_id = str(getattr(item, "id", "") or f"image-{index}")
    status = str(getattr(item, "status", "") or "")
    revised_prompt = str(getattr(item, "revised_prompt", "") or "")
    source_path_value = getattr(item, "saved_path", None) or getattr(item, "savedPath", None)
    result = str(getattr(item, "result", "") or "")
    source_path = _sdk_saved_path(source_path_value)

    suffix = _image_suffix(source_path, result)
    destination = _next_available_path(output_dir / f"{_safe_output_stem(output_stem)}{'' if index == 1 else f'-{index}'}{suffix}")
    if source_path is not None and source_path.is_file():
        shutil.copy2(source_path, destination)
    elif result:
        destination.write_bytes(_decode_image_result(result))
    else:
        raise CodexPythonSdkImageGenError(
            f"imageGeneration item {image_id!r} had neither savedPath nor base64 result"
        )

    image_bytes = destination.read_bytes()
    with Image.open(destination) as image:
        width, height = image.size
        image_format = str(image.format or "").lower()
    mime_type = mimetypes.guess_type(destination.name)[0] or (
        f"image/{image_format}" if image_format else "application/octet-stream"
    )
    return CodexGeneratedImage(
        image_id=image_id,
        status=status,
        path=destination,
        source_path=str(source_path) if source_path is not None else "result_base64",
        revised_prompt=revised_prompt,
        mime_type=mime_type,
        width=width,
        height=height,
        bytes=len(image_bytes),
        sha256=hashlib.sha256(image_bytes).hexdigest(),
    )


def _image_suffix(source_path: Path | None, result: str) -> str:
    if source_path is not None and source_path.suffix:
        return source_path.suffix.lower()
    if result.startswith("data:"):
        mime_type = result.split(";", 1)[0].removeprefix("data:")
        suffix = mimetypes.guess_extension(mime_type)
        if suffix:
            return suffix
    return ".png"


def _sdk_saved_path(value: Any) -> Path | None:
    if not value:
        return None
    raw_value = getattr(value, "root", value)
    try:
        path_text = os.fspath(raw_value)
    except TypeError:
        path_text = str(raw_value)
    if not path_text.strip():
        return None
    return Path(path_text).expanduser().resolve(strict=False)


def _decode_image_result(result: str) -> bytes:
    payload = result.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")
    try:
        return base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise CodexPythonSdkImageGenError("imageGeneration result was not valid base64") from exc


def _safe_output_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return stem or "codex-imagegen"


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10_000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise CodexPythonSdkImageGenError(f"could not choose a free output path near {path}")


def _write_imagegen_turn_archive(result: Any, archive_dir: Path, *, task_name: str) -> None:
    if archive_dir.exists():
        shutil.rmtree(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    items = list(getattr(result, "items", []) or [])
    summary = {
        "schema": CODEX_SDK_TURN_RESULT_SCHEMA,
        "task_name": task_name,
        "turn_id": getattr(result, "id", None),
        "status": _codex_sdk_jsonable(getattr(result, "status", None)),
        "started_at": getattr(result, "started_at", None),
        "completed_at": getattr(result, "completed_at", None),
        "duration_ms": getattr(result, "duration_ms", None),
        "final_response": getattr(result, "final_response", None),
        "item_count": len(items),
        "usage": _codex_sdk_jsonable(getattr(result, "usage", None)),
        "raw_image_base64_omitted": True,
    }
    (archive_dir / "turn_result_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    events_path = archive_dir / "codex_session_events.jsonl"
    with events_path.open("w", encoding="utf-8") as handle:
        for index, item in enumerate(items, start=1):
            event = {
                "schema": CODEX_SDK_SESSION_EVENT_SCHEMA,
                "task_name": task_name,
                "turn_id": getattr(result, "id", None),
                "index": index,
                "item": _sanitize_sdk_item_for_archive(item),
            }
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema": "drawai.codex_imagegen_session_archive.v1",
        "task_name": task_name,
        "archive_dir": str(archive_dir),
        "summary_file": "turn_result_summary.json",
        "events_file": events_path.name,
        "event_count": len(items),
        "raw_codex_logs_copied": False,
        "raw_image_base64_omitted": True,
    }
    (archive_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sanitize_sdk_item_for_archive(item: Any) -> Any:
    payload = item.root if hasattr(item, "root") else item
    data = _codex_sdk_jsonable(payload)
    if not isinstance(data, dict):
        return data
    item_type = data.get("type")
    if item_type != "imageGeneration":
        return data
    result = data.get("result")
    if isinstance(result, str):
        data["result"] = {
            "base64_chars": len(result),
            "sha256": hashlib.sha256(result.encode("utf-8")).hexdigest(),
            "omitted": True,
        }
    return data


def _append_imagegen_error_trace(
    trace: Path | None,
    *,
    task_name: str,
    started_at: float,
    exc: BaseException,
) -> None:
    model_runtime._append_trace(
        trace,
        {
            "type": "codex_python_sdk_imagegen_error",
            "runner": CODEX_PYTHON_SDK_IMAGEGEN_RUNNER,
            "task_name": task_name,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "error_type": type(exc).__name__,
            "error": _safe_error_text(str(exc)),
        },
    )
