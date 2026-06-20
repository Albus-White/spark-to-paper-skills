from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .artifacts import DrawAiArtifactPaths, write_json
from .config import Sam3Config
from .http_utils import model_busy_retry_after_seconds, urlopen_direct_for_loopback
from .overlays import render_sam_prompt_overlay
from .prompt_plan import Sam3Prompt

SAM3_PROPOSALS_PATH = "/v1/segment/proposals"
DEFAULT_MODEL_QUEUE_TIMEOUT_SECONDS = 600.0


class Sam3ResponseError(ValueError):
    """Raised when the SAM3 service returns a malformed JSON response."""


class JsonTransport(Protocol):
    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], float]:
        ...


@dataclass(frozen=True)
class Sam3PromptRun:
    prompt_id: str
    regions: list[Any]
    raw_regions: list[Any]
    artifacts: dict[str, Any]
    artifact_path: Path
    elapsed_ms: float


@dataclass(frozen=True)
class Sam3PromptPlanResult:
    prompt_runs: tuple[Sam3PromptRun, ...]
    raw_regions: list[Any]


class HttpJsonTransport:
    def __init__(self, base_url: str, queue_timeout_s: float | None = None):
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
                raise Sam3ResponseError(
                    _transport_error_message(
                        "SAM3 HTTP error",
                        self.base_url,
                        path,
                        timeout_s,
                        http_status=exc.code,
                        body_excerpt=body_excerpt,
                    )
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise Sam3ResponseError(
                    _transport_error_message(
                        "SAM3 request failed",
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
            raise Sam3ResponseError(
                _transport_error_message(
                    "SAM3 response contained malformed JSON",
                    self.base_url,
                    path,
                    timeout_s,
                    body_excerpt=_short_excerpt(response_text),
                )
            ) from exc
        if not isinstance(decoded, dict):
            raise Sam3ResponseError(
                _transport_error_message(
                    "SAM3 response must be a JSON object",
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
        queue_timeout_s = _queue_timeout_seconds(self.queue_timeout_s, "DRAWAI_SAM3_QUEUE_TIMEOUT_SECONDS")
        if time.monotonic() - queue_started + retry_after > queue_timeout_s:
            raise Sam3ResponseError(
                _transport_error_message(
                    "SAM3 service stayed busy",
                    self.base_url,
                    path,
                    timeout_s,
                    http_status=cause.code,
                    cause=f"queue_timeout_s={queue_timeout_s:g}",
                )
            ) from cause
        time.sleep(retry_after)


def run_sam3_prompt_plan(
    sam3_config: Sam3Config,
    image_path: str | Path,
    artifact_paths: DrawAiArtifactPaths,
    transport: JsonTransport | None = None,
) -> Sam3PromptPlanResult:
    image_path = Path(image_path)
    image_base64 = _read_image_base64(image_path)
    active_transport = transport or HttpJsonTransport(sam3_config.base_url)
    prompt_runs: list[Sam3PromptRun] = []
    all_raw_regions: list[Any] = []

    for prompt in sam3_config.prompts:
        prompt_id = _safe_prompt_id(prompt.id)
        artifact_path = artifact_paths.prompt_runs_dir / f"{prompt_id}.json"
        artifact_prefix = f"sam3/prompt_runs/{prompt_id}"
        prompt_payload = _prompt_to_payload(prompt)
        request_payload = {
            "image_base64": image_base64,
            "artifact_prefix": artifact_prefix,
            "prompts": [prompt_payload],
            "merge_threshold": sam3_config.service_merge_threshold,
            "return_overlay": sam3_config.return_overlay,
            "return_masks": sam3_config.return_masks,
        }

        try:
            response_payload, elapsed_ms = active_transport.post_json(
                SAM3_PROPOSALS_PATH,
                request_payload,
                sam3_config.timeout_seconds,
            )
            regions = _require_regions(response_payload, prompt.id)
            artifacts = _normalize_artifacts(response_payload.get("artifacts"))
            response_raw_regions = _normalize_raw_regions(response_payload.get("raw_regions"), prompt.id)
            response_raw_regions = _localize_raw_region_masks(
                response_raw_regions,
                artifacts,
                prompt.id,
                artifact_paths,
            )
            raw_regions = _with_prompt_provenance(response_raw_regions, prompt)
        except Sam3ResponseError as exc:
            raise Sam3ResponseError(_with_run_error_context(str(exc), sam3_config, prompt.id)) from exc
        except Exception as exc:
            raise Sam3ResponseError(
                _with_run_error_context(f"{type(exc).__name__}: {exc}", sam3_config, prompt.id)
            ) from exc

        normalized_response = dict(response_payload)
        normalized_response["raw_regions"] = response_raw_regions
        normalized_response["artifacts"] = artifacts
        sanitized_regions = _sanitize_inline_image_data(regions)
        sanitized_raw_regions = _sanitize_inline_image_data(raw_regions)
        sanitized_response = _sanitize_inline_image_data(normalized_response)
        sanitized_artifacts = _sanitize_inline_image_data(artifacts)
        review_overlay_path = artifact_paths.sam_prompt_overlays_dir / f"{prompt_id}.png"
        review_overlay_legend = render_sam_prompt_overlay(
            image_path,
            prompt.id,
            sanitized_regions,
            review_overlay_path,
        )

        run_payload = {
            "prompt_id": prompt.id,
            "request": _sanitize_request_payload(request_payload, image_path),
            "response": sanitized_response,
            "regions": sanitized_regions,
            "raw_regions": sanitized_raw_regions,
            "artifacts": sanitized_artifacts,
            "artifact_path": str(artifact_path),
            "review_overlay_path": str(review_overlay_path),
            "review_overlay_legend": review_overlay_legend,
            "elapsed_ms": elapsed_ms,
        }
        write_json(artifact_path, run_payload)

        prompt_run = Sam3PromptRun(
            prompt_id=prompt.id,
            regions=sanitized_regions,
            raw_regions=sanitized_raw_regions,
            artifacts=sanitized_artifacts,
            artifact_path=artifact_path,
            elapsed_ms=elapsed_ms,
        )
        prompt_runs.append(prompt_run)
        all_raw_regions.extend(sanitized_raw_regions)

    write_json(
        artifact_paths.raw_regions_json,
        {
            "raw_regions": all_raw_regions,
            "prompt_runs": [
                {
                    "prompt_id": run.prompt_id,
                    "artifact_path": str(run.artifact_path),
                    "review_overlay_path": str(
                        artifact_paths.sam_prompt_overlays_dir / f"{_safe_prompt_id(run.prompt_id)}.png"
                    ),
                    "elapsed_ms": run.elapsed_ms,
                }
                for run in prompt_runs
            ],
        },
    )
    return Sam3PromptPlanResult(prompt_runs=tuple(prompt_runs), raw_regions=all_raw_regions)


def _read_image_base64(image_path: str | Path) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode("ascii")


def _prompt_to_payload(prompt: Sam3Prompt) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": prompt.id,
        "text": prompt.text,
        "confidence_threshold": prompt.confidence_threshold,
    }
    for field_name in ("level", "max_masks"):
        value = getattr(prompt, field_name, None)
        if value is not None:
            payload[field_name] = value
    return payload


def _require_regions(response_payload: dict[str, Any], prompt_id: str) -> list[Any]:
    regions = response_payload.get("regions")
    if not isinstance(regions, list):
        raise Sam3ResponseError(
            f"SAM3 response for prompt {prompt_id!r} field 'regions' must be a list"
        )
    return regions


def _normalize_raw_regions(raw_regions: Any, prompt_id: str) -> list[Any]:
    if raw_regions is None:
        return []
    if not isinstance(raw_regions, list):
        raise Sam3ResponseError(
            f"SAM3 response for prompt {prompt_id!r} field 'raw_regions' must be a list"
        )
    return list(raw_regions)


def _with_prompt_provenance(raw_regions: list[Any], prompt: Sam3Prompt) -> list[Any]:
    source_prompt = _prompt_to_payload(prompt)
    normalized: list[Any] = []
    for region in raw_regions:
        if isinstance(region, dict):
            region_payload = dict(region)
        else:
            region_payload = {"value": region}
        if "source_prompt" in region_payload:
            region_payload["sam3_source_prompt"] = region_payload.pop("source_prompt")
        region_payload["source_prompt"] = prompt.id
        region_payload["source_prompt_meta"] = source_prompt
        normalized.append(region_payload)
    return normalized


def _normalize_artifacts(artifacts: Any) -> dict[str, Any]:
    if artifacts is None:
        return {}
    if not isinstance(artifacts, dict):
        raise Sam3ResponseError("SAM3 response field 'artifacts' must be a mapping")
    return dict(artifacts)


def _localize_raw_region_masks(
    raw_regions: list[Any],
    artifacts: Mapping[str, Any],
    prompt_id: str,
    artifact_paths: DrawAiArtifactPaths,
) -> list[Any]:
    localized_regions: list[Any] = []
    for index, raw_region in enumerate(raw_regions, start=1):
        if not isinstance(raw_region, dict):
            localized_regions.append(raw_region)
            continue
        region = dict(raw_region)
        mask_path = _region_mask_path(region)
        if not mask_path:
            localized_regions.append(region)
            continue
        source = _resolve_response_mask_path(mask_path, artifacts, artifact_paths)
        if source is None:
            raise Sam3ResponseError(
                f"SAM3 response mask_path could not be resolved for prompt {prompt_id!r}: {mask_path!r}"
            )
        artifact_paths.sam_masks_dir.mkdir(parents=True, exist_ok=True)
        mask_name = _localized_mask_name(prompt_id, index, source.name)
        destination = artifact_paths.sam_masks_dir / mask_name
        if source.resolve(strict=False) != destination.resolve(strict=False):
            shutil.copy2(source, destination)
        relative_mask_path = destination.relative_to(artifact_paths.root).as_posix()
        _set_region_mask_path(region, relative_mask_path)
        localized_regions.append(region)
    return localized_regions


def _region_mask_path(region: Mapping[str, Any]) -> str:
    value = region.get("mask_path")
    if isinstance(value, str) and value.strip():
        return value.strip()
    geometry = region.get("geometry")
    if isinstance(geometry, Mapping):
        value = geometry.get("mask_path")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _set_region_mask_path(region: dict[str, Any], mask_path: str) -> None:
    region["mask_path"] = mask_path
    geometry = dict(region.get("geometry")) if isinstance(region.get("geometry"), Mapping) else {}
    geometry["kind"] = "mask"
    geometry["mask_path"] = mask_path
    if "bbox" in region:
        geometry["bbox"] = region["bbox"]
    geometry["coordinate_system"] = "figure_image_pixels"
    region["geometry"] = geometry


def _resolve_response_mask_path(
    mask_path: str,
    artifacts: Mapping[str, Any],
    artifact_paths: DrawAiArtifactPaths,
) -> Path | None:
    raw = Path(mask_path).expanduser()
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        for key in ("mask_dir", "masks_dir"):
            value = artifacts.get(key)
            if isinstance(value, str) and value.strip():
                mask_dir = Path(value).expanduser()
                candidates.append(mask_dir / raw.name)
                candidates.append(mask_dir.parent / raw)
        regions_json = artifacts.get("regions_json")
        if isinstance(regions_json, str) and regions_json.strip():
            candidates.append(Path(regions_json).expanduser().parent / raw)
        candidates.append(artifact_paths.root / raw)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _localized_mask_name(prompt_id: str, index: int, source_name: str) -> str:
    source_suffix = Path(source_name).suffix.lower() or ".png"
    source_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(source_name).stem).strip("._-") or "mask"
    return f"{_safe_prompt_id(prompt_id)}_{index:03d}_{source_stem}{source_suffix}"


def _safe_prompt_id(prompt_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", prompt_id).strip("._")
    if not safe_id:
        raise ValueError(f"sam3 prompt id {prompt_id!r} cannot be used as an artifact name")
    return safe_id


def _sanitize_request_payload(payload: dict[str, Any], image_path: Path) -> dict[str, Any]:
    sanitized = dict(payload)
    image_base64 = sanitized.pop("image_base64", "")
    image_bytes = image_path.read_bytes()
    sanitized.update(
        {
            "image_path": str(image_path),
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "image_bytes": len(image_bytes),
            "image_base64_chars": len(image_base64),
        }
    )
    return sanitized


def _sanitize_inline_image_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_inline_image_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_inline_image_data(item) for item in value]
    if isinstance(value, str):
        match = re.fullmatch(r"data:(image/[^;,]+);base64,(.*)", value, flags=re.DOTALL)
        if match:
            return {
                "redacted": True,
                "kind": "inline_image_base64",
                "mime_type": match.group(1),
                "base64_chars": len(match.group(2)),
            }
    return value


def _with_run_error_context(message: str, sam3_config: Sam3Config, prompt_id: str) -> str:
    return (
        f"{message}; prompt_id={prompt_id!r}; endpoint={SAM3_PROPOSALS_PATH!r}; "
        f"base_url={sam3_config.base_url!r}; timeout_s={sam3_config.timeout_seconds!r}"
    )


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


def _queue_timeout_seconds(raw_value: float | None, env_name: str) -> float:
    value = raw_value
    if value is None:
        env_value = os.environ.get(env_name) or os.environ.get("DRAWAI_MODEL_QUEUE_TIMEOUT_SECONDS")
        value = DEFAULT_MODEL_QUEUE_TIMEOUT_SECONDS if env_value is None else float(env_value)
    value = float(value)
    if value <= 0:
        raise Sam3ResponseError(f"{env_name} must be positive")
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
