from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .http_utils import model_busy_retry_after_seconds, urlopen_direct_for_loopback

OCR_BOXES_ENDPOINT = "/v1/ocr/boxes"
LEGACY_OCR_SOURCES = frozenset({"model_stub"})
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
DEFAULT_RETRY_MAX_ATTEMPTS = 12
DEFAULT_RETRY_BASE_DELAY_SECONDS = 2.0
DEFAULT_RETRY_MAX_DELAY_SECONDS = 20.0
DEFAULT_MODEL_QUEUE_TIMEOUT_SECONDS = 600.0


class OcrProviderError(ValueError):
    """Raised when an OCR provider cannot produce normalized OCR boxes."""


class OcrHttpStatusError(OcrProviderError):
    def __init__(self, message: str, *, http_status: int, body_excerpt: str = "") -> None:
        super().__init__(message)
        self.http_status = int(http_status)
        self.body_excerpt = body_excerpt


class OcrBoxProvider(Protocol):
    def extract_boxes(self, image_path: Path) -> dict[str, Any]:
        ...


class JsonTransport(Protocol):
    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], float]:
        ...


class HttpJsonTransport:
    def __init__(self, base_url: str, queue_timeout_s: float | None = None):
        base_url = str(base_url or "").strip()
        if not base_url:
            raise OcrProviderError("remote PaddleOCR base_url must be a non-empty string")
        self.base_url = base_url.rstrip("/")
        self.queue_timeout_s = queue_timeout_s

    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], float]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        body = json.dumps(payload).encode("utf-8")
        queue_started = time.monotonic()
        while True:
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            started = time.monotonic()
            try:
                with urlopen_direct_for_loopback(request, url, timeout=timeout_s) as response:
                    response_body = response.read()
                break
            except urllib.error.HTTPError as exc:
                body_bytes = _read_error_body(exc)
                retry_after = model_busy_retry_after_seconds(exc, body_bytes)
                if retry_after is not None:
                    self._wait_for_model_queue(path, timeout_s, queue_started, retry_after, exc)
                    continue
                body_excerpt = _short_excerpt_bytes(body_bytes)
                raise OcrHttpStatusError(
                    _transport_error_message(
                        "Remote PaddleOCR HTTP error",
                        self.base_url,
                        path,
                        timeout_s,
                        http_status=exc.code,
                        body_excerpt=body_excerpt,
                    ),
                    http_status=exc.code,
                    body_excerpt=body_excerpt,
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise OcrProviderError(
                    _transport_error_message(
                        "Remote PaddleOCR request failed",
                        self.base_url,
                        path,
                        timeout_s,
                        cause=str(exc),
                    )
                ) from exc
        elapsed_ms = (time.monotonic() - started) * 1000
        response_text = response_body.decode("utf-8", errors="replace")
        try:
            decoded = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise OcrProviderError(
                _transport_error_message(
                    "Remote PaddleOCR response contained malformed JSON",
                    self.base_url,
                    path,
                    timeout_s,
                    body_excerpt=_short_excerpt(response_text),
                )
            ) from exc
        if not isinstance(decoded, dict):
            raise OcrProviderError(
                _transport_error_message(
                    "Remote PaddleOCR response must be a JSON object",
                    self.base_url,
                    path,
                    timeout_s,
                    body_excerpt=_short_excerpt(response_text),
                )
            )
        return decoded, elapsed_ms

    def _wait_for_model_queue(
        self,
        path: str,
        timeout_s: float,
        queue_started: float,
        retry_after: float,
        cause: urllib.error.HTTPError,
    ) -> None:
        queue_timeout_s = _queue_timeout_seconds(self.queue_timeout_s, "DRAWAI_OCR_QUEUE_TIMEOUT_SECONDS")
        if time.monotonic() - queue_started + retry_after > queue_timeout_s:
            raise OcrHttpStatusError(
                _transport_error_message(
                    "Remote PaddleOCR service stayed busy",
                    self.base_url,
                    path,
                    timeout_s,
                    http_status=cause.code,
                    cause=f"queue_timeout_s={queue_timeout_s:g}",
                ),
                http_status=cause.code,
            ) from cause
        time.sleep(retry_after)


@dataclass(frozen=True)
class FixtureOcrBoxProvider:
    fixture_path: Path | str

    def extract_boxes(self, image_path: Path) -> dict[str, Any]:
        del image_path
        fixture_path = Path(self.fixture_path)
        try:
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise OcrProviderError(f"OCR fixture not found: {fixture_path}") from exc
        except json.JSONDecodeError as exc:
            raise OcrProviderError(f"OCR fixture contains malformed JSON: {fixture_path}") from exc
        return normalize_ocr_boxes_payload(payload, default_source="fixture")


class RemotePaddleOcrProvider:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: JsonTransport | None = None,
        retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS,
        retry_base_delay_seconds: float = DEFAULT_RETRY_BASE_DELAY_SECONDS,
        retry_max_delay_seconds: float = DEFAULT_RETRY_MAX_DELAY_SECONDS,
        sleep: Any = time.sleep,
    ) -> None:
        self.base_url = str(base_url or "").strip()
        if not self.base_url:
            raise OcrProviderError("remote PaddleOCR base_url must be a non-empty string")
        self.timeout_seconds = float(timeout_seconds)
        if self.timeout_seconds <= 0:
            raise OcrProviderError("remote PaddleOCR timeout_seconds must be positive")
        self.transport = transport or HttpJsonTransport(self.base_url)
        self.retry_max_attempts = max(1, int(retry_max_attempts))
        self.retry_base_delay_seconds = max(0.0, float(retry_base_delay_seconds))
        self.retry_max_delay_seconds = max(0.0, float(retry_max_delay_seconds))
        self._sleep = sleep

    def extract_boxes(self, image_path: Path) -> dict[str, Any]:
        image_path = Path(image_path)
        image_bytes = image_path.read_bytes()
        payload = {
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "filename": image_path.name,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "image_bytes": len(image_bytes),
        }
        try:
            response_payload, elapsed_ms = self._post_json_with_retries(payload)
        except Exception as exc:
            if isinstance(exc, OcrProviderError):
                raise
            raise OcrProviderError(
                "Remote PaddleOCR request failed: "
                f"endpoint={OCR_BOXES_ENDPOINT!r}, base_url={self.base_url!r}, "
                f"timeout_s={self.timeout_seconds!r}, cause={type(exc).__name__}: {exc}"
            ) from exc
        normalized = normalize_ocr_boxes_payload(response_payload, default_source="remote_paddleocr")
        normalized["provider"] = "remote_paddleocr"
        normalized["elapsed_ms"] = elapsed_ms
        return normalized

    def _post_json_with_retries(self, payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
        started = time.monotonic()
        last_error: OcrProviderError | None = None
        for attempt in range(1, self.retry_max_attempts + 1):
            try:
                response_payload, _elapsed_ms = self.transport.post_json(
                    OCR_BOXES_ENDPOINT,
                    payload,
                    self.timeout_seconds,
                )
                return response_payload, (time.monotonic() - started) * 1000
            except OcrProviderError as exc:
                last_error = exc
                if not _should_retry_ocr_error(exc) or attempt >= self.retry_max_attempts:
                    raise
                self._sleep(_retry_delay_seconds(attempt, self.retry_base_delay_seconds, self.retry_max_delay_seconds))
        assert last_error is not None
        raise last_error


def build_ocr_provider(
    ocr_config: Any,
) -> OcrBoxProvider:
    provider = str(getattr(ocr_config, "provider", "") or "").strip()
    if provider == "fixture":
        fixture = getattr(ocr_config, "fixture", None)
        fixture_path = getattr(fixture, "path", None)
        if fixture_path is None:
            raise OcrProviderError("ocr.fixture.path is required when ocr.provider is 'fixture'")
        return FixtureOcrBoxProvider(fixture_path)
    if provider == "remote_paddleocr":
        remote = getattr(ocr_config, "remote_paddleocr", None)
        return RemotePaddleOcrProvider(
            base_url=getattr(remote, "base_url", ""),
            timeout_seconds=getattr(remote, "timeout_seconds", 0),
        )
    raise OcrProviderError(f"Unsupported OCR provider: {provider!r}")


def normalize_ocr_boxes_payload(
    payload: Any,
    *,
    default_source: str,
    default_confidence: float | None = None,
    max_boxes: int | None = None,
    allow_missing_ocr_text_boxes: bool = False,
) -> dict[str, Any]:
    raw_boxes = _extract_raw_boxes(
        payload,
        allow_missing_ocr_text_boxes=allow_missing_ocr_text_boxes,
    )
    boxes: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for raw_box in raw_boxes:
        if max_boxes is not None and len(boxes) >= max_boxes:
            break
        if not isinstance(raw_box, dict):
            continue
        bbox = _normalize_bbox(raw_box.get("bbox"))
        if bbox is None:
            continue
        box_id = _normalize_box_id(raw_box.get("id"), used_ids)
        used_ids.add(box_id)
        normalized: dict[str, Any] = {
            "id": box_id,
            "bbox": bbox,
            "confidence": _normalize_confidence(raw_box.get("confidence"), default_confidence),
            "source": _normalize_source(raw_box.get("source"), default_source),
        }
        if normalized["source"] in LEGACY_OCR_SOURCES:
            raise OcrProviderError(
                "Legacy OCR source is not supported in the DrawAI/SAM3 mainline: "
                f"source={normalized['source']!r}. Regenerate OCR with remote_paddleocr "
                "or use a fixture produced from real OCR."
            )
        text = raw_box.get("text")
        if isinstance(text, str) and text:
            normalized["text"] = text
        boxes.append(normalized)
    return {"ocr_text_boxes": boxes}


def clamp_ocr_boxes_to_canvas(
    payload: dict[str, Any],
    *,
    canvas_width: int | float,
    canvas_height: int | float,
) -> dict[str, Any]:
    width = _as_number(canvas_width)
    height = _as_number(canvas_height)
    if width is None or height is None or width <= 0 or height <= 0:
        raise OcrProviderError("canvas_width and canvas_height must be positive numbers")

    clamped_payload = dict(payload)
    clamped_boxes: list[dict[str, Any]] = []
    raw_boxes = payload.get("ocr_text_boxes")
    if not isinstance(raw_boxes, list):
        raise OcrProviderError("OCR payload field 'ocr_text_boxes' must be a list")

    for raw_box in raw_boxes:
        if not isinstance(raw_box, dict):
            continue
        bbox = _normalize_bbox(raw_box.get("bbox"))
        if bbox is None:
            continue
        x1, y1, x2, y2 = [float(value) for value in bbox]
        left = max(0.0, min(width, x1))
        top = max(0.0, min(height, y1))
        right = max(0.0, min(width, x2))
        bottom = max(0.0, min(height, y2))
        if right <= left or bottom <= top:
            continue
        box = dict(raw_box)
        box["bbox"] = [
            _clean_number(left),
            _clean_number(top),
            _clean_number(right),
            _clean_number(bottom),
        ]
        clamped_boxes.append(box)

    clamped_payload["ocr_text_boxes"] = clamped_boxes
    return clamped_payload


def _extract_raw_boxes(payload: Any, *, allow_missing_ocr_text_boxes: bool) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "ocr_text_boxes" not in payload:
            if not allow_missing_ocr_text_boxes:
                raise OcrProviderError("OCR payload missing required field 'ocr_text_boxes'")
            return []
        raw_boxes = payload["ocr_text_boxes"]
        if not isinstance(raw_boxes, list):
            raise OcrProviderError("OCR payload field 'ocr_text_boxes' must be a list")
        return raw_boxes
    raise OcrProviderError("OCR payload must be a JSON object or list")


def _normalize_bbox(raw_bbox: Any) -> list[int | float] | None:
    if isinstance(raw_bbox, dict):
        raw_bbox = _bbox_from_mapping(raw_bbox)
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    values: list[int | float] = []
    for value in raw_bbox:
        number = _as_number(value)
        if number is None:
            return None
        values.append(_clean_number(number))
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        return None
    return values


def _bbox_from_mapping(raw_bbox: dict[str, Any]) -> list[Any] | None:
    if all(key in raw_bbox for key in ("x1", "y1", "x2", "y2")):
        return [raw_bbox["x1"], raw_bbox["y1"], raw_bbox["x2"], raw_bbox["y2"]]
    if all(key in raw_bbox for key in ("x", "y", "w", "h")):
        x = _as_number(raw_bbox["x"])
        y = _as_number(raw_bbox["y"])
        w = _as_number(raw_bbox["w"])
        h = _as_number(raw_bbox["h"])
        if x is None or y is None or w is None or h is None:
            return None
        return [x, y, x + w, y + h]
    return None


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return number


def _clean_number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return value


def _normalize_confidence(raw_confidence: Any, default_confidence: float | None) -> float:
    value = _as_number(raw_confidence)
    if value is None:
        value = float(default_confidence if default_confidence is not None else 0.0)
    return max(0.0, min(1.0, float(value)))


def _normalize_source(raw_source: Any, default_source: str) -> str:
    if isinstance(raw_source, str) and raw_source.strip():
        return raw_source.strip()
    return default_source


def _normalize_box_id(raw_id: Any, used_ids: set[str]) -> str:
    candidate = _coerce_box_id(raw_id)
    if candidate and candidate not in used_ids:
        return candidate
    index = 1
    while True:
        generated = f"T{index:03d}"
        if generated not in used_ids:
            return generated
        index += 1


def _coerce_box_id(raw_id: Any) -> str | None:
    if not isinstance(raw_id, str):
        return None
    text = raw_id.strip()
    match = re.fullmatch(r"T(\d+)", text)
    if not match:
        return None
    return f"T{int(match.group(1)):03d}"


def _transport_error_message(
    prefix: str,
    base_url: str,
    path: str,
    timeout_s: float,
    *,
    http_status: int | None = None,
    body_excerpt: str | None = None,
    cause: str | None = None,
) -> str:
    parts = [
        prefix,
        f"base_url={base_url!r}",
        f"endpoint={path!r}",
        f"timeout_s={timeout_s!r}",
    ]
    if http_status is not None:
        parts.append(f"http_status={http_status}")
    if body_excerpt:
        parts.append(f"body_excerpt={body_excerpt!r}")
    if cause:
        parts.append(f"cause={cause!r}")
    return "; ".join(parts)


def _should_retry_ocr_error(error: OcrProviderError) -> bool:
    status = getattr(error, "http_status", None)
    if isinstance(status, int) and status in RETRYABLE_HTTP_STATUSES:
        return True
    text = str(error).lower()
    return "concurrency limit" in text or "http_status=429" in text


def _retry_delay_seconds(attempt: int, base_delay: float, max_delay: float) -> float:
    if base_delay <= 0 or max_delay <= 0:
        return 0.0
    return min(max_delay, base_delay * attempt)


def _queue_timeout_seconds(raw_value: float | None, env_name: str) -> float:
    value = raw_value
    if value is None:
        env_value = os.environ.get(env_name) or os.environ.get("DRAWAI_MODEL_QUEUE_TIMEOUT_SECONDS")
        value = DEFAULT_MODEL_QUEUE_TIMEOUT_SECONDS if env_value is None else float(env_value)
    value = float(value)
    if value <= 0:
        raise OcrProviderError(f"{env_name} must be positive")
    return value


def _read_error_body(error: urllib.error.HTTPError) -> bytes:
    try:
        return error.read()
    except OSError:
        return b""


def _body_excerpt(error: urllib.error.HTTPError) -> str:
    return _short_excerpt_bytes(_read_error_body(error))


def _short_excerpt_bytes(body: bytes) -> str:
    return _short_excerpt(body.decode("utf-8", errors="replace"))


def _short_excerpt(text: str, limit: int = 500) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."
