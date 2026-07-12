#!/usr/bin/env python3
"""Resolve, validate, and probe the external DrawAI model-service connection.

The local Skill keeps DrawAI orchestration and vector reconstruction.  Only SAM3, PaddleOCR, and
RMBG inference lives on the external server.  Secrets stay in the environment and never enter a
generated YAML config or JSON report.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _dotenv  # noqa: E402,F401

ENGINE = HERE.parent / "engine"
sys.path.insert(0, str(ENGINE / "src"))
from drawai.http_utils import urlopen_direct_for_loopback  # noqa: E402

EXPECTED_ENDPOINTS = {
    "sam3": "/v1/segment/proposals",
    "ocr": "/v1/ocr/boxes",
    "rmbg": "/v1/rmbg/remove-background",
}
ACCELERATED_MODELS = frozenset({"sam3", "rmbg"})


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    value = float(raw) if raw else default
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g} seconds")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    value = int(raw) if raw else default
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _validated_url(name: str, value: str, allow_insecure_http: bool) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        raise ValueError(f"{name} is required")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{name} must not contain credentials; use DRAWAI_REMOTE_API_KEY")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{name} must not contain query credentials or fragments")
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme == "http" and not loopback and not allow_insecure_http:
        raise ValueError(
            f"{name} uses clear-text HTTP for a non-loopback host; use HTTPS, an SSH tunnel, "
            "or explicitly set DRAWAI_REMOTE_ALLOW_INSECURE_HTTP=1"
        )
    return value


@dataclass(frozen=True)
class RemoteRuntimeSettings:
    sam3_url: str
    ocr_url: str
    rmbg_url: str
    request_timeout_seconds: float
    queue_timeout_seconds: float
    queue_max_polls: int
    health_timeout_seconds: float
    health_attempts: int
    retry_max_attempts: int
    require_accelerator: bool
    auth_configured: bool
    ca_bundle_configured: bool

    def service_urls(self) -> dict[str, str]:
        return {"sam3": self.sam3_url, "ocr": self.ocr_url, "rmbg": self.rmbg_url}

    def public_dict(self) -> dict[str, Any]:
        return {
            "services": self.service_urls(),
            "request_timeout_seconds": self.request_timeout_seconds,
            "queue_timeout_seconds": self.queue_timeout_seconds,
            "queue_max_polls": self.queue_max_polls,
            "health_timeout_seconds": self.health_timeout_seconds,
            "health_attempts": self.health_attempts,
            "retry_max_attempts": self.retry_max_attempts,
            "require_accelerator": self.require_accelerator,
            "auth_configured": self.auth_configured,
            "ca_bundle_configured": self.ca_bundle_configured,
        }


def load_settings() -> RemoteRuntimeSettings:
    base = os.environ.get("DRAWAI_REMOTE_BASE_URL", "").strip()
    allow_insecure = _truthy(os.environ.get("DRAWAI_REMOTE_ALLOW_INSECURE_HTTP"))
    urls = {}
    for service in ("sam3", "ocr", "rmbg"):
        env_name = f"DRAWAI_REMOTE_{service.upper()}_URL"
        urls[service] = _validated_url(env_name, os.environ.get(env_name, "").strip() or base, allow_insecure)
    return RemoteRuntimeSettings(
        sam3_url=urls["sam3"],
        ocr_url=urls["ocr"],
        rmbg_url=urls["rmbg"],
        request_timeout_seconds=_bounded_float("DRAWAI_REMOTE_REQUEST_TIMEOUT_SECONDS", 600, 30, 1800),
        queue_timeout_seconds=_bounded_float("DRAWAI_REMOTE_QUEUE_TIMEOUT_SECONDS", 180, 10, 900),
        queue_max_polls=_bounded_int("DRAWAI_REMOTE_QUEUE_MAX_POLLS", 180, 1, 300),
        health_timeout_seconds=_bounded_float("DRAWAI_REMOTE_HEALTH_TIMEOUT_SECONDS", 10, 1, 30),
        health_attempts=_bounded_int("DRAWAI_REMOTE_HEALTH_ATTEMPTS", 2, 1, 3),
        retry_max_attempts=_bounded_int("DRAWAI_REMOTE_RETRY_MAX_ATTEMPTS", 3, 1, 5),
        require_accelerator=not _truthy(os.environ.get("DRAWAI_REMOTE_ALLOW_CPU_HEAVY_MODELS")),
        auth_configured=bool(os.environ.get("DRAWAI_REMOTE_API_KEY", "").strip()),
        ca_bundle_configured=bool(os.environ.get("DRAWAI_REMOTE_CA_BUNDLE", "").strip()),
    )


def apply_environment(settings: RemoteRuntimeSettings) -> None:
    timeout = str(settings.queue_timeout_seconds)
    os.environ["DRAWAI_SAM3_QUEUE_TIMEOUT_SECONDS"] = timeout
    os.environ["DRAWAI_OCR_QUEUE_TIMEOUT_SECONDS"] = timeout
    os.environ["DRAWAI_REMOTE_QUEUE_MAX_POLLS"] = str(settings.queue_max_polls)
    os.environ["DRAWAI_REMOTE_RETRY_MAX_ATTEMPTS"] = str(settings.retry_max_attempts)


def write_resolved_config(base_config: Path, output: Path, settings: RemoteRuntimeSettings) -> Path:
    payload = yaml.safe_load(base_config.read_text(encoding="utf-8")) or {}
    payload.setdefault("sam3", {})["base_url"] = settings.sam3_url
    payload["sam3"]["timeout_seconds"] = settings.request_timeout_seconds
    ocr = payload.setdefault("ocr", {})
    ocr["provider"] = "remote_paddleocr"
    ocr.setdefault("remote_paddleocr", {})["base_url"] = settings.ocr_url
    ocr["remote_paddleocr"]["timeout_seconds"] = settings.request_timeout_seconds
    rmbg = payload.setdefault("asset_materialization", {}).setdefault("rmbg", {})
    rmbg.update({
        "enabled": True,
        "provider": "service",
        "base_url": settings.rmbg_url,
        "timeout_seconds": settings.request_timeout_seconds,
        "model_path": "",
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return output


def validate_binding(config_path: Path, settings: RemoteRuntimeSettings) -> list[str]:
    """Prove that the generated case will call only the declared external services."""
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - configuration boundary
        return [f"remote config unreadable: {exc}"]
    actual = {
        "sam3": (payload.get("sam3") or {}).get("base_url"),
        "ocr": ((payload.get("ocr") or {}).get("remote_paddleocr") or {}).get("base_url"),
        "rmbg": ((payload.get("asset_materialization") or {}).get("rmbg") or {}).get("base_url"),
    }
    issues = [
        f"{service} remote binding mismatch: {actual.get(service)!r} != {url!r}"
        for service, url in settings.service_urls().items() if actual.get(service) != url
    ]
    timeout_values = {
        "sam3": (payload.get("sam3") or {}).get("timeout_seconds"),
        "ocr": ((payload.get("ocr") or {}).get("remote_paddleocr") or {}).get("timeout_seconds"),
        "rmbg": ((payload.get("asset_materialization") or {}).get("rmbg") or {}).get("timeout_seconds"),
    }
    for service, value in timeout_values.items():
        try:
            timeout_matches = float(value or 0) == settings.request_timeout_seconds
        except (TypeError, ValueError):
            timeout_matches = False
        if not timeout_matches:
            issues.append(
                f"{service} request timeout mismatch: {value!r} != {settings.request_timeout_seconds!r}"
            )
    if str((payload.get("ocr") or {}).get("provider") or "") != "remote_paddleocr":
        issues.append("OCR provider is not remote_paddleocr")
    rmbg = (payload.get("asset_materialization") or {}).get("rmbg") or {}
    if rmbg.get("provider") != "service" or rmbg.get("enabled") is not True:
        issues.append("RMBG is not bound to the external service provider")
    secret = os.environ.get("DRAWAI_REMOTE_API_KEY", "").strip()
    if secret and secret in config_path.read_text(encoding="utf-8"):
        issues.append("remote API key leaked into generated YAML")
    return issues


def _health_payload(base_url: str, settings: RemoteRuntimeSettings) -> tuple[dict[str, Any], str]:
    errors = []
    for suffix in ("/health", "/v1/health"):
        url = f"{base_url}{suffix}"
        for attempt in range(1, settings.health_attempts + 1):
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            try:
                with urlopen_direct_for_loopback(
                    request, url, timeout=settings.health_timeout_seconds
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("health response is not a JSON object")
                return payload, url
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    errors.append(f"{url}: HTTP 404")
                    break
                errors.append(f"{url}: HTTP {exc.code}")
            except Exception as exc:  # noqa: BLE001 - bounded connection boundary
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
            if attempt < settings.health_attempts:
                time.sleep(min(0.5 * attempt, 1.0))
    raise RuntimeError("; ".join(errors[-4:]))


def probe(settings: RemoteRuntimeSettings) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    errors: list[str] = []
    payload_by_url: dict[str, tuple[dict[str, Any], str]] = {}
    for service, base_url in settings.service_urls().items():
        if base_url not in payload_by_url:
            try:
                payload_by_url[base_url] = _health_payload(base_url, settings)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{service} health failed: {exc}")
                continue
        payload, health_url = payload_by_url[base_url]
        services = payload.get("services") if isinstance(payload.get("services"), dict) else {}
        detail = services.get(service) if isinstance(services.get(service), dict) else None
        if str(payload.get("status") or "").lower() != "ok":
            errors.append(f"{service} server status is not ok")
        if detail is None:
            errors.append(f"{service} is absent from remote health contract")
            continue
        if detail.get("endpoint") != EXPECTED_ENDPOINTS[service]:
            errors.append(
                f"{service} endpoint mismatch: {detail.get('endpoint')!r} != {EXPECTED_ENDPOINTS[service]!r}"
            )
        device = str(detail.get("device") or "").lower()
        if settings.require_accelerator and service in ACCELERATED_MODELS and not any(
            token in device for token in ("cuda", "gpu")
        ):
            errors.append(f"{service} heavy model is not reported on a GPU device: {device or 'missing'}")
        reports[service] = {
            "base_url": base_url,
            "health_url": health_url,
            "endpoint": detail.get("endpoint"),
            "device": detail.get("device"),
        }
    return {
        "schema": "ts.drawai.remote_runtime_preflight.v1",
        "ok": not errors and set(reports) == set(EXPECTED_ENDPOINTS),
        "connection": settings.public_dict(),
        "services": reports,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-config", default=str(ENGINE / "configs" / "drawai" / "config.yaml"))
    parser.add_argument("--write-config", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args()
    try:
        settings = load_settings()
        apply_environment(settings)
        if args.write_config:
            write_resolved_config(Path(args.base_config).resolve(), Path(args.write_config).resolve(), settings)
        report = {
            "schema": "ts.drawai.remote_runtime_preflight.v1",
            "ok": True,
            "connection": settings.public_dict(),
            "services": {},
            "errors": [],
        } if args.config_only else probe(settings)
    except Exception as exc:  # noqa: BLE001
        report = {"schema": "ts.drawai.remote_runtime_preflight.v1", "ok": False,
                  "connection": {}, "services": {}, "errors": [f"{type(exc).__name__}: {exc}"]}
    if args.report:
        path = Path(args.report).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
