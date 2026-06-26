from __future__ import annotations

import json
import urllib.request
from typing import Any
from urllib.parse import urlparse

DRAWAI_MODEL_BUSY_HEADER = "X-DrawAI-Queue"
DRAWAI_MODEL_BUSY_VALUE = "model-busy"
DEFAULT_MODEL_BUSY_RETRY_AFTER_SECONDS = 1.0


def urlopen_direct_for_loopback(request: urllib.request.Request, url: str, *, timeout: float):
    if is_loopback_url(url):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


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
