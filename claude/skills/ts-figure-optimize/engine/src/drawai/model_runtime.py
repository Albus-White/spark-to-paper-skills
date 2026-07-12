from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
from ipaddress import ip_address
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


class ModelRuntimeError(ValueError):
    """Raised when the DrawAI model runtime cannot invoke a vision model."""


RATE_LIMIT_RETRY_DELAYS_SECONDS = (10.0, 30.0, 60.0)
_MAX_TOKENS_RANGE_RE = re.compile(r"Range of max_tokens should be \[1,\s*(\d+)\]", re.IGNORECASE)
_MAX_TOKENS_AT_MOST_RE = re.compile(
    r"(?:max_output_tokens|max_tokens)[^\d]{0,80}(?:<=|at most|less than or equal to|should be)\s*(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProviderConnection:
    connection_id: str
    provider_type: str
    base_url: str = ""
    api_key: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeSettings:
    provider: str
    api_key: str
    model_name: str
    image_model_name: str = ""
    base_url: str = ""
    connection_id: str = ""
    provider_connection: ProviderConnection | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    concurrency_mode: str = "auto"
    max_concurrent: int = 20
    max_critic_rounds: int = 3
    wire_api: str = "responses"
    extra_body: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "api_key": self.api_key,
            "model_name": self.model_name,
            "image_model_name": self.image_model_name,
            "base_url": self.base_url,
            "connection_id": self.connection_id,
            "extra_headers": dict(self.extra_headers),
            "concurrency_mode": self.concurrency_mode,
            "max_concurrent": self.max_concurrent,
            "max_critic_rounds": self.max_critic_rounds,
            "wire_api": self.wire_api,
            "extra_body": dict(self.extra_body),
        }


def invoke_vision_text(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: RuntimeSettings | dict[str, Any] | None = None,
    trace_path: str | Path | None = None,
    max_output_tokens: int = 4096,
) -> str:
    normalized_image_paths = _normalize_image_paths(image_paths)
    if not normalized_image_paths:
        raise ModelRuntimeError("at least one image path is required for vision invocation")
    return invoke_multimodal_text(
        image_paths=normalized_image_paths,
        prompt=prompt,
        task_name=task_name,
        runtime_config=runtime_config,
        trace_path=trace_path,
        max_output_tokens=max_output_tokens,
    )


def invoke_multimodal_text(
    *,
    image_paths: str | Path | Sequence[str | Path] = (),
    prompt: str,
    task_name: str,
    runtime_config: RuntimeSettings | dict[str, Any] | None = None,
    trace_path: str | Path | None = None,
    max_output_tokens: int = 4096,
) -> str:
    if runtime_config is None:
        raise ModelRuntimeError(
            "runtime_config is required for DrawAI model runtime usage without an injected invoker"
        )
    normalized_image_paths = _normalize_image_paths(image_paths)
    resolved_settings = _resolve_settings(runtime_config)
    direct_output = _runtime_direct_output(runtime_config)
    settings_attempts = (
        _direct_output_settings_attempts(resolved_settings)
        if direct_output
        else (resolved_settings,)
    )
    settings = settings_attempts[0]
    if settings.provider_connection is None:
        raise ModelRuntimeError("runtime_config did not resolve to a provider connection")
    timeout_seconds = _runtime_timeout_seconds(runtime_config)

    input_content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    image_traces: list[dict[str, Any]] = []
    for image_path in normalized_image_paths:
        image_bytes = image_path.read_bytes()
        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        input_content.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{image_base64}",
            }
        )
        image_traces.append(
            {
                "image_path": str(image_path),
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "image_bytes": len(image_bytes),
                "image_base64_chars": len(image_base64),
            }
        )
    trace = Path(trace_path) if trace_path is not None else None
    _raise_if_running_loop()
    output = ""
    for attempt_index, attempt_settings in enumerate(settings_attempts, start=1):
        _append_trace(
            trace,
            {
                "type": "request",
                "task_name": task_name,
                "provider": attempt_settings.provider,
                "connection_id": attempt_settings.connection_id,
                "model_name": attempt_settings.model_name,
                "wire_api": attempt_settings.wire_api,
                "direct_output": direct_output,
                "attempt": attempt_index,
                "attempts": len(settings_attempts),
                "extra_body": attempt_settings.extra_body,
                "images": image_traces,
                "max_output_tokens": int(max_output_tokens),
                "timeout_seconds": timeout_seconds,
            },
        )
        output = _invoke_provider_sync(
            settings=attempt_settings,
            input_content=input_content,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            task_name=task_name,
            trace_path=trace,
        )
        if output and output.strip():
            break
        _append_trace(
            trace,
            {
                "type": "empty_response",
                "task_name": task_name,
                "attempt": attempt_index,
                "attempts": len(settings_attempts),
            },
        )
    if not output or not output.strip():
        raise ModelRuntimeError(f"model returned no text output for task {task_name!r}")
    _append_trace(
        trace,
        {
            "type": "response",
            "task_name": task_name,
            "output_excerpt": output[:2000],
            "output_chars": len(output),
        },
    )
    return output


