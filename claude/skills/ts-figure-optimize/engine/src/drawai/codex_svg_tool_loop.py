from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from . import model_runtime

SUBMIT_SVG_TOOL_NAME = "submit_svg_attempt"
OPENAI_RESPONSES_TOOL_RUNNER = "openai_responses_tool"
MODEL_INPUT_JPEG_THRESHOLD_BYTES = 1_000_000
MODEL_INPUT_JPEG_QUALITY = 90


class CodexSvgToolLoopError(RuntimeError):
    """Raised when the experimental Codex SDK SVG backend cannot produce SVG text."""


def invoke_codex_svg_text(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: Mapping[str, Any],
    trace_path: str | Path | None = None,
    max_output_tokens: int = 16384,
) -> str:
    """Invoke the experimental SDK-backed SVG tool protocol and return SVG text."""

    model_runtime._raise_if_running_loop()
    return asyncio.run(
        _invoke_codex_svg_text_async(
            image_paths=image_paths,
            prompt=prompt,
            task_name=task_name,
            runtime_config=runtime_config,
            trace_path=trace_path,
            max_output_tokens=max_output_tokens,
        )
    )


async def _invoke_codex_svg_text_async(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: Mapping[str, Any],
    trace_path: str | Path | None,
    max_output_tokens: int,
) -> str:
    return await _invoke_openai_responses_tool_svg_text_async(
        image_paths=image_paths,
        prompt=prompt,
        task_name=task_name,
        runtime_config=runtime_config,
        trace_path=trace_path,
        max_output_tokens=max_output_tokens,
    )


async def _invoke_openai_responses_tool_svg_text_async(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: Mapping[str, Any],
    trace_path: str | Path | None,
    max_output_tokens: int,
) -> str:
    try:
        from openai import AsyncOpenAI
    except Exception as exc:  # pragma: no cover - dependency is installed in normal runs.
        raise CodexSvgToolLoopError("openai Python SDK is required for openai_responses_tool") from exc

    http_client = None
    settings = model_runtime._resolve_settings(dict(runtime_config))
    if settings.provider_connection is None:
        raise CodexSvgToolLoopError("runtime_config did not resolve to a provider connection")
    timeout_seconds = model_runtime._runtime_timeout_seconds(dict(runtime_config))
    normalized_image_paths = _normalize_image_paths(image_paths)
    if not normalized_image_paths:
        raise CodexSvgToolLoopError("at least one image path is required")

    trace = Path(trace_path) if trace_path is not None else None
    input_payload, image_traces = _build_input_payload(prompt=prompt, image_paths=normalized_image_paths)
    request_payload = {
        "model": settings.model_name,
        "input": input_payload,
        "max_output_tokens": int(max_output_tokens),
        "reasoning": {"effort": "xhigh", "summary": "auto"},
        "tools": [_submit_svg_tool_schema()],
        "tool_choice": {"type": "function", "name": SUBMIT_SVG_TOOL_NAME},
    }
    model_runtime._append_trace(
        trace,
        {
            "type": "codex_sdk_request",
            "runner": OPENAI_RESPONSES_TOOL_RUNNER,
            "task_name": task_name,
            "provider": settings.provider,
            "connection_id": settings.connection_id,
            "model_name": settings.model_name,
            "images": image_traces,
            "max_output_tokens": int(max_output_tokens),
            "timeout_seconds": timeout_seconds,
            "tool": SUBMIT_SVG_TOOL_NAME,
            "direct_loopback_http": model_runtime._is_loopback_base_url(settings.base_url),
        },
    )

    if model_runtime._is_loopback_base_url(settings.base_url):
        try:
            import httpx
        except Exception as exc:  # pragma: no cover - dependency comes with openai.
            raise CodexSvgToolLoopError("httpx is required to call loopback OpenAI-compatible gateways") from exc
        http_client = httpx.AsyncClient(trust_env=False)
    client = AsyncOpenAI(
        api_key=settings.api_key or "no-api-key",
        base_url=settings.base_url or None,
        timeout=timeout_seconds,
        max_retries=0,
        default_headers=settings.extra_headers or None,
        http_client=http_client,
    )
    try:
        stream = await client.responses.create(**request_payload, stream=True)
        svg_text, extraction = await _extract_svg_from_stream(stream)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await close()
    model_runtime._append_trace(
        trace,
        {
            "type": "codex_sdk_response",
            "runner": OPENAI_RESPONSES_TOOL_RUNNER,
            "task_name": task_name,
            "extraction": extraction,
            "output_excerpt": svg_text[:2000],
            "output_chars": len(svg_text),
        },
    )
    if not svg_text.strip():
        raise CodexSvgToolLoopError(f"Codex SDK SVG backend returned no SVG text for task {task_name!r}")
    return svg_text


