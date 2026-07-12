from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import hashlib
import os
import re
import signal
import shutil
import sqlite3
import tempfile
import threading
import time
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import model_runtime


CODEX_PYTHON_SDK_RUNNER = "codex_python_sdk_controlled"
DEFAULT_CODEX_REASONING_EFFORT = "xhigh"
CODEX_DOCTOR_REASONING_EFFORT = "low"
CODEX_REASONING_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh"}
)
CODEX_SESSION_LOG_ARCHIVE_SCHEMA = "drawai.codex_session_log_archive.v1"
CODEX_SDK_TURN_RESULT_SCHEMA = "drawai.codex_sdk_turn_result.v1"
CODEX_SDK_SESSION_EVENT_SCHEMA = "drawai.codex_sdk_session_event.v1"
CODEX_SESSION_LOG_DIRS = ("sessions", "log", "logs", "shell_snapshots")
CODEX_SESSION_LOG_FILES = (
    "history.jsonl",
    "session_index.jsonl",
)
CODEX_SESSION_RUNTIME_STATE_FILES = (
    "logs_2.sqlite",
    "logs_2.sqlite-shm",
    "logs_2.sqlite-wal",
    "state_5.sqlite",
    "state_5.sqlite-shm",
    "state_5.sqlite-wal",
)
CODEX_RUNTIME_EVENT_TAIL_FILE = "codex_runtime_events.jsonl"
CODEX_FAST_SERVICE_TIER = "priority"


class CodexPythonSdkSvgError(RuntimeError):
    """Raised when the controlled Codex Python SDK SVG runner cannot return SVG text."""


def build_codex_svg_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["svg"],
        "properties": {
            "svg": {
                "type": "string",
                "description": "A complete SVG document string starting with <svg and ending with </svg>.",
            }
        },
    }