def _invoke_provider_sync(
    *,
    settings: RuntimeSettings,
    input_content: list[dict[str, Any]],
    max_output_tokens: int,
    timeout_seconds: float,
    task_name: str,
    trace_path: Path | None,
) -> str:
    effective_max_output_tokens = int(max_output_tokens)
    rate_limit_retry_count = 0
    provider_retry_count = 0
    while True:
        try:
            if settings.wire_api == "chat_completions":
                return asyncio.run(
                    _invoke_openai_compatible_chat_completion(
                        settings=settings,
                        input_content=input_content,
                        max_output_tokens=effective_max_output_tokens,
                        timeout_seconds=timeout_seconds,
                        task_name=task_name,
                        trace_path=trace_path,
                    )
                )
            return asyncio.run(
                _invoke_openai_compatible_response(
                    settings=settings,
                    input_content=input_content,
                    max_output_tokens=effective_max_output_tokens,
                    timeout_seconds=timeout_seconds,
                    task_name=task_name,
                    trace_path=trace_path,
                )
            )
        except Exception as exc:
            token_cap = _max_output_token_cap_from_error(exc)
            if token_cap is not None and effective_max_output_tokens > token_cap:
                _append_trace(
                    trace_path,
                    {
                        "type": "provider_retry",
                        "task_name": task_name,
                        "reason": "max_output_tokens_cap",
                        "retry": provider_retry_count + 1,
                        "previous_max_output_tokens": effective_max_output_tokens,
                        "next_max_output_tokens": token_cap,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                effective_max_output_tokens = token_cap
                provider_retry_count += 1
                continue
            if (
                _is_retryable_rate_limit(exc)
                and rate_limit_retry_count < len(RATE_LIMIT_RETRY_DELAYS_SECONDS)
            ):
                delay_seconds = RATE_LIMIT_RETRY_DELAYS_SECONDS[rate_limit_retry_count]
                _append_trace(
                    trace_path,
                    {
                        "type": "provider_retry",
                        "task_name": task_name,
                        "reason": "rate_limit",
                        "retry": provider_retry_count + 1,
                        "delay_seconds": delay_seconds,
                        "max_output_tokens": effective_max_output_tokens,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                time.sleep(delay_seconds)
                rate_limit_retry_count += 1
                provider_retry_count += 1
                continue
            raise ModelRuntimeError(
                f"model provider call failed for task {task_name!r}: {exc}"
            ) from exc


async def _invoke_openai_compatible_response(
    *,
    settings: RuntimeSettings,
    input_content: list[dict[str, Any]],
    max_output_tokens: int,
    timeout_seconds: float,
    task_name: str = "",
    trace_path: Path | None = None,
) -> str:
    try:
        from openai import AsyncOpenAI
    except Exception as exc:  # pragma: no cover - dependency is installed for normal runs.
        raise ModelRuntimeError("openai Python SDK is required for model_runtime responses calls") from exc

    http_client = None
    if _is_loopback_base_url(settings.base_url):
        try:
            import httpx
        except Exception as exc:  # pragma: no cover - dependency comes with openai.
            raise ModelRuntimeError("httpx is required for loopback OpenAI-compatible gateways") from exc
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
        response = await client.responses.create(
            model=settings.model_name,
            input=[{"role": "user", "content": input_content}],
            max_output_tokens=int(max_output_tokens),
        )
        _append_provider_response(
            trace_path,
            {
                "type": "provider_response",
                "task_name": task_name,
                "wire_api": settings.wire_api,
                "model_name": settings.model_name,
                "response": response,
            },
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await close()

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str) and text.strip():
                return text
    return ""


async def _invoke_openai_compatible_chat_completion(
    *,
    settings: RuntimeSettings,
    input_content: list[dict[str, Any]],
    max_output_tokens: int,
    timeout_seconds: float,
    task_name: str = "",
    trace_path: Path | None = None,
) -> str:
    try:
        from openai import AsyncOpenAI
    except Exception as exc:  # pragma: no cover - dependency is installed for normal runs.
        raise ModelRuntimeError("openai Python SDK is required for model_runtime chat completion calls") from exc

    http_client = None
    if _is_loopback_base_url(settings.base_url):
        try:
            import httpx
        except Exception as exc:  # pragma: no cover - dependency comes with openai.
            raise ModelRuntimeError("httpx is required for loopback OpenAI-compatible gateways") from exc
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
        request_payload: dict[str, Any] = {
            "model": settings.model_name,
            "messages": [{"role": "user", "content": _chat_message_content(input_content)}],
            "max_tokens": int(max_output_tokens),
        }
        if settings.extra_body:
            request_payload["extra_body"] = settings.extra_body
        response = await client.chat.completions.create(**request_payload)
        _append_provider_response(
            trace_path,
            {
                "type": "provider_response",
                "task_name": task_name,
                "wire_api": settings.wire_api,
                "model_name": settings.model_name,
                "response": response,
            },
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await close()

    choices = getattr(response, "choices", []) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, Sequence) and not isinstance(content, str | bytes | bytearray):
            parts: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(item, Mapping) and isinstance(item.get("text"), str):
                    parts.append(str(item["text"]))
            if "".join(parts).strip():
                return "".join(parts)
    return ""


def _chat_message_content(input_content: list[dict[str, Any]]) -> str | list[dict[str, Any]]:
    if len(input_content) == 1 and input_content[0].get("type") == "input_text":
        return str(input_content[0].get("text") or "")
    content: list[dict[str, Any]] = []
    for item in input_content:
        if item.get("type") == "input_text":
            content.append({"type": "text", "text": str(item.get("text") or "")})
        elif item.get("type") == "input_image":
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": str(item.get("image_url") or "")},
                }
            )
    return content


def _normalize_image_paths(image_paths: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(image_paths, (str, Path)):
        return [Path(image_paths)]
    return [Path(path) for path in image_paths]


def _agent_id_for_task(task_name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(task_name).strip()).strip("_").lower()
    return f"box_ir_{normalized or 'vision'}"


def _resolve_settings(runtime_config: RuntimeSettings | dict[str, Any]) -> RuntimeSettings:
    if isinstance(runtime_config, RuntimeSettings):
        return runtime_config
    if not isinstance(runtime_config, Mapping):
        raise ModelRuntimeError(
            f"runtime_config must be RuntimeSettings or mapping, got {type(runtime_config).__name__}"
        )
    provider = str(runtime_config.get("provider") or runtime_config.get("connection_id") or "").strip()
    if not provider:
        raise ModelRuntimeError("runtime_config.provider or runtime_config.connection_id is required")
    connection_id = str(runtime_config.get("connection_id") or provider).strip()
    model_name = str(runtime_config.get("model_name") or "").strip()
    if not model_name:
        raise ModelRuntimeError("runtime_config.model_name is required")
    base_url = str(runtime_config.get("base_url") or "").strip()
    api_key = str(runtime_config.get("api_key") or "").strip()
    api_key_env = str(runtime_config.get("api_key_env") or "").strip()
    if not api_key and api_key_env and os.environ.get(api_key_env):
        api_key = str(os.environ[api_key_env])
    extra_headers = (
        dict(runtime_config.get("extra_headers") or {})
        if isinstance(runtime_config.get("extra_headers"), Mapping)
        else {}
    )
    api_provider = runtime_config.get("api_provider")
    wire_api = str(runtime_config.get("wire_api") or "").strip()
    if isinstance(api_provider, Mapping) and str(api_provider.get("mode") or "auth").strip().lower() == "thirdparty":
        base_url = str(api_provider.get("base_url") or base_url).strip()
        api_key = _api_provider_key(api_provider) or api_key
        wire_api = str(api_provider.get("wire_api") or wire_api).strip()
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    wire_api = (wire_api or "responses").strip().lower().replace("-", "_")
    if wire_api in {"chat", "chat_completion", "chat_completions"}:
        wire_api = "chat_completions"
    elif wire_api != "responses":
        raise ModelRuntimeError("runtime_config.wire_api must be responses or chat_completions")
    extra_body = (
        dict(runtime_config.get("extra_body") or {})
        if isinstance(runtime_config.get("extra_body"), Mapping)
        else {}
    )
    provider_connection = ProviderConnection(
        connection_id=connection_id,
        provider_type=provider,
        base_url=base_url,
        api_key=api_key,
        extra_headers=extra_headers,
    )
    return RuntimeSettings(
        provider=provider,
        connection_id=connection_id,
        api_key=api_key,
        model_name=model_name,
        image_model_name=str(runtime_config.get("image_model_name") or "").strip(),
        base_url=base_url,
        provider_connection=provider_connection,
        extra_headers=extra_headers,
        concurrency_mode=str(runtime_config.get("concurrency_mode") or "auto"),
        max_concurrent=int(runtime_config.get("max_concurrent") or 20),
        max_critic_rounds=int(runtime_config.get("max_critic_rounds") or 3),
        wire_api=wire_api,
        extra_body=extra_body,
    )


def _api_provider_key(api_provider: Mapping[str, Any]) -> str:
    api_key = str(api_provider.get("api_key") or "").strip()
    if api_key:
        return api_key
    for key_name in ("api_key_env", "env_key"):
        env_name = str(api_provider.get(key_name) or "").strip()
        if env_name and os.environ.get(env_name):
            return str(os.environ[env_name])
    return ""


def _runtime_timeout_seconds(runtime_config: RuntimeSettings | dict[str, Any]) -> float:
    raw_timeout: Any = None
    if isinstance(runtime_config, dict):
        raw_timeout = runtime_config.get("timeout_seconds")
    else:
        raw_timeout = getattr(runtime_config, "timeout_seconds", None)
    if raw_timeout in (None, ""):
        return 600.0
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError) as exc:
        raise ModelRuntimeError("runtime_config.timeout_seconds must be numeric") from exc
    if timeout <= 0:
        raise ModelRuntimeError("runtime_config.timeout_seconds must be positive")
    return timeout


def _runtime_direct_output(runtime_config: RuntimeSettings | dict[str, Any]) -> bool:
    if isinstance(runtime_config, Mapping):
        return bool(runtime_config.get("direct_output"))
    return False


def _direct_output_settings_attempts(settings: RuntimeSettings) -> tuple[RuntimeSettings, ...]:
    primary = replace(settings, extra_body=_direct_output_extra_body(settings.extra_body))
    stripped_extra_body = _direct_output_stripped_extra_body(primary.extra_body)
    if stripped_extra_body == primary.extra_body:
        return (primary,)
    return (primary, replace(primary, extra_body=stripped_extra_body))


def _direct_output_extra_body(extra_body: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(extra_body)
    reasoning = data.get("reasoning")
    if isinstance(reasoning, Mapping):
        normalized_reasoning = dict(reasoning)
        normalized_reasoning["enabled"] = False
        data["reasoning"] = normalized_reasoning
    thinking = data.get("thinking")
    if isinstance(thinking, Mapping):
        normalized_thinking = dict(thinking)
        normalized_thinking["type"] = "disabled"
        data["thinking"] = normalized_thinking
    return data


def _direct_output_stripped_extra_body(extra_body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in extra_body.items()
        if str(key).lower() not in {"reasoning", "thinking"}
    }


def _max_output_token_cap_from_error(exc: Exception) -> int | None:
    text = _error_text(exc)
    for pattern in (_MAX_TOKENS_RANGE_RE, _MAX_TOKENS_AT_MOST_RE):
        match = pattern.search(text)
        if match is None:
            continue
        cap = int(match.group(1))
        if cap > 0:
            return cap
    return None


def _is_retryable_rate_limit(exc: Exception) -> bool:
    text = _error_text(exc).lower()
    class_name = type(exc).__name__.lower()
    return (
        "ratelimit" in class_name
        or "rate_limit" in text
        or "limit_burst_rate" in text
        or "too quickly" in text
        or "429" in text
    )


def _error_text(exc: Exception) -> str:
    parts = [str(exc)]
    for attr_name in ("message", "code", "type", "body"):
        value = getattr(exc, attr_name, None)
        if value not in (None, ""):
            parts.append(str(value))
    return "\n".join(parts)


def _raise_if_running_loop() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise ModelRuntimeError(
        "DrawAI vision runtime cannot be used inside an active asyncio loop; inject an async-aware invoker instead"
    )


def _is_loopback_base_url(base_url: str) -> bool:
    hostname = urlparse(str(base_url or "")).hostname
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _append_trace(trace_path: Path | None, event: dict[str, Any]) -> None:
    if trace_path is None:
        return
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize_trace_value(event), ensure_ascii=False, sort_keys=True) + "\n")


def _append_provider_response(trace_path: Path | None, event: Mapping[str, Any]) -> None:
    if trace_path is None:
        return
    path = _provider_response_path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize_provider_response_value(event), ensure_ascii=False, sort_keys=True) + "\n")


