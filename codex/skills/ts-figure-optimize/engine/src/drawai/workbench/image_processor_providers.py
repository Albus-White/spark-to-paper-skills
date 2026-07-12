from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, Sequence

from fastapi import HTTPException
from PIL import Image

from .api_presets import ApiPreset, api_preset_by_id, read_workbench_api_presets
from .processor_settings import (
    ProcessorSetting,
    read_workbench_processor_settings,
    require_processor_configured_from_settings,
)

MAX_GENERATED_IMAGE_BYTES = 50 * 1024 * 1024
_DEFAULT_RETRY_ATTEMPTS = 3
_DEFAULT_RETRY_DELAY_SECONDS = 1.0
_TRANSIENT_HTTP_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
urlopen_external = urllib.request.urlopen


def asset_prepare_image_providers(workspace: str | Path) -> dict[str, Any]:
    api_presets = read_workbench_api_presets(workspace)
    settings = read_workbench_processor_settings(workspace)
    return asset_prepare_image_providers_from_settings(settings, api_presets=api_presets)


def asset_prepare_image_providers_from_settings(
    settings: Mapping[str, ProcessorSetting],
    *,
    api_presets: Sequence[ApiPreset],
) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for processor in ("image_generate", "image_edit"):
        try:
            setting = require_processor_configured_from_settings(settings, processor, api_presets=api_presets)
        except ValueError:
            continue
        if setting.driver_id != "openai_images_api":
            continue
        preset = _processor_api_preset(api_presets, processor, setting.api_preset_id)
        if processor == "image_generate":
            providers["image_generate"] = images_api_generate_provider(preset)
        else:
            providers["image_edit"] = images_api_edit_provider(preset)
    return providers


