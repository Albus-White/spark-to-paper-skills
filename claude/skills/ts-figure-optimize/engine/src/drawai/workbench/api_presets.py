from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin, urlparse
import urllib.error
import urllib.request


API_PRESETS_SCHEMA = "drawai.workbench.api_presets.v1"
SUPPORTED_API_PRESET_TYPES = ("images_api", "llm_chat_completions", "llm_responses")


@dataclass(frozen=True)
class ApiPreset:
    id: str
    label: str
    type: str
    base_url: str
    model: str
    api_key_env: str = ""
    api_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def api_presets_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve(strict=False) / "settings" / "api_presets.json"


def read_workbench_api_presets(workspace: str | Path) -> tuple[ApiPreset, ...]:
    path = api_presets_path(workspace)
    if not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Workbench API presets must be a JSON object: {path}")
    return normalize_workbench_api_presets(payload)


def write_workbench_api_presets(workspace: str | Path, payload: Mapping[str, Any]) -> tuple[ApiPreset, ...]:
    presets = normalize_workbench_api_presets(payload)
    path = api_presets_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_api_presets_document(presets), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return presets


def workbench_api_presets_payload(workspace: str | Path) -> dict[str, Any]:
    return _api_presets_document(read_workbench_api_presets(workspace))


def normalize_workbench_api_presets(payload: Mapping[str, Any] | None) -> tuple[ApiPreset, ...]:
    data = dict(payload or {})
    raw_presets = data.get("presets", ())
    if not isinstance(raw_presets, Sequence) or isinstance(raw_presets, str | bytes):
        raise ValueError("API presets payload must contain a presets array")
    presets: list[ApiPreset] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_presets):
        if not isinstance(item, Mapping):
            raise ValueError(f"presets[{index}] must be an object")
        preset = _normalize_api_preset(item, index)
        if preset.id in seen:
            raise ValueError(f"duplicate API preset id: {preset.id}")
        seen.add(preset.id)
        presets.append(preset)
    return tuple(presets)


def api_preset_by_id(presets: Sequence[ApiPreset], preset_id: str) -> ApiPreset | None:
    return next((preset for preset in presets if preset.id == preset_id), None)


def _normalize_api_preset(item: Mapping[str, Any], index: int) -> ApiPreset:
    preset_id = _required_slug(item.get("id"), f"presets[{index}].id")
    preset_type = _required_string(item.get("type"), f"presets[{index}].type")
    if preset_type not in SUPPORTED_API_PRESET_TYPES:
        supported = ", ".join(SUPPORTED_API_PRESET_TYPES)
        raise ValueError(f"unsupported API preset type: {preset_type!r}. Expected one of: {supported}")
    label = str(item.get("label") or preset_id).strip()
    base_url = _required_string(item.get("base_url"), f"presets[{index}].base_url").rstrip("/")
    model = _required_string(item.get("model"), f"presets[{index}].model")
    api_key_env = str(item.get("api_key_env") or "").strip()
    api_key = str(item.get("api_key") or "").strip()
    return ApiPreset(
        id=preset_id,
        label=label,
        type=preset_type,
        base_url=base_url,
        model=model,
        api_key_env=api_key_env,
        api_key=api_key,
    )


def _api_presets_document(presets: Sequence[ApiPreset]) -> dict[str, Any]:
    return {
        "schema": API_PRESETS_SCHEMA,
        "preset_types": list(SUPPORTED_API_PRESET_TYPES),
        "presets": [preset.to_dict() for preset in presets],
    }