def _provider_response_path(trace_path: Path) -> Path:
    if trace_path.name == "llm_trace.jsonl":
        return trace_path.with_name("llm_provider_response.jsonl")
    return trace_path.with_name(f"{trace_path.stem}_provider_response.jsonl")


def _sanitize_trace_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lower_key = key_text.lower()
            normalized_key = lower_key.replace("-", "_")
            if lower_key == "authorization" or "api_key" in normalized_key:
                sanitized[key_text] = "[redacted]"
            elif lower_key in {"image_base64", "base64", "data", "payload"} and (
                lower_key == "payload" or _looks_like_base64(item)
            ):
                sanitized[key_text] = _redacted_base64(item)
            elif lower_key.endswith("payload") and isinstance(item, str) and _looks_like_base64(item):
                sanitized[key_text] = _redacted_base64(item)
            else:
                sanitized[key_text] = _sanitize_trace_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_trace_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_trace_string(value)
    return value


def _sanitize_provider_response_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lower_key = key_text.lower()
            normalized_key = lower_key.replace("-", "_")
            if lower_key == "authorization" or "api_key" in normalized_key:
                sanitized[key_text] = "[redacted]"
            elif lower_key in {"image_base64", "base64", "data", "payload"} and (
                lower_key == "payload" or _looks_like_base64(item)
            ):
                sanitized[key_text] = _redacted_base64(item)
            elif lower_key.endswith("payload") and isinstance(item, str) and _looks_like_base64(item):
                sanitized[key_text] = _redacted_base64(item)
            else:
                sanitized[key_text] = _sanitize_provider_response_value(item)
        return sanitized
    if isinstance(value, list | tuple):
        return [_sanitize_provider_response_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_provider_response_string(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _sanitize_provider_response_value(model_dump(mode="json"))
        except TypeError:
            return _sanitize_provider_response_value(model_dump())
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _sanitize_provider_response_value(to_dict())
    if hasattr(value, "__dict__"):
        return _sanitize_provider_response_value(
            {key: item for key, item in vars(value).items() if not str(key).startswith("_")}
        )
    return _sanitize_provider_response_string(str(value))


_DATA_URL_RE = re.compile(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+")
_AUTH_HEADER_RE = re.compile(r"(?i)(authorization\s*:\s*)[^\n\r,;\"']+")
_BARE_BEARER_RE = re.compile(
    r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{20,}|[A-Za-z0-9._~+/=-]*[._~+/=-][A-Za-z0-9._~+/=-]*)"
)
_API_KEY_ASSIGN_RE = re.compile(r"(?i)(\bapi[_-]?key\s*[=:]\s*)[^\s,;\"']+")
_X_API_KEY_HEADER_RE = re.compile(r"(?i)(\bx-api-key\s*:\s*)[^\s,;\"']+")
_BASE64_ASSIGN_RE = re.compile(
    r"(?i)(\b(?:payload|image_base64|data)\s*=\s*)([A-Za-z0-9+/=]{24,})"
)


def _sanitize_trace_string(value: str) -> str:
    text = _DATA_URL_RE.sub("[redacted-inline-image-base64]", value)
    text = _AUTH_HEADER_RE.sub(r"\1[redacted]", text)
    text = _X_API_KEY_HEADER_RE.sub(r"\1[redacted]", text)
    text = _API_KEY_ASSIGN_RE.sub(r"\1[redacted]", text)
    text = _BASE64_ASSIGN_RE.sub(r"\1[redacted-base64]", text)
    text = _BARE_BEARER_RE.sub(r"\1[redacted]", text)
    if len(text) > 4000:
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        return f"{text[:1000]}\n...[trace truncated len={len(text)} sha256={digest}]"
    return text


def _sanitize_provider_response_string(value: str) -> str:
    text = _DATA_URL_RE.sub("[redacted-inline-image-base64]", value)
    text = _AUTH_HEADER_RE.sub(r"\1[redacted]", text)
    text = _X_API_KEY_HEADER_RE.sub(r"\1[redacted]", text)
    text = _API_KEY_ASSIGN_RE.sub(r"\1[redacted]", text)
    text = _BASE64_ASSIGN_RE.sub(r"\1[redacted-base64]", text)
    return _BARE_BEARER_RE.sub(r"\1[redacted]", text)


def _redacted_base64(value: Any) -> dict[str, Any]:
    text = str(value or "")
    return {
        "redacted": True,
        "kind": "image_base64",
        "base64_chars": len(text),
    }


def _looks_like_base64(value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 32:
        return False
    return re.fullmatch(r"[A-Za-z0-9+/=\s]+", value) is not None