def controlled_codex_config_overrides(
    extra_overrides: Sequence[str] | None = None,
    *,
    runtime_config: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    overrides = (
        'web_search="disabled"',
        "features.shell_tool=true",
        "features.rmcp_client=false",
        "features.multi_agent=false",
        "features.memories=false",
        "features.hooks=false",
        "features.apps=false",
        "project_doc_max_bytes=0",
        "project_doc_fallback_filenames=[]",
        'cli_auth_credentials_store="file"',
        "shell_environment_policy.ignore_default_excludes=false",
        'shell_environment_policy.exclude=["CODEX_HOME","DRAWAI_HOST_HOME","DRAWAI_HOST_CODEX_HOME"]',
        'sandbox_mode="danger-full-access"',
    )
    return (
        *overrides,
        *_host_codex_model_provider_overrides_from_env(),
        *_runtime_codex_model_provider_overrides(runtime_config),
        *(str(item) for item in (extra_overrides or ())),
    )


def _host_codex_model_provider_overrides_from_env() -> tuple[str, ...]:
    if not _env_truthy(os.environ.get("DRAWAI_CODEX_INHERIT_HOST_CONFIG")):
        return ()
    return host_codex_model_provider_overrides(_host_codex_home() / "config.toml")


def _runtime_codex_model_provider_overrides(runtime_config: Mapping[str, Any] | None) -> tuple[str, ...]:
    api_provider = _runtime_api_provider_config(runtime_config)
    if not api_provider or str(api_provider.get("mode") or "auth").strip().lower() != "thirdparty":
        return ()
    provider_name = str(api_provider.get("model_provider") or "drawai-relay").strip()
    base_url = str(api_provider.get("base_url") or "").strip()
    if not provider_name or not base_url:
        return ()
    model_name = str((runtime_config or {}).get("model_name") or "").strip()
    provider_key = _toml_dotted_key(provider_name)
    prefix = f"model_providers.{provider_key}"
    env_key = str(api_provider.get("env_key") or api_provider.get("api_key_env") or "OPENAI_API_KEY").strip()
    overrides: list[str] = [f"model_provider={_toml_string(provider_name)}"]
    if model_name:
        overrides.append(f"model={_toml_string(model_name)}")
    overrides.append(f"{prefix}.name={_toml_string(str(api_provider.get('name') or provider_name))}")
    wire_api = str(api_provider.get("wire_api") or "responses").strip()
    if wire_api:
        overrides.append(f"{prefix}.wire_api={_toml_string(wire_api)}")
    overrides.append(f"{prefix}.base_url={_toml_string(base_url)}")
    if env_key:
        overrides.append(f"{prefix}.env_key={_toml_string(env_key)}")
    requires_auth = api_provider.get("requires_openai_auth")
    if isinstance(requires_auth, bool):
        overrides.append(f"{prefix}.requires_openai_auth={str(requires_auth).lower()}")
    return tuple(overrides)


def host_codex_model_provider_overrides(config_path: str | Path) -> tuple[str, ...]:
    """Return safe model/provider -c overrides from a host Codex config."""

    path = Path(config_path).expanduser().resolve(strict=False)
    try:
        config_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except UnicodeDecodeError as exc:
        raise CodexPythonSdkSvgError(f"Host Codex config is not UTF-8: {path}") from exc
    try:
        payload = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as exc:
        raise CodexPythonSdkSvgError(f"Host Codex config is invalid TOML: {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        return ()

    provider_name = str(payload.get("model_provider") or "").strip()
    providers = payload.get("model_providers")
    if not provider_name or not isinstance(providers, Mapping):
        return ()
    provider = providers.get(provider_name)
    if not isinstance(provider, Mapping):
        return ()

    overrides: list[str] = [f"model_provider={_toml_string(provider_name)}"]
    model_name = str(os.environ.get("DRAWAI_CODEX_MODEL") or payload.get("model") or "").strip()
    if model_name:
        overrides.append(f"model={_toml_string(model_name)}")

    provider_key = _toml_dotted_key(provider_name)
    prefix = f"model_providers.{provider_key}"
    for key in ("name", "wire_api", "base_url", "env_key"):
        value = provider.get(key)
        if isinstance(value, str) and value.strip():
            overrides.append(f"{prefix}.{key}={_toml_string(value.strip())}")
    requires_auth = provider.get("requires_openai_auth")
    if isinstance(requires_auth, bool):
        overrides.append(f"{prefix}.requires_openai_auth={str(requires_auth).lower()}")
    return tuple(overrides)


def _env_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _toml_dotted_key(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z0-9_-]+", value) else _toml_string(value)


def _toml_string(value: str) -> str:
    return json.dumps(str(value))


def parse_svg_from_final_response(final_response: Any) -> tuple[str, dict[str, str]]:
    if not isinstance(final_response, str) or not final_response.strip():
        raise CodexPythonSdkSvgError("Codex Python SDK final_response was empty")
    text = final_response.strip()
    if text.startswith("<svg") and text.endswith("</svg>"):
        return text, {"source": "direct_svg"}
    payload = _json_object_from_text(text)
    svg = payload.get("svg")
    if not isinstance(svg, str) or not svg.strip():
        raise CodexPythonSdkSvgError(
            "Codex Python SDK final_response JSON did not contain non-empty svg"
        )
    return svg, {"source": "json_object", "field": "svg"}


def _append_codex_sdk_error_trace(
    trace: Path | None,
    *,
    task_name: str,
    started_at: float,
    exc: BaseException,
) -> str:
    safe_error = _safe_error_text(str(exc))
    model_runtime._append_trace(
        trace,
        {
            "type": "codex_python_sdk_error",
            "runner": CODEX_PYTHON_SDK_RUNNER,
            "task_name": task_name,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "error_type": type(exc).__name__,
            "error": safe_error,
        },
    )
    return safe_error


def _safe_error_text(text: str, *, max_chars: int = 2000) -> str:
    sanitized = re.sub(
        r"(?i)\b(Bearer|Basic)\s+([A-Za-z0-9._~+/=-]{20,}|[A-Za-z0-9._~+/=-]*[._~+/=-][A-Za-z0-9._~+/=-]*)",
        r"\1 <redacted>",
        text,
    )
    sanitized = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "sk-<redacted>", sanitized)
    if len(sanitized) > max_chars:
        return f"{sanitized[:max_chars]}..."
    return sanitized


@dataclass(frozen=True)
class PreparedCodexHome:
    codex_home: Path
    host_codex_home: Path
    auth_copied: bool
    agents_md_present: bool
    agents_override_present: bool

    def to_trace(self) -> dict[str, Any]:
        return {
            "isolated": True,
            "path": str(self.codex_home),
            "host_codex_home": str(self.host_codex_home),
            "auth_copied": self.auth_copied,
            "agents_md_present": self.agents_md_present,
            "agents_override_present": self.agents_override_present,
        }


@contextmanager
def _isolated_codex_home(_workspace_dir: Path):
    host_codex_home = _host_codex_home()
    with tempfile.TemporaryDirectory(
        prefix="drawai-codex-home-",
        ignore_cleanup_errors=True,
    ) as temporary_dir:
        codex_home = Path(temporary_dir).resolve(strict=True)
        auth_source = host_codex_home / "auth.json"
        auth_copied = False
        if auth_source.exists():
            shutil.copy2(auth_source, codex_home / "auth.json")
            auth_copied = True
        yield PreparedCodexHome(
            codex_home=codex_home,
            host_codex_home=host_codex_home,
            auth_copied=auth_copied,
            agents_md_present=(codex_home / "AGENTS.md").exists(),
            agents_override_present=(codex_home / "AGENTS.override.md").exists(),
        )


def _host_codex_home() -> Path:
    explicit = os.environ.get("DRAWAI_HOST_CODEX_HOME") or os.environ.get("CODEX_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve(strict=False)
    host_home = os.environ.get("DRAWAI_HOST_HOME") or os.environ.get("HOME")
    if host_home:
        return (Path(host_home).expanduser() / ".codex").resolve(strict=False)
    return (Path.home() / ".codex").resolve(strict=False)


def _codex_sdk_env(codex_home: Path, *, runtime_config: Mapping[str, Any] | None = None) -> dict[str, str]:
    env: dict[str, str] = {
        "CODEX_HOME": str(codex_home),
        "HOME": str(codex_home.parent),
    }
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if openai_api_key:
        env["OPENAI_API_KEY"] = openai_api_key
    api_provider = _runtime_api_provider_config(runtime_config)
    if api_provider and str(api_provider.get("mode") or "auth").strip().lower() == "thirdparty":
        env_key = str(api_provider.get("env_key") or api_provider.get("api_key_env") or "OPENAI_API_KEY").strip()
        api_key = str(api_provider.get("api_key") or "").strip()
        api_key_env = str(api_provider.get("api_key_env") or "").strip()
        if api_key_env and os.environ.get(api_key_env):
            env[env_key] = os.environ[api_key_env]
        elif api_key:
            env[env_key] = api_key
    return env


def _runtime_api_provider_config(runtime_config: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not isinstance(runtime_config, Mapping):
        return None
    api_provider = runtime_config.get("api_provider")
    return api_provider if isinstance(api_provider, Mapping) else None


def check_codex_python_sdk_connectivity(
    *,
    timeout_seconds: float = 600.0,
    model_name: str = "",
) -> str:
    """Run a lightweight Codex SDK turn to validate auth and network connectivity."""
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise CodexPythonSdkSvgError("timeout_seconds must be positive")
    sdk = _load_openai_codex_sdk()
    normalized_model = _normalize_codex_model_name(model_name)
    reasoning_effort = CODEX_DOCTOR_REASONING_EFFORT
    with tempfile.TemporaryDirectory(
        prefix="drawai-codex-doctor-",
        ignore_cleanup_errors=True,
    ) as temporary_dir:
        run_cwd = Path(temporary_dir).resolve(strict=True)
        with _isolated_codex_home(run_cwd) as prepared_codex_home:
            with sdk.Codex(
                sdk.CodexConfig(
                    cwd=str(run_cwd),
                    config_overrides=controlled_codex_config_overrides(),
                    env=_codex_sdk_env(prepared_codex_home.codex_home),
                )
            ) as codex:
                thread = codex.thread_start(
                    approval_mode=sdk.ApprovalMode.deny_all,
                    config={"model_reasoning_effort": reasoning_effort},
                    cwd=str(run_cwd),
                    developer_instructions="You are a DrawAI connectivity probe. Reply with exactly OK.",
                    ephemeral=True,
                    model=normalized_model,
                    sandbox=sdk.Sandbox.full_access,
                )
                result = _run_thread_with_timeout(
                    thread,
                    [sdk.TextInput("Reply exactly: OK")],
                    timeout_seconds=timeout,
                    approval_mode=sdk.ApprovalMode.deny_all,
                    cwd=str(run_cwd),
                    effort=reasoning_effort,
                    model=normalized_model,
                    sandbox=sdk.Sandbox.full_access,
                )
    final_response = str(getattr(result, "final_response", "") or "").strip()
    if not final_response:
        raise CodexPythonSdkSvgError("Codex SDK connectivity check returned an empty final_response")
    return f"Codex SDK responded with {len(final_response)} chars"


def _codex_session_log_archive_dir(
    run_cwd: Path, *, output_svg: Path | None, output_response: Path | None
) -> Path:
    if output_response is not None:
        return output_response.parent / "codex_session_log"
    if output_svg is not None:
        return output_svg.parent / "codex_session_log"
    return run_cwd / "codex_session_log"


def _archive_codex_session_logs(
    codex_home: Path,
    archive_dir: Path,
    *,
    task_name: str,
    sdk_turn_result: Any | None = None,
) -> dict[str, Any]:
    archive_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    for name in CODEX_SESSION_LOG_DIRS:
        source = codex_home / name
        destination = archive_dir / name
        if not source.exists():
            missing.append(name)
            continue
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, destination)
        copied.append(name)

    for name in CODEX_SESSION_LOG_FILES:
        source = codex_home / name
        if source.exists() and source.is_file():
            shutil.copy2(source, archive_dir / name)
            copied.append(name)
        else:
            missing.append(name)

    runtime_tail = _write_codex_runtime_log_tail(
        codex_home / "logs_2.sqlite",
        archive_dir / CODEX_RUNTIME_EVENT_TAIL_FILE,
    )
    if runtime_tail.get("status") == "ok" or (archive_dir / CODEX_RUNTIME_EVENT_TAIL_FILE).is_file():
        copied.append(CODEX_RUNTIME_EVENT_TAIL_FILE)
        if runtime_tail.get("status") != "ok":
            runtime_tail = {
                **runtime_tail,
                "preserved_live_path": str(archive_dir / CODEX_RUNTIME_EVENT_TAIL_FILE),
            }

    sdk_turn_result_report = None
    if sdk_turn_result is not None:
        sdk_turn_result_report = _write_codex_sdk_turn_result_archive(
            sdk_turn_result,
            archive_dir,
            task_name=task_name,
        )

    manifest = {
        "schema": CODEX_SESSION_LOG_ARCHIVE_SCHEMA,
        "task_name": task_name,
        "codex_home": str(codex_home),
        "archive_dir": str(archive_dir),
        "copied": copied,
        "missing": missing,
        "runtime_event_tail": runtime_tail,
        "skipped_runtime_state": [
            name for name in CODEX_SESSION_RUNTIME_STATE_FILES if (codex_home / name).exists()
        ],
        "sdk_turn_result": sdk_turn_result_report,
        "auth_json_copied": (archive_dir / "auth.json").exists(),
    }
    (archive_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _write_codex_runtime_log_tail(source: Path, destination: Path, *, limit: int = 200) -> dict[str, Any]:
    if not source.is_file():
        return {"status": "missing", "source": str(source), "path": str(destination), "event_count": 0}
    try:
        connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=0.2)
        try:
            rows = _read_codex_runtime_rows(connection, limit=int(limit))
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        return {
            "status": "error",
            "source": str(source),
            "path": str(destination),
            "event_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = list(reversed(rows))
    with destination.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_codex_runtime_log_row(row), ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "status": "ok",
        "source": str(source),
        "path": str(destination),
        "event_count": len(rows),
    }


def _read_codex_runtime_rows(connection: sqlite3.Connection, *, limit: int) -> list[tuple[Any, ...]]:
    rows = connection.execute(
        """
        select id, ts, ts_nanos, level, target, feedback_log_body
        from logs
        where feedback_log_body like '%websocket event:%'
        order by id desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    if rows:
        return rows
    return connection.execute(
        """
        select id, ts, ts_nanos, level, target, feedback_log_body
        from logs
        where feedback_log_body is not null
        order by id desc
        limit ?
        """,
        (limit,),
    ).fetchall()


def _codex_runtime_log_row(row: tuple[Any, ...]) -> dict[str, Any]:
    raw_message = str(row[5] or "")
    payload = _extract_codex_websocket_event(raw_message)
    event = _summarize_codex_runtime_payload(payload)
    return {
        "id": row[0],
        "ts": row[1],
        "ts_nanos": row[2],
        "level": str(row[3] or ""),
        "target": str(row[4] or ""),
        "event_type": str(payload.get("type") or "") if isinstance(payload, Mapping) else "",
        "event_kind": _extract_codex_otel_event_kind(raw_message),
        "message": _codex_runtime_event_message(event, raw_message),
        "event": event,
    }


def _extract_codex_websocket_event(message: str) -> Mapping[str, Any] | None:
    marker = "websocket event: "
    index = message.find(marker)
    if index < 0:
        return None
    payload_text = message[index + len(marker) :].strip()
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, Mapping):
        return payload
    return None


def _summarize_codex_runtime_payload(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    event_type = str(payload.get("type") or "")
    summary: dict[str, Any] = {"type": event_type}
    for key in ("sequence_number", "output_index", "item_id", "call_id"):
        value = payload.get(key)
        if isinstance(value, str | int | float | bool):
            summary[key] = value
    for key in ("text", "delta"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            summary[key] = _redact_codex_runtime_message(value)[:2000]

    item = payload.get("item")
    if isinstance(item, Mapping):
        item_summary: dict[str, Any] = {}
        for key in ("id", "type", "name", "status", "role"):
            value = item.get(key)
            if isinstance(value, str | int | float | bool):
                item_summary[key] = value
        if isinstance(item.get("arguments"), str):
            item_summary["arguments"] = _redact_codex_runtime_message(str(item["arguments"]))[:2000]
        if isinstance(item.get("summary"), Sequence) and not isinstance(item.get("summary"), str | bytes | bytearray):
            item_summary["summary_count"] = len(item["summary"])  # type: ignore[arg-type]
        if isinstance(item.get("content"), Sequence) and not isinstance(item.get("content"), str | bytes | bytearray):
            item_summary["content_count"] = len(item["content"])  # type: ignore[arg-type]
        if "encrypted_content" in item:
            item_summary["encrypted_content"] = "[redacted]"
        summary["item"] = item_summary

    response = payload.get("response")
    if isinstance(response, Mapping):
        response_summary: dict[str, Any] = {}
        for key in ("id", "status", "created_at", "completed_at", "background"):
            value = response.get(key)
            if isinstance(value, str | int | float | bool) or value is None:
                response_summary[key] = value
        error = response.get("error")
        if isinstance(error, Mapping):
            response_summary["error"] = {
                str(key): _redact_codex_runtime_message(str(value))[:1000]
                for key, value in error.items()
                if isinstance(value, str | int | float | bool)
            }
        elif isinstance(error, str) and error:
            response_summary["error"] = _redact_codex_runtime_message(error)[:1000]
        summary["response"] = response_summary
    return summary


def _codex_runtime_event_message(event: Mapping[str, Any] | None, raw_message: str) -> str:
    if isinstance(event, Mapping):
        for key in ("text", "delta"):
            value = event.get(key)
            if isinstance(value, str) and value:
                return value[:900]
        item = event.get("item")
        if isinstance(item, Mapping):
            item_type = str(item.get("type") or "")
            item_name = str(item.get("name") or "")
            if item_type or item_name:
                return " ".join(part for part in (item_type, item_name) if part)[:900]
        response = event.get("response")
        if isinstance(response, Mapping):
            status = str(response.get("status") or "")
            if status:
                return f"response {status}"[:900]
        event_type = str(event.get("type") or "")
        if event_type:
            return event_type[:900]
    return _redact_codex_runtime_message(raw_message)[:900]


def _redact_codex_runtime_message(message: str) -> str:
    redacted = re.sub(r'user\.email="[^"]*"', 'user.email="[redacted]"', message)
    redacted = re.sub(r'user\.account_id="[^"]*"', 'user.account_id="[redacted]"', redacted)
    return redacted


def _extract_codex_otel_event_kind(message: str) -> str:
    match = re.search(r"event\.kind=([^\s]+)", message)
    if not match:
        return ""
    return match.group(1).strip('"')


def _write_codex_sdk_turn_result_archive(
    result: Any,
    archive_dir: Path,
    *,
    task_name: str,
) -> dict[str, Any]:
    items = list(getattr(result, "items", []) or [])
    turn_id = getattr(result, "id", None)
    summary_path = archive_dir / "turn_result_summary.json"
    events_path = archive_dir / "codex_session_events.jsonl"

    summary = {
        "schema": CODEX_SDK_TURN_RESULT_SCHEMA,
        "task_name": task_name,
        "turn_id": turn_id,
        "status": _codex_sdk_jsonable(getattr(result, "status", None)),
        "started_at": getattr(result, "started_at", None),
        "completed_at": getattr(result, "completed_at", None),
        "duration_ms": getattr(result, "duration_ms", None),
        "final_response": getattr(result, "final_response", None),
        "item_count": len(items),
        "usage": _codex_sdk_jsonable(getattr(result, "usage", None)),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with events_path.open("w", encoding="utf-8") as handle:
        for index, item in enumerate(items, start=1):
            event = {
                "schema": CODEX_SDK_SESSION_EVENT_SCHEMA,
                "task_name": task_name,
                "turn_id": turn_id,
                "index": index,
                "item": _codex_sdk_jsonable(item),
            }
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    return {
        "schema": CODEX_SDK_TURN_RESULT_SCHEMA,
        "summary_file": summary_path.name,
        "events_file": events_path.name,
        "event_count": len(items),
    }


def _codex_sdk_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str | int | float | bool):
        return enum_value
    if hasattr(value, "model_dump"):
        for kwargs in (
            {"by_alias": True, "exclude_none": True, "mode": "json"},
            {"exclude_none": True, "mode": "json"},
            {},
        ):
            try:
                return _codex_sdk_jsonable(value.model_dump(**kwargs))
            except TypeError:
                continue
    if isinstance(value, Mapping):
        return {str(key): _codex_sdk_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_codex_sdk_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            str(key): _codex_sdk_jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def _normalize_codex_model_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"auto", "default", "codex-default"}:
        return None
    return text


def _normalize_codex_reasoning_effort(value: Any) -> str:
    if value is None:
        return DEFAULT_CODEX_REASONING_EFFORT
    text = str(value).strip().lower()
    if not text or text in {"auto", "default", "codex-default"}:
        return DEFAULT_CODEX_REASONING_EFFORT
    if text not in CODEX_REASONING_EFFORTS:
        supported = ", ".join(sorted(CODEX_REASONING_EFFORTS))
        raise CodexPythonSdkSvgError(
            f"runtime_config.reasoning_effort={text!r} is unsupported. Expected one of: {supported}"
        )
    return text


def _runtime_fast(runtime_config: Mapping[str, Any]) -> bool:
    raw = runtime_config.get("fast")
    if raw in (None, ""):
        return False
    if isinstance(raw, bool):
        return raw
    raise CodexPythonSdkSvgError("runtime_config.fast must be a boolean")


def _load_openai_codex_sdk() -> Any:
    try:
        import openai_codex

        return openai_codex
    except ModuleNotFoundError as exc:
        raise CodexPythonSdkSvgError(
            "openai-codex is required for codex_python_sdk_controlled. "
            "Run `uv sync`, then restart the Workbench/API process; or run this command through: "
            "uv run --with openai-codex --prerelease=allow python ..."
        ) from exc


class CodexPythonSdkSvgSession:
    """Reusable controlled Codex SDK thread for one DrawAI SVG generation run."""

    def __init__(
        self,
        *,
        runtime_config: Mapping[str, Any] | None = None,
        trace_path: str | Path | None = None,
        isolated_cwd: str | Path | None = None,
        config_overrides: Sequence[str] | None = None,
        shared_prompt: str | None = None,
    ) -> None:
        settings = dict(runtime_config or {})
        self.runtime_config = settings
        self.model_name = _normalize_codex_model_name(settings.get("model_name"))
        self.reasoning_effort = _normalize_codex_reasoning_effort(
            settings.get("reasoning_effort", settings.get("model_reasoning_effort"))
        )
        self.service_tier = CODEX_FAST_SERVICE_TIER if _runtime_fast(settings) else None
        self.timeout_seconds = model_runtime._runtime_timeout_seconds(settings)
        self.run_cwd = (
            Path(isolated_cwd)
            if isolated_cwd is not None
            else Path(tempfile.gettempdir()) / "drawai-codex-sdk-svg"
        )
        self.run_cwd = self.run_cwd.expanduser().resolve(strict=False)
        self.trace = Path(trace_path) if trace_path is not None else None
        self.overrides = controlled_codex_config_overrides(config_overrides, runtime_config=settings)
        self.shared_prompt = str(shared_prompt or "").strip()

        self._sdk: Any | None = None
        self._codex_home_context: Any | None = None
        self._prepared_codex_home: PreparedCodexHome | None = None
        self._codex_context: Any | None = None
        self._codex: Any | None = None
        self._thread: Any | None = None
        self._thread_id: str | None = None
        self._turn_index = 0
        self._thread_start_trace_written = False

    def __enter__(self) -> "CodexPythonSdkSvgSession":
        if self._thread is not None:
            return self
        self.run_cwd.mkdir(parents=True, exist_ok=True)
        self._sdk = _load_openai_codex_sdk()
        self._codex_home_context = _isolated_codex_home(self.run_cwd)
        self._prepared_codex_home = self._codex_home_context.__enter__()
        try:
            self._codex_context = self._sdk.Codex(
                self._sdk.CodexConfig(
                    cwd=str(self.run_cwd),
                    config_overrides=self.overrides,
                    env=_codex_sdk_env(self._prepared_codex_home.codex_home, runtime_config=self.runtime_config),
                )
            )
            self._codex = self._codex_context.__enter__()
            self._thread = self._codex.thread_start(
                approval_mode=self._sdk.ApprovalMode.deny_all,
                config={"model_reasoning_effort": self.reasoning_effort},
                cwd=str(self.run_cwd),
                developer_instructions=_controlled_shared_prompt(
                    self.shared_prompt,
                    workspace_dir=self.run_cwd,
                ),
                ephemeral=True,
                model=self.model_name,
                sandbox=self._sdk.Sandbox.full_access,
                service_tier=self.service_tier,
            )
            raw_thread_id = getattr(self._thread, "id", None)
            self._thread_id = str(raw_thread_id) if raw_thread_id else None
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        codex_context = self._codex_context
        codex_home_context = self._codex_home_context
        self._thread = None
        self._codex = None
        self._codex_context = None
        self._prepared_codex_home = None
        self._codex_home_context = None
        try:
            if codex_context is not None:
                codex_context.__exit__(exc_type, exc, tb)
        finally:
            if codex_home_context is not None:
                codex_home_context.__exit__(exc_type, exc, tb)
        return False

    def close(self) -> None:
        self.__exit__(None, None, None)

    def invoke(
        self,
        *,
        image_paths: str | Path | Sequence[str | Path],
        prompt: str,
        task_name: str,
        output_svg_path: str | Path | None = None,
        output_response_path: str | Path | None = None,
    ) -> str:
        if self._thread is None:
            self.__enter__()
        assert self._sdk is not None
        assert self._thread is not None
        assert self._prepared_codex_home is not None

        normalized_image_paths = _normalize_image_paths(image_paths)
        if not normalized_image_paths:
            raise CodexPythonSdkSvgError("at least one image path is required")

        output_svg = (
            _normalize_workspace_output_path(output_svg_path, self.run_cwd)
            if output_svg_path is not None
            else None
        )
        output_response = (
            _normalize_workspace_output_path(output_response_path, self.run_cwd)
            if output_response_path is not None
            else None
        )
        output_schema = None if output_svg is not None else build_codex_svg_output_schema()
        session_log_archive_dir = _codex_session_log_archive_dir(
            self.run_cwd,
            output_svg=output_svg,
            output_response=output_response,
        )
        image_traces = _trace_images(normalized_image_paths)
        codex_input = [
            self._sdk.TextInput(
                _controlled_prompt(
                    prompt,
                    workspace_dir=self.run_cwd,
                    output_svg_path=output_svg,
                    output_response_path=output_response,
                )
            ),
            *(
                self._sdk.LocalImageInput(path=str(image_path))
                for image_path in normalized_image_paths
            ),
        ]
        self._turn_index += 1
        turn_index = self._turn_index
        started_at = time.monotonic()
        model_runtime._append_trace(
            self.trace,
            {
                "type": "codex_python_sdk_request",
                "runner": CODEX_PYTHON_SDK_RUNNER,
                "task_name": task_name,
                "thread_id": self._thread_id,
                "turn_index": turn_index,
                "thread_reused": turn_index > 1,
                "model_name": self.model_name or "codex-default",
                "reasoning_effort": self.reasoning_effort,
                "service_tier": self.service_tier,
                "timeout_seconds": self.timeout_seconds,
                "images": image_traces,
                "isolated_cwd": str(self.run_cwd),
                "codex_home": self._prepared_codex_home.to_trace(),
                "config_overrides": list(self.overrides),
                "sandbox": "danger-full-access",
                "output_svg_path": str(output_svg) if output_svg is not None else None,
                "output_response_path": str(output_response)
                if output_response is not None
                else None,
                "output_schema": output_schema,
                "session_log_archive_path": str(session_log_archive_dir),
            },
        )
        self._append_thread_start_trace_once()
        result: Any | None = None
        try:
            run_kwargs = {
                "approval_mode": self._sdk.ApprovalMode.deny_all,
                "cwd": str(self.run_cwd),
                "effort": self.reasoning_effort,
                "model": self.model_name,
                "sandbox": self._sdk.Sandbox.full_access,
                "service_tier": self.service_tier,
            }
            if output_schema is not None:
                run_kwargs["output_schema"] = output_schema
            result = _run_thread_with_timeout(
                self._thread,
                codex_input,
                timeout_seconds=self.timeout_seconds,
                **run_kwargs,
            )
        except CodexPythonSdkSvgError as exc:
            _append_codex_sdk_error_trace(
                self.trace, task_name=task_name, started_at=started_at, exc=exc
            )
            raise
        except Exception as exc:
            safe_error = _append_codex_sdk_error_trace(
                self.trace, task_name=task_name, started_at=started_at, exc=exc
            )
            raise CodexPythonSdkSvgError(
                f"Codex Python SDK invocation failed: {safe_error}"
            ) from exc
        finally:
            archive_report = _archive_codex_session_logs(
                self._prepared_codex_home.codex_home,
                session_log_archive_dir,
                task_name=task_name,
                sdk_turn_result=result,
            )
            model_runtime._append_trace(
                self.trace,
                {
                    "type": "codex_python_sdk_session_log_archive",
                    "runner": CODEX_PYTHON_SDK_RUNNER,
                    "task_name": task_name,
                    "thread_id": self._thread_id,
                    "turn_index": turn_index,
                    "duration_ms": int((time.monotonic() - started_at) * 1000),
                    "archive": archive_report,
                },
            )

        if output_svg is not None:
            try:
                svg_text = _read_output_svg_file(output_svg)
            except CodexPythonSdkSvgError as exc:
                _append_codex_sdk_error_trace(
                    self.trace, task_name=task_name, started_at=started_at, exc=exc
                )
                raise
            extraction = {"source": "output_svg_path", "path": str(output_svg)}
        else:
            try:
                svg_text, extraction = parse_svg_from_final_response(
                    result.final_response
                )
            except CodexPythonSdkSvgError as exc:
                _append_codex_sdk_error_trace(
                    self.trace, task_name=task_name, started_at=started_at, exc=exc
                )
                raise
        model_runtime._append_trace(
            self.trace,
            {
                "type": "codex_python_sdk_response",
                "runner": CODEX_PYTHON_SDK_RUNNER,
                "task_name": task_name,
                "thread_id": self._thread_id,
                "turn_index": turn_index,
                "extraction": extraction,
                "source": extraction.get("source"),
                "duration_ms": getattr(result, "duration_ms", None),
                "output_chars": len(svg_text),
                "output_excerpt": svg_text[:2000],
                "final_response_excerpt": str(getattr(result, "final_response", ""))[
                    :2000
                ],
            },
        )
        return svg_text

    def _append_thread_start_trace_once(self) -> None:
        if self._thread_start_trace_written or self._prepared_codex_home is None:
            return
        model_runtime._append_trace(
            self.trace,
            {
                "type": "codex_python_sdk_thread_start",
                "runner": CODEX_PYTHON_SDK_RUNNER,
                "thread_id": self._thread_id,
                "model_name": self.model_name or "codex-default",
                "reasoning_effort": self.reasoning_effort,
                "service_tier": self.service_tier,
                "isolated_cwd": str(self.run_cwd),
                "codex_home": self._prepared_codex_home.to_trace(),
                "config_overrides": list(self.overrides),
                "sandbox": "danger-full-access",
                "shared_prompt_chars": len(self.shared_prompt),
            },
        )
        self._thread_start_trace_written = True


def invoke_codex_python_sdk_svg_text(
    *,
    image_paths: str | Path | Sequence[str | Path],
    prompt: str,
    task_name: str,
    runtime_config: Mapping[str, Any] | None = None,
    trace_path: str | Path | None = None,
    isolated_cwd: str | Path | None = None,
    output_svg_path: str | Path | None = None,
    output_response_path: str | Path | None = None,
    config_overrides: Sequence[str] | None = None,
) -> str:
    with CodexPythonSdkSvgSession(
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=isolated_cwd,
        config_overrides=config_overrides,
    ) as session:
        return session.invoke(
            image_paths=image_paths,
            prompt=prompt,
            task_name=task_name,
            output_svg_path=output_svg_path,
            output_response_path=output_response_path,
        )


class _CodexPythonSdkTimeout(TimeoutError):
    pass


def _run_thread_with_timeout(
    thread: Any, run_input: Any, *, timeout_seconds: float, **kwargs: Any
) -> Any:
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise CodexPythonSdkSvgError("runtime_config.timeout_seconds must be positive")
    if threading.current_thread() is not threading.main_thread() or not hasattr(
        signal, "setitimer"
    ):
        return _run_thread_with_worker_timeout(
            thread, run_input, timeout_seconds=timeout, **kwargs
        )

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def _handle_timeout(_signum: int, _frame: Any) -> None:
        raise _CodexPythonSdkTimeout

    try:
        signal.signal(signal.SIGALRM, _handle_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout)
        return thread.run(run_input, **kwargs)
    except _CodexPythonSdkTimeout as exc:
        raise CodexPythonSdkSvgError(
            f"Codex Python SDK run exceeded timeout_seconds={timeout:g}"
        ) from exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])


def _run_thread_with_worker_timeout(
    thread: Any, run_input: Any, *, timeout_seconds: float, **kwargs: Any
) -> Any:
    done = threading.Event()
    state: dict[str, Any] = {}

    def _target() -> None:
        try:
            state["result"] = thread.run(run_input, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - propagate SDK worker failure.
            state["error"] = exc
        finally:
            done.set()

    worker = threading.Thread(
        target=_target,
        name="drawai-codex-sdk-timeout",
        daemon=True,
    )
    worker.start()
    if not done.wait(timeout_seconds):
        _close_timed_out_thread_client(thread)
        raise CodexPythonSdkSvgError(
            f"Codex Python SDK run exceeded timeout_seconds={timeout_seconds:g}"
        )
    if "error" in state:
        raise state["error"]
    return state.get("result")


def _close_timed_out_thread_client(thread: Any) -> None:
    client = getattr(thread, "_client", None)
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _controlled_shared_prompt(prompt: str, *, workspace_dir: Path) -> str:
    return (
        "Internal DrawAI reusable SVG generation thread.\n"
        f"Workspace root: {workspace_dir}\n"
        "The shared context below applies to every subsequent turn in this thread. "
        "You may use shell commands to inspect files, invoke local system executables, and write outputs inside this workspace. "
        "Do not use MCP tools, apps, web search, memories, skills, hooks, or multi-agent delegation. "
        "Write DrawAI outputs only inside the workspace root unless this prompt explicitly names another output path.\n\n"
        f"{prompt}"
    )


def _controlled_prompt(
    prompt: str,
    *,
    workspace_dir: Path,
    output_svg_path: Path | None = None,
    output_response_path: Path | None = None,
) -> str:
    if output_svg_path is None:
        return (
            "Internal DrawAI SVG generation task.\n"
            "Use only the attached prompt and attached images. Do not use skills, MCP tools, apps, "
            "web search, memories, or unrelated local files.\n"
            "Return only JSON matching the provided output schema. The svg field must contain only one complete "
            "SVG document string, starting with <svg and ending with </svg>.\n\n"
            f"{prompt}"
        )
    response_line = (
        f"- If useful, write brief notes to: {output_response_path}\n"
        if output_response_path is not None
        else ""
    )
    return (
        "Internal DrawAI SVG generation task.\n"
        f"Workspace root: {workspace_dir}\n"
        "You may use shell commands to inspect files, invoke local system executables, and write outputs inside this workspace. "
        "Do not use MCP tools, apps, web search, memories, skills, hooks, or multi-agent delegation. "
        "Write DrawAI outputs only inside the workspace root unless this prompt explicitly names another output path.\n\n"
        "Write the SVG file yourself. Output contract:\n"
        f"- Required SVG output path: {output_svg_path}\n"
        f"{response_line}"
        "- The SVG output file must contain exactly one complete SVG document, starting with <svg and ending with </svg>.\n"
        "- Keep the final chat response short; the SVG file is the source of truth.\n\n"
        f"{prompt}"
    )


def _normalize_workspace_output_path(
    path_value: str | Path, workspace_dir: Path
) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = workspace_dir / path
    resolved = path.resolve(strict=False)
    if not _is_relative_to(resolved, workspace_dir):
        raise CodexPythonSdkSvgError(
            f"output path must be inside Codex workspace root: {resolved}"
        )
    return resolved


def _read_output_svg_file(path: Path) -> str:
    if not path.exists():
        raise CodexPythonSdkSvgError(
            f"Codex did not write required SVG output file: {path}"
        )
    if not path.is_file():
        raise CodexPythonSdkSvgError(f"Codex SVG output path is not a file: {path}")
    svg_text = path.read_text(encoding="utf-8").strip()
    if not svg_text.startswith("<svg") or not svg_text.endswith("</svg>"):
        raise CodexPythonSdkSvgError(
            f"Codex SVG output file is not a complete SVG document: {path}"
        )
    return svg_text


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _json_object_from_text(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CodexPythonSdkSvgError(
            "Codex Python SDK final_response was not valid JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise CodexPythonSdkSvgError(
            "Codex Python SDK final_response JSON must be an object"
        )
    return parsed


def _normalize_image_paths(
    image_paths: str | Path | Sequence[str | Path],
) -> list[Path]:
    if isinstance(image_paths, (str, Path)):
        raw_paths: Sequence[str | Path] = [image_paths]
    else:
        raw_paths = image_paths
    normalized: list[Path] = []
    for raw_path in raw_paths:
        image_path = Path(raw_path).expanduser().resolve()
        if not image_path.exists():
            raise CodexPythonSdkSvgError(f"image path does not exist: {image_path}")
        normalized.append(image_path)
    return normalized


def _trace_images(image_paths: Sequence[Path]) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for image_path in image_paths:
        image_bytes = image_path.read_bytes()
        traces.append(
            {
                "image_path": str(image_path),
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "image_bytes": len(image_bytes),
            }
        )
    return traces