def _required_slug(value: Any, field_name: str) -> str:
    text = _required_string(value, field_name)
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(char not in allowed for char in text):
        raise ValueError(f"{field_name} must contain only letters, numbers, underscore, or hyphen")
    return text


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def resolve_api_preset_logo_url(base_url: str, timeout_seconds: float = 3.0) -> str:
    for page_url in api_preset_logo_page_urls(base_url):
        try:
            request = urllib.request.Request(
                page_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "DrawAI Workbench logo resolver",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                content = response.read(512_000)
                encoding = response.headers.get_content_charset() or "utf-8"
                html = content.decode(encoding, errors="replace")
        except (OSError, UnicodeError, urllib.error.URLError):
            continue
        logo_url = api_preset_logo_url_from_html(response.geturl() or page_url, html)
        if logo_url:
            return logo_url
    return ""


def api_preset_logo_page_urls(base_url: str) -> tuple[str, ...]:
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ()
    hostname = parsed.hostname.lower().rstrip(".")
    if _is_local_logo_host(hostname):
        return ()
    candidates: list[str] = [f"{parsed.scheme}://{parsed.netloc}/"]
    brand_host = _brand_host_for_api_hostname(hostname)
    if brand_host and brand_host != hostname:
        candidates.append(f"{parsed.scheme}://{brand_host}/")
        candidates.append(f"{parsed.scheme}://www.{brand_host}/")
    return tuple(dict.fromkeys(candidates))


def api_preset_logo_url_from_html(page_url: str, html: str) -> str:
    parser = _ApiPresetLogoHtmlParser()
    parser.feed(html)
    parser.close()
    for href in parser.icon_hrefs:
        resolved = _resolved_http_url(page_url, href)
        if resolved:
            return resolved
    for payload in parser.json_ld_payloads:
        logo_url = _logo_url_from_json_ld_payload(page_url, payload)
        if logo_url:
            return logo_url
    return ""


def _brand_host_for_api_hostname(hostname: str) -> str:
    if hostname.startswith("api."):
        return hostname.removeprefix("api.")
    parts = hostname.split(".")
    if len(parts) >= 3 and parts[0] in {"api", "gateway", "proxy"}:
        return ".".join(parts[1:])
    return ""


def _resolved_http_url(page_url: str, href: str) -> str:
    text = href.strip()
    if not text:
        return ""
    resolved = urljoin(page_url, text)
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return resolved


def _logo_url_from_json_ld_payload(page_url: str, payload: str) -> str:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    logo_url = _find_logo_url(data)
    return _resolved_http_url(page_url, logo_url) if logo_url else ""


def _find_logo_url(value: Any) -> str:
    if isinstance(value, Mapping):
        logo = value.get("logo")
        if isinstance(logo, str):
            return logo
        if isinstance(logo, Mapping):
            url = logo.get("url")
            if isinstance(url, str):
                return url
        if isinstance(logo, Sequence) and not isinstance(logo, str | bytes):
            for item in logo:
                found = _find_logo_url({"logo": item})
                if found:
                    return found
        for item in value.values():
            found = _find_logo_url(item)
            if found:
                return found
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            found = _find_logo_url(item)
            if found:
                return found
    return ""


class _ApiPresetLogoHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.icon_hrefs: list[str] = []
        self.json_ld_payloads: list[str] = []
        self._json_ld_depth = 0
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "link":
            rel_tokens = set(attributes.get("rel", "").lower().split())
            if {"icon", "apple-touch-icon", "mask-icon", "shortcut"}.intersection(rel_tokens):
                href = attributes.get("href", "")
                if href:
                    self.icon_hrefs.append(href)
        if tag.lower() == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self._json_ld_depth += 1
            self._json_ld_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._json_ld_depth:
            self._json_ld_depth -= 1
            payload = "".join(self._json_ld_parts).strip()
            if payload:
                self.json_ld_payloads.append(payload)
            self._json_ld_parts = []

    def handle_data(self, data: str) -> None:
        if self._json_ld_depth:
            self._json_ld_parts.append(data)


def _is_local_logo_host(hostname: str) -> bool:
    return (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname == "::1"
        or hostname == "0.0.0.0"
        or hostname.startswith("127.")
    )


__all__ = [
    "API_PRESETS_SCHEMA",
    "SUPPORTED_API_PRESET_TYPES",
    "ApiPreset",
    "api_preset_logo_page_urls",
    "api_preset_logo_url_from_html",
    "api_preset_by_id",
    "api_presets_path",
    "normalize_workbench_api_presets",
    "read_workbench_api_presets",
    "workbench_api_presets_payload",
    "write_workbench_api_presets",
]
