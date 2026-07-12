from __future__ import annotations

import base64
import io
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

from .http_utils import urlopen_direct_for_loopback

RMBG_REMOVE_BACKGROUND_PATH = "/v1/rmbg/remove-background"


class RmbgResponseError(ValueError):
    """Raised when the remote RMBG service response cannot be used."""


class JsonTransport(Protocol):
    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], float]:
        ...


@dataclass(frozen=True)
class RmbgResult:
    image: Image.Image
    artifacts: dict[str, Any]
    elapsed_ms: float


class HttpJsonTransport:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], float]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        body = json.dumps(payload).encode("utf-8")
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
        except urllib.error.HTTPError as exc:
            excerpt = exc.read().decode("utf-8", errors="replace")[:500]
            raise RmbgResponseError(
                f"RMBG HTTP error from {url}: status={exc.code}, body={excerpt!r}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RmbgResponseError(f"RMBG request failed for {url}: {exc}") from exc

        elapsed_ms = (time.monotonic() - started) * 1000
        response_text = response_body.decode("utf-8", errors="replace")
        try:
            decoded = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise RmbgResponseError(
                f"RMBG response contained malformed JSON from {url}: {response_text[:500]!r}"
            ) from exc
        if not isinstance(decoded, dict):
            raise RmbgResponseError(f"RMBG response must be a JSON object from {url}")
        return decoded, elapsed_ms


class RemoteRmbgClient:
    def __init__(self, base_url: str, transport: JsonTransport | None = None):
        self.base_url = base_url
        self.transport = transport or HttpJsonTransport(base_url)

    def remove_background(
        self,
        image: Image.Image,
        output_name: str,
        *,
        timeout_s: float,
        model_path: str = "",
        artifact_prefix: str | None = None,
    ) -> RmbgResult:
        payload: dict[str, Any] = {
            "image_base64": _image_to_base64(image.convert("RGB")),
            "output_name": output_name,
            "return_image": True,
        }
        if model_path:
            payload["model_path"] = model_path
        if artifact_prefix:
            payload["artifact_prefix"] = artifact_prefix

        response_payload, elapsed_ms = self.transport.post_json(
            RMBG_REMOVE_BACKGROUND_PATH,
            payload,
            timeout_s,
        )
        if response_payload.get("error"):
            raise RmbgResponseError(f"RMBG service error: {response_payload.get('error')}")
        if response_payload.get("detail"):
            raise RmbgResponseError(f"RMBG service error: {response_payload.get('detail')}")
        image_base64 = response_payload.get("image_base64")
        if not isinstance(image_base64, str) or not image_base64.strip():
            raise RmbgResponseError("RMBG response missing required image_base64 field")
        artifacts = response_payload.get("artifacts")
        if not isinstance(artifacts, dict):
            artifacts = {}
        return RmbgResult(
            image=_decode_base64_image(image_base64).convert("RGBA"),
            artifacts=dict(artifacts),
            elapsed_ms=elapsed_ms,
        )


def _image_to_base64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _decode_base64_image(image_base64: str) -> Image.Image:
    payload = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
    return Image.open(io.BytesIO(base64.b64decode(payload)))