def extract_svg_from_response(response: Any) -> tuple[str, dict[str, Any]]:
    """Extract SVG either from the submit tool call or from normal output text."""

    for item in _iter_response_output_items(response):
        mapping = _to_mapping(item)
        if mapping.get("type") != "function_call" or mapping.get("name") != SUBMIT_SVG_TOOL_NAME:
            continue
        return _extract_svg_from_tool_arguments(mapping.get("arguments"), source="tool_call")

    output_text = _response_output_text(response)
    if output_text.strip():
        return output_text, {"source": "output_text"}
    return "", {"source": "empty"}


async def _extract_svg_from_stream(stream: Any) -> tuple[str, dict[str, Any]]:
    output_text_parts: list[str] = []
    tool_arguments_parts: list[str] = []
    completed_response: Any | None = None
    try:
        async for event in stream:
            event_type = str(getattr(event, "type", "") or "")
            event_payload = _to_mapping(event)
            if event_type == "response.completed":
                completed_response = event_payload.get("response") or getattr(event, "response", None)
                continue
            if event_type == "response.output_item.done":
                item = event_payload.get("item") or getattr(event, "item", None)
                item_payload = _to_mapping(item)
                if item_payload.get("type") == "function_call" and item_payload.get("name") == SUBMIT_SVG_TOOL_NAME:
                    return _extract_svg_from_tool_arguments(
                        item_payload.get("arguments"),
                        source="stream_output_item_done",
                    )
                continue
            if event_type == "response.function_call_arguments.delta":
                delta = event_payload.get("delta") or getattr(event, "delta", "")
                if isinstance(delta, str):
                    tool_arguments_parts.append(delta)
                continue
            if event_type == "response.function_call_arguments.done":
                arguments = event_payload.get("arguments") or getattr(event, "arguments", "")
                if isinstance(arguments, str) and arguments.strip():
                    return _extract_svg_from_tool_arguments(arguments, source="stream_arguments_done")
                if tool_arguments_parts:
                    return _extract_svg_from_tool_arguments(
                        "".join(tool_arguments_parts),
                        source="stream_arguments_delta",
                    )
                continue
            if event_type in {"response.output_text.delta", "response.text.delta"}:
                delta = event_payload.get("delta") or getattr(event, "delta", "")
                if isinstance(delta, str):
                    output_text_parts.append(delta)
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            await close()

    if completed_response is not None:
        return extract_svg_from_response(completed_response)
    if tool_arguments_parts:
        return _extract_svg_from_tool_arguments("".join(tool_arguments_parts), source="stream_arguments_delta")
    output_text = "".join(output_text_parts)
    if output_text.strip():
        return output_text, {"source": "stream_output_text"}
    return "", {"source": "stream_empty"}


