from __future__ import annotations

import json
import os
import re
import ssl
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DRAWAI_MODEL_BUSY_HEADER = "X-DrawAI-Queue"
DRAWAI_MODEL_BUSY_VALUE = "model-busy"
DEFAULT_MODEL_BUSY_RETRY_AFTER_SECONDS = 1.0
DEFAULT_REMOTE_QUEUE_MAX_POLLS = 180
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def remote_service_headers() -> dict[str, str]:
    """Return optional gateway authentication without persisting the secret in DrawAI configs."""
    api_key = os.environ.get("DRAWAI_REMOTE_API_KEY", "").strip()
    if not api_key:
        return {}
    header = os.environ.get("DRAWAI_REMOTE_API_KEY_HEADER", "Authorization").strip()
    scheme = os.environ.get("DRAWAI_REMOTE_API_KEY_SCHEME", "Bearer").strip()
    if not _HEADER_NAME_RE.fullmatch(header):
        raise ValueError("DRAWAI_REMOTE_API_KEY_HEADER is not a valid HTTP header name")
    if any(char in api_key for char in "\r\n") or any(char in scheme for char in "\r\n"):
        raise ValueError("remote service credentials must not contain CR/LF")
    value = f"{scheme} {api_key}".strip() if scheme else api_key
    return {header: value}


def remote_queue_max_polls() -> int:
    raw = os.environ.get("DRAWAI_REMOTE_QUEUE_MAX_POLLS", str(DEFAULT_REMOTE_QUEUE_MAX_POLLS))
    value = int(raw or DEFAULT_REMOTE_QUEUE_MAX_POLLS)
    if not 1 <= value <= 300:
        raise ValueError("DRAWAI_REMOTE_QUEUE_MAX_POLLS must be between 1 and 300")
    return value


def _remote_ssl_context(url: str) -> ssl.SSLContext | None:
    if urlparse(str(url or "")).scheme.lower() != "https":
        return None
    ca_bundle = os.environ.get("DRAWAI_REMOTE_CA_BUNDLE", "").strip()
    if not ca_bundle:
        return ssl.create_default_context()
    path = Path(os.path.expandvars(ca_bundle)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"DRAWAI_REMOTE_CA_BUNDLE not found: {path}")
    return ssl.create_default_context(cafile=str(path))


def urlopen_direct_for_loopback(request: urllib.request.Request, url: str, *, timeout: float):
    for name, value in remote_service_headers().items():
        if request.get_header(name) is None:
            request.add_unredirected_header(name, value)
    context = _remote_ssl_context(url)
    if is_loopback_url(url):
        handlers: list[Any] = [urllib.request.ProxyHandler({})]
        if context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=context))
        opener = urllib.request.build_opener(*handlers)
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def is_loopback_url(value: str) -> bool:
    hostname = urlparse(str(value or "")).hostname
    return hostname in {"127.0.0.1", "localhost", "::1"}


def model_busy_headers(retry_after_seconds: float = DEFAULT_MODEL_BUSY_RETRY_AFTER_SECONDS) -> dict[str, str]:
    retry_after = max(0.0, float(retry_after_seconds))
    retry_after_text = str(int(retry_after)) if retry_after.is_integer() else str(retry_after)
    return {
        "Retry-After": retry_after_text,
        DRAWAI_MODEL_BUSY_HEADER: DRAWAI_MODEL_BUSY_VALUE,
    }


def model_busy_retry_after_seconds(error: Any, body: bytes | None) -> float | None:
    headers = getattr(error, "headers", None)
    queue_value = _header_get(headers, DRAWAI_MODEL_BUSY_HEADER)
    if queue_value is None or queue_value.strip().lower() != DRAWAI_MODEL_BUSY_VALUE:
        return None
    header_value = _header_get(headers, "Retry-After")
    if header_value:
        return max(0.0, float(header_value))
    body_value = _body_retry_after_seconds(body)
    if body_value is not None:
        return max(0.0, body_value)
    return DEFAULT_MODEL_BUSY_RETRY_AFTER_SECONDS


def _header_get(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    value = headers.get(name)
    if value is not None:
        return str(value)
    lower_name = name.lower()
    for key, item in getattr(headers, "items", lambda: [])():
        if str(key).lower() == lower_name:
            return str(item)
    return None


def _body_retry_after_seconds(body: bytes | None) -> float | None:
    if not body:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        value = detail.get("retry_after_seconds")
    else:
        value = payload.get("retry_after_seconds") if isinstance(payload, dict) else None
    if value is None:
        return None
    return float(value)