def images_api_generate_provider(preset: ApiPreset) -> Callable[..., Mapping[str, Any]]:
    def generate(
        *,
        prompt: str,
        output_dir: str | Path,
        task_name: str,
        output_stem: str,
        runtime_config: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        output_path = Path(output_dir).expanduser().resolve(strict=False)
        output_path.mkdir(parents=True, exist_ok=True)
        api_key = _api_preset_key(preset)
        request_payload = _images_api_payload(preset, prompt, runtime_config=runtime_config)
        response_payload = call_image_generation_upstream(
            request_payload,
            api_url=image_generation_api_url(preset.base_url),
            api_key=api_key,
        )
        image_payload = _materialize_first_images_api_image(
            response_payload,
            output_dir=output_path,
            output_stem=output_stem,
            download_api_key=api_key,
        )
        return _provider_result("generate", preset, prompt, output_path, task_name, image_payload)

    return generate


def images_api_edit_provider(preset: ApiPreset) -> Callable[..., Mapping[str, Any]]:
    def edit(
        *,
        source_image_path: str | Path,
        prompt: str,
        output_dir: str | Path,
        task_name: str,
        output_stem: str,
        runtime_config: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        output_path = Path(output_dir).expanduser().resolve(strict=False)
        output_path.mkdir(parents=True, exist_ok=True)
        api_key = _api_preset_key(preset)
        request_payload = _images_api_payload(preset, prompt, runtime_config=runtime_config)
        if _uses_reference_generation_edit(preset.base_url):
            response_payload = call_image_reference_edit_upstream(
                request_payload,
                source_image_path=source_image_path,
                api_url=image_generation_api_url(preset.base_url),
                api_key=api_key,
            )
        else:
            response_payload = call_image_edit_upstream(
                request_payload,
                source_image_path=source_image_path,
                api_url=image_edit_api_url(preset.base_url),
                api_key=api_key,
            )
        image_payload = _materialize_first_images_api_image(
            response_payload,
            output_dir=output_path,
            output_stem=output_stem,
            download_api_key=api_key,
        )
        result = _provider_result("edit", preset, prompt, output_path, task_name, image_payload)
        result["source_image_path"] = str(source_image_path)
        return result

    return edit


def image_generation_api_url(base_url: Any = None) -> str:
    return _image_api_url(base_url, endpoint="generations")


def image_edit_api_url(base_url: Any = None) -> str:
    return _image_api_url(base_url, endpoint="edits")


def call_image_generation_upstream(
    payload: Mapping[str, Any],
    *,
    api_url: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    api_key = api_key or os.environ.get("DRAWAI_IMAGEGEN_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="DRAWAI_IMAGEGEN_API_KEY or OPENAI_API_KEY is required for image generation")
    request = urllib.request.Request(
        api_url,
        data=json.dumps(dict(payload)).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    timeout = _optional_positive_float_env("DRAWAI_IMAGEGEN_TIMEOUT_SECONDS") or 600.0
    raw = _read_images_api_request(request, timeout=timeout, operation="image generation")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="image generation upstream returned non-JSON response") from exc
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=502, detail="image generation upstream JSON response must be an object")
    task_id = _image_generation_task_id(decoded)
    if task_id:
        return _poll_image_generation_task(api_url, api_key, task_id)
    return decoded


def call_image_edit_upstream(
    payload: Mapping[str, Any],
    *,
    source_image_path: str | Path,
    api_url: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    api_key = api_key or os.environ.get("DRAWAI_IMAGEGEN_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="DRAWAI_IMAGEGEN_API_KEY or OPENAI_API_KEY is required for image editing")
    source_path = Path(source_image_path).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise HTTPException(status_code=400, detail=f"image edit source image does not exist: {source_path}")
    source_bytes = source_path.read_bytes()
    if len(source_bytes) > MAX_GENERATED_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="image edit source image is too large")
    body, content_type = _multipart_image_edit_body(
        payload,
        source_name=source_path.name,
        source_bytes=source_bytes,
        source_media_type=_media_type(source_path),
    )
    request = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": content_type,
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    timeout = _optional_positive_float_env("DRAWAI_IMAGEGEN_TIMEOUT_SECONDS") or 600.0
    raw = _read_images_api_request(request, timeout=timeout, operation="image edit")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="image edit upstream returned non-JSON response") from exc
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=502, detail="image edit upstream JSON response must be an object")
    task_id = _image_generation_task_id(decoded)
    if task_id:
        return _poll_image_generation_task(api_url, api_key, task_id)
    return decoded


def call_image_reference_edit_upstream(
    payload: Mapping[str, Any],
    *,
    source_image_path: str | Path,
    api_url: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    api_key = api_key or os.environ.get("DRAWAI_IMAGEGEN_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="DRAWAI_IMAGEGEN_API_KEY or OPENAI_API_KEY is required for image editing")
    source_path = Path(source_image_path).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise HTTPException(status_code=400, detail=f"image edit source image does not exist: {source_path}")
    source_bytes = source_path.read_bytes()
    if len(source_bytes) > MAX_GENERATED_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="image edit source image is too large")
    request_payload = dict(payload)
    request_payload["image_urls"] = [
        f"data:{_media_type(source_path)};base64,{base64.b64encode(source_bytes).decode('ascii')}"
    ]
    return call_image_generation_upstream(request_payload, api_url=api_url, api_key=api_key)


def _processor_api_preset(api_presets: Sequence[ApiPreset], processor: str, api_preset_id: str) -> ApiPreset:
    preset = api_preset_by_id(api_presets, api_preset_id)
    if preset is None:
        raise ValueError(f"API preset not found for {processor}: {api_preset_id or '<empty>'}")
    return preset


def _images_api_payload(
    preset: ApiPreset,
    prompt: str,
    *,
    runtime_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": preset.model,
        "prompt": prompt,
        "n": 1,
    }
    if isinstance(runtime_config, Mapping):
        extra_payload = runtime_config.get("api_payload")
        if isinstance(extra_payload, Mapping):
            payload.update(dict(extra_payload))
        for key in ("size", "quality", "background", "moderation", "output_format", "output_compression"):
            value = runtime_config.get(key)
            if value is not None and value != "":
                payload[key] = value
    return payload


def _provider_result(
    operation: str,
    preset: ApiPreset,
    prompt: str,
    output_path: Path,
    task_name: str,
    image_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "drawai.workbench.images_api_provider_result.v1",
        "runner": "images_api",
        "task_name": task_name,
        "operation": operation,
        "provider": preset.id,
        "model": preset.model,
        "prompt": prompt,
        "output_dir": str(output_path),
        "images": [dict(image_payload)],
    }


def _multipart_image_edit_body(
    payload: Mapping[str, Any],
    *,
    source_name: str,
    source_bytes: bytes,
    source_media_type: str,
) -> tuple[bytes, str]:
    boundary = f"drawai-{binascii.hexlify(os.urandom(12)).decode('ascii')}"
    chunks: list[bytes] = []
    for key, value in payload.items():
        if value is None or value == "":
            continue
        chunks.extend(
            (
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{_quote_multipart_name(str(key))}"\r\n\r\n'.encode("utf-8"),
                _multipart_scalar_value(value).encode("utf-8"),
                b"\r\n",
            )
        )
    chunks.extend(
        (
            f"--{boundary}\r\n".encode("utf-8"),
            (
                'Content-Disposition: form-data; name="image"; '
                f'filename="{_quote_multipart_name(source_name)}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {source_media_type}\r\n\r\n".encode("utf-8"),
            source_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        )
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _multipart_scalar_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float | str):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _quote_multipart_name(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "")


def _image_api_url(base_url: Any, *, endpoint: str) -> str:
    raw = str(base_url or "https://api.openai.com").strip()
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="image generation Base URL must be an http(s) URL")
    path = parsed.path.rstrip("/")
    suffix = f"/images/{endpoint}"
    for existing_suffix in ("/images/generations", "/images/edits"):
        if path.endswith(existing_suffix):
            endpoint_path = f"{path[: -len(existing_suffix)]}{suffix}"
            break
    else:
        endpoint_path = ""
    if not endpoint_path and path.endswith("/v1"):
        endpoint_path = f"{path}{suffix}"
    elif not endpoint_path and path:
        endpoint_path = f"{path}/v1/images/{endpoint}"
    elif not endpoint_path:
        endpoint_path = f"/v1/images/{endpoint}"
    return urllib.parse.urlunparse(parsed._replace(path=endpoint_path))


def _uses_reference_generation_edit(base_url: Any) -> bool:
    parsed = urllib.parse.urlparse(str(base_url or "").strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return netloc.endswith("apimart.ai") or path.endswith("/images/generations")


def _api_preset_key(preset: ApiPreset) -> str:
    if preset.api_key:
        return preset.api_key
    if preset.api_key_env:
        value = os.environ.get(preset.api_key_env)
        if value:
            return value
        raise HTTPException(status_code=503, detail=f"{preset.api_key_env} is required for API preset {preset.id}")
    raise HTTPException(status_code=503, detail=f"API preset {preset.id} must set api_key_env or api_key")


def _materialize_first_images_api_image(
    payload: Mapping[str, Any],
    *,
    output_dir: Path,
    output_stem: str,
    download_api_key: str | None = None,
) -> dict[str, Any]:
    for index, record in enumerate(_image_generation_payload_records(payload), start=1):
        image_bytes, suffix = _images_api_record_bytes(record, download_api_key=download_api_key)
        if not image_bytes:
            continue
        if len(image_bytes) > MAX_GENERATED_IMAGE_BYTES:
            raise HTTPException(status_code=502, detail="image generation upstream returned an image that is too large")
        image_path = _unique_upload_path(output_dir / f"{_safe_download_stem(output_stem)}{suffix}")
        image_path.write_bytes(image_bytes)
        with Image.open(image_path) as image:
            width, height = image.size
        return {
            "id": str(record.get("id") or f"images-api-{index}"),
            "status": str(record.get("status") or "completed"),
            "path": str(image_path),
            "source_path": str(image_path),
            "revised_prompt": str(record.get("revised_prompt") or ""),
            "mime_type": _media_type(image_path),
            "width": width,
            "height": height,
            "bytes": len(image_bytes),
        }
    raise HTTPException(status_code=502, detail="image generation upstream did not return an image")


def _images_api_record_bytes(record: Mapping[str, Any], *, download_api_key: str | None = None) -> tuple[bytes, str]:
    raw_b64 = record.get("b64_json") or record.get("image_base64")
    if isinstance(raw_b64, str) and raw_b64.strip():
        mime_type = str(record.get("mime_type") or record.get("content_type") or "image/png").split(";", 1)[0].lower()
        try:
            image_bytes = base64.b64decode("".join(raw_b64.split()), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=502, detail="image generation upstream returned invalid base64 image data") from exc
        return image_bytes, _image_suffix_from_mime(mime_type)
    raw_url = record.get("url")
    if isinstance(raw_url, str) and raw_url.strip():
        return _read_generated_image_value(raw_url, download_api_key=download_api_key)
    return b"", ".png"


def _read_generated_image_value(value: str, *, download_api_key: str | None = None) -> tuple[bytes, str]:
    text = value.strip()
    if text.startswith("data:"):
        return _read_data_image_url(text)
    return _download_generated_image_url(text, api_key=download_api_key)


def _read_data_image_url(value: str) -> tuple[bytes, str]:
    match = re.fullmatch(r"data:(image/[A-Za-z0-9.+-]+);base64,(.*)", value, flags=re.DOTALL)
    if match is None:
        raise HTTPException(status_code=400, detail="invalid data image URL")
    mime_type = match.group(1).lower()
    try:
        image_bytes = base64.b64decode("".join(match.group(2).split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid base64 data image URL") from exc
    if len(image_bytes) > MAX_GENERATED_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="image URL is too large")
    return image_bytes, _image_suffix_from_mime(mime_type)


def _download_generated_image_url(value: str, *, api_key: str | None = None) -> tuple[bytes, str]:
    try:
        image_bytes, mime_type = _read_generated_image_url(value)
    except urllib.error.HTTPError as exc:
        if exc.code not in {401, 403} or not api_key:
            raise HTTPException(status_code=400, detail=f"failed to download image URL: {exc}") from exc
        try:
            image_bytes, mime_type = _read_generated_image_url(
                value,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        except (urllib.error.URLError, TimeoutError, OSError) as retry_exc:
            raise HTTPException(status_code=400, detail=f"failed to download image URL: {retry_exc}") from retry_exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"failed to download image URL: {exc}") from exc
    if len(image_bytes) > MAX_GENERATED_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="image URL is too large")
    return image_bytes, _image_suffix_from_mime(mime_type)


def _read_generated_image_url(value: str, *, headers: Mapping[str, str] | None = None) -> tuple[bytes, str]:
    request_headers = {
        "Accept": "image/*,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 DrawAI/1.0",
    }
    if headers:
        request_headers.update(dict(headers))
    request = urllib.request.Request(value, headers=request_headers)
    with urlopen_external(request, timeout=600) as response:
        image_bytes = response.read(MAX_GENERATED_IMAGE_BYTES + 1)
        mime_type = str(response.headers.get("content-type") or "image/png").split(";", 1)[0].lower()
    return image_bytes, mime_type


def _poll_image_generation_task(api_url: str, api_key: str, task_id: str) -> dict[str, Any]:
    task_url = _image_generation_task_url(api_url, task_id)
    timeout = _optional_positive_float_env("DRAWAI_IMAGEGEN_TASK_TIMEOUT_SECONDS") or 600.0
    interval = _optional_positive_float_env("DRAWAI_IMAGEGEN_POLL_INTERVAL_SECONDS") or 2.0
    deadline = time.monotonic() + timeout
    last_payload: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        payload = _get_image_generation_task(task_url, api_key)
        last_payload = payload
        status = _image_generation_task_status(payload)
        if status == "completed":
            return payload
        if status in {"failed", "canceled", "cancelled", "rejected", "error"}:
            raise HTTPException(status_code=502, detail=_image_generation_task_error(payload, task_id))
        time.sleep(interval)
    detail = f"image generation task timed out after {timeout:.0f}s"
    if last_payload:
        status = _image_generation_task_status(last_payload)
        if status:
            detail = f"{detail} (task: {task_id}, status: {status})"
    raise HTTPException(status_code=504, detail=detail)


def _get_image_generation_task(task_url: str, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        task_url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )
    timeout = _optional_positive_float_env("DRAWAI_IMAGEGEN_TIMEOUT_SECONDS") or 600.0
    raw = _read_images_api_request(request, timeout=timeout, operation="image generation task polling")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="image generation task endpoint returned non-JSON response") from exc
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=502, detail="image generation task endpoint JSON response must be an object")
    return decoded


def _image_generation_task_url(api_url: str, task_id: str) -> str:
    parsed = urllib.parse.urlparse(api_url)
    path = parsed.path.rstrip("/")
    for marker in ("/images/generations", "/images/edits"):
        if path.endswith(marker):
            base_path = path[: -len(marker)]
            break
    else:
        base_path = "/v1"
    task_path = f"{base_path.rstrip('/')}/tasks/{urllib.parse.quote(task_id)}"
    return urllib.parse.urlunparse(parsed._replace(path=task_path, params="", query="", fragment=""))


def _image_generation_task_id(payload: Mapping[str, Any]) -> str:
    for record in _image_generation_payload_records(payload):
        task_id = record.get("task_id") or record.get("id")
        status = str(record.get("status") or record.get("state") or "").lower()
        if isinstance(task_id, str) and task_id.strip() and status in {"submitted", "in_progress", "processing", "queued"}:
            return task_id.strip()
    return ""


def _image_generation_task_status(payload: Mapping[str, Any]) -> str:
    for record in _image_generation_payload_records(payload):
        status = record.get("status") or record.get("state")
        if isinstance(status, str) and status.strip():
            return status.strip().lower()
    return ""


def _image_generation_task_error(payload: Mapping[str, Any], task_id: str) -> str:
    for record in _image_generation_payload_records(payload):
        for key in ("error", "message", "detail", "failure_reason"):
            value = record.get(key)
            if isinstance(value, Mapping):
                message = value.get("message") or value.get("detail")
                if message:
                    return str(message)
            if value:
                return str(value)
    return f"image generation task failed: {task_id}"


def _image_generation_payload_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = payload.get("data")
    records: list[Mapping[str, Any]] = []
    if isinstance(data, Mapping):
        records.append(data)
    elif isinstance(data, list):
        records.extend(item for item in data if isinstance(item, Mapping))
    records.append(payload)
    for record in tuple(records):
        result = record.get("result")
        if not isinstance(result, Mapping):
            continue
        images = result.get("images")
        if isinstance(images, list):
            for image in images:
                if not isinstance(image, Mapping):
                    continue
                url = image.get("url")
                if isinstance(url, str):
                    records.append({"url": url})
                elif isinstance(url, list):
                    records.extend({"url": item} for item in url if isinstance(item, str) and item)
                else:
                    records.append(image)
    return records


def _image_generation_error_detail(exc: urllib.error.HTTPError) -> str:
    raw = exc.read()
    text = raw.decode("utf-8", errors="replace") if raw else ""
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, Mapping):
            error = payload.get("error")
            if isinstance(error, Mapping) and error.get("message"):
                return str(error.get("message"))
            if payload.get("detail"):
                return str(payload.get("detail"))
            if payload.get("message"):
                return str(payload.get("message"))
        return text[:500]
    return f"image generation upstream returned HTTP {exc.code}"


def _read_images_api_request(
    request: urllib.request.Request,
    *,
    timeout: float,
    operation: str,
) -> bytes:
    attempts = _optional_positive_int_env("DRAWAI_IMAGEGEN_RETRY_ATTEMPTS") or _DEFAULT_RETRY_ATTEMPTS
    delay = _optional_positive_float_env("DRAWAI_IMAGEGEN_RETRY_DELAY_SECONDS") or _DEFAULT_RETRY_DELAY_SECONDS
    for attempt in range(1, attempts + 1):
        try:
            with urlopen_external(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = _image_generation_error_detail(exc)
            if attempt < attempts and _retryable_http_status(exc.code):
                time.sleep(delay * attempt)
                continue
            raise HTTPException(status_code=exc.code or 502, detail=detail) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < attempts:
                time.sleep(delay * attempt)
                continue
            raise HTTPException(status_code=502, detail=f"{operation} request failed: {exc}") from exc
    raise RuntimeError(f"{operation} request retry loop exhausted unexpectedly")


def _retryable_http_status(status_code: int | None) -> bool:
    return int(status_code or 0) in _TRANSIENT_HTTP_STATUS_CODES


def _image_suffix_from_mime(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type.lower(), ".png")


def _media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _safe_download_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return stem or "drawai_image"


def _unique_upload_path(path: Path) -> Path:
    if not path.exists():
        return path
    parent = path.parent
    stem = path.stem or "upload"
    suffix = path.suffix
    index = 2
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _optional_positive_float_env(name: str) -> float | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _optional_positive_int_env(name: str) -> int | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


__all__ = [
    "asset_prepare_image_providers",
    "asset_prepare_image_providers_from_settings",
    "call_image_edit_upstream",
    "call_image_generation_upstream",
    "call_image_reference_edit_upstream",
    "image_edit_api_url",
    "image_generation_api_url",
    "images_api_edit_provider",
    "images_api_generate_provider",
]
