from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
from ipaddress import ip_address
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


class ModelRuntimeError(ValueError):
    """Raised when the DrawAI model runtime cannot invoke a vision model."""


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
    if runtime_config is None:
        raise ModelRuntimeError(
            "runtime_config is required for DrawAI model runtime usage without an injected invoker"
        )
    normalized_image_paths = _normalize_image_paths(image_paths)
    if not normalized_image_paths:
        raise ModelRuntimeError("at least one image path is required for vision invocation")
    settings = _resolve_settings(runtime_config)
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
    _append_trace(
        trace,
        {
            "type": "request",
            "task_name": task_name,
            "provider": settings.provider,
            "connection_id": settings.connection_id,
            "model_name": settings.model_name,
            "images": image_traces,
            "max_output_tokens": int(max_output_tokens),
            "timeout_seconds": timeout_seconds,
        },
    )
    _raise_if_running_loop()
    output = asyncio.run(
        _invoke_openai_compatible_response(
            settings=settings,
            input_content=input_content,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
    )
    if not output:
        raise ModelRuntimeError(f"vision model returned no text output for task {task_name!r}")
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


async def _invoke_openai_compatible_response(
    *,
    settings: RuntimeSettings,
    input_content: list[dict[str, Any]],
    max_output_tokens: int,
    timeout_seconds: float,
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
    extra_headers = (
        dict(runtime_config.get("extra_headers") or {})
        if isinstance(runtime_config.get("extra_headers"), Mapping)
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
    )


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