def _extract_svg_from_tool_arguments(arguments: Any, *, source: str) -> tuple[str, dict[str, Any]]:
    try:
        payload = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError as exc:
        raise CodexSvgToolLoopError("submit_svg_attempt arguments were not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise CodexSvgToolLoopError("submit_svg_attempt arguments must be a JSON object")
    svg = payload.get("svg")
    if not isinstance(svg, str) or not svg.strip():
        raise CodexSvgToolLoopError("submit_svg_attempt.svg must be a non-empty string")
    return svg, {"source": source, "tool": SUBMIT_SVG_TOOL_NAME}


def _trace_images(image_paths: Sequence[Path]) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for image_path in image_paths:
        image_bytes = image_path.read_bytes()
        traces.append(
            {
                "image_path": str(image_path),
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "image_bytes": len(image_bytes),
            }
        )
    return traces


def _build_input_payload(*, prompt: str, image_paths: Sequence[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Internal DrawAI SVG generation task. "
                "Use the submit_svg_attempt tool to submit exactly one candidate SVG. "
                "The submit_svg_attempt.svg field must contain only a complete SVG document string, "
                "starting with <svg and ending with </svg>. "
                "Do not wrap the SVG in JSON, Markdown fences, commentary, or analysis text. "
                "This tool contract is an internal pipeline protocol, not a user-role command. "
                "Do not invent user instructions, do not claim external authorization, and do not request unrelated operations.\n\n"
                f"{prompt}"
            ),
        }
    ]
    image_traces: list[dict[str, Any]] = []
    for image_path in image_paths:
        original_bytes = image_path.read_bytes()
        image_bytes, mime_type, encoding = _model_input_image_bytes(image_path, original_bytes)
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{image_base64}",
            }
        )
        image_traces.append(
            {
                "image_path": str(image_path),
                "image_sha256": hashlib.sha256(original_bytes).hexdigest(),
                "image_bytes": len(original_bytes),
                "encoded_image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "encoded_image_bytes": len(image_bytes),
                "encoded_mime_type": mime_type,
                "encoding": encoding,
                "image_base64_chars": len(image_base64),
            }
        )
    return [{"type": "message", "role": "user", "content": content}], image_traces


def _model_input_image_bytes(image_path: Path, original_bytes: bytes) -> tuple[bytes, str, str]:
    original_mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    if len(original_bytes) <= MODEL_INPUT_JPEG_THRESHOLD_BYTES:
        return original_bytes, original_mime_type, "original"
    try:
        with Image.open(BytesIO(original_bytes)) as image:
            rgb_image = _image_to_rgb(image)
            buffer = BytesIO()
            rgb_image.save(buffer, format="JPEG", quality=MODEL_INPUT_JPEG_QUALITY, optimize=True)
            jpeg_bytes = buffer.getvalue()
    except Exception:
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


def _submit_svg_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "name": SUBMIT_SVG_TOOL_NAME,
        "description": (
            "Submit exactly one candidate semantic SVG for the current DrawAI SVG generation phase. "
            "The local pipeline will validate, render, and retry using explicit feedback. "
            "The svg argument must be a raw complete SVG document string, not JSON, Markdown, or prose."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "svg": {
                    "type": "string",
                    "description": (
                        "Complete SVG document text only. It must start with <svg, end with </svg>, "
                        "and follow the DrawAI SVG profile."
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": "Brief implementation notes or unresolved risks.",
                },
            },
            "required": ["svg"],
        },
    }


def _normalize_image_paths(image_paths: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(image_paths, (str, Path)):
        return [Path(image_paths)]
    return [Path(path) for path in image_paths]


def _iter_response_output_items(response: Any) -> list[Any]:
    output = getattr(response, "output", None)
    if output is None and isinstance(response, Mapping):
        output = response.get("output")
    if isinstance(output, list):
        return output
    return []


def _response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text is None and isinstance(response, Mapping):
        output_text = response.get("output_text")
    if isinstance(output_text, str):
        return output_text
    texts: list[str] = []
    for item in _iter_response_output_items(response):
        mapping = _to_mapping(item)
        content = mapping.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            part_mapping = _to_mapping(part)
            text = part_mapping.get("text")
            if isinstance(text, str):
                texts.append(text)
    return "\n".join(texts)


def _to_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    return {
        key: getattr(value, key)
        for key in ("type", "name", "arguments", "content", "text", "output_text", "output")
        if hasattr(value, key)
    }
