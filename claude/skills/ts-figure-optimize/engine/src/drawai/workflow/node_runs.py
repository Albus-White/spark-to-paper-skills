from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schema import NODE_RUN_SCHEMA, NodeRunStatus

INPUT_MANIFEST_SCHEMA = "drawai.workflow_input_manifest.v1"


@dataclass(frozen=True)
class NodeRunRecord:
    node_id: str
    node_type: str
    attempt_id: str
    root: Path
    workdir: Path
    provider_id: str = ""
    resource_id: str = ""
    started_at: str = ""
    started_monotonic: float = 0.0


def node_run_dir(root: str | Path, node_id: str, attempt_id: str) -> Path:
    root_path = Path(root).expanduser().resolve()
    safe_node_id = _safe_segment(node_id, field_name="node_id")
    safe_attempt_id = _safe_attempt_id(attempt_id)
    workdir = root_path / "nodes" / safe_node_id / "runs" / safe_attempt_id
    resolved = workdir.resolve()
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"node run path is outside run root: {node_id}") from exc
    return resolved


def begin_node_run(
    root: str | Path,
    node_id: str,
    *,
    node_type: str,
    provider_id: str = "",
    resource_id: str = "",
) -> NodeRunRecord:
    root_path = Path(root).expanduser().resolve()
    safe_node_id = _safe_segment(node_id, field_name="node_id")
    attempt_id = _next_attempt_id(root_path, safe_node_id)
    workdir = node_run_dir(root_path, safe_node_id, attempt_id)
    (workdir / "output").mkdir(parents=True, exist_ok=False)
    started_at = _utc_now()
    record = NodeRunRecord(
        node_id=safe_node_id,
        node_type=node_type,
        attempt_id=attempt_id,
        root=root_path,
        workdir=workdir,
        provider_id=provider_id,
        resource_id=resource_id,
        started_at=started_at,
        started_monotonic=time.monotonic(),
    )
    _write_node_run_payload(
        record,
        status="running",
        started_at=started_at,
    )
    return record


def write_input_manifest(
    workdir: str | Path,
    *,
    inputs: Sequence[Mapping[str, Any]],
) -> Path:
    workdir_path = Path(workdir).expanduser().resolve()
    manifest_path = workdir_path / "input_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": INPUT_MANIFEST_SCHEMA,
                "inputs": [_jsonable(dict(item)) for item in inputs],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def finish_node_run_ok(
    record: NodeRunRecord,
    *,
    inputs: Sequence[Mapping[str, Any]] = (),
    outputs: Sequence[Mapping[str, Any]] = (),
    prompt_path: str = "",
    stdout_path: str = "",
    stderr_path: str = "",
    trace_path: str = "",
    session_log_path: str = "",
    execution_manifest_path: str = "",
    exit_code: int = 0,
) -> None:
    _write_node_run_payload(
        record,
        status="ok",
        inputs=inputs,
        outputs=outputs,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        trace_path=trace_path,
        session_log_path=session_log_path,
        execution_manifest_path=execution_manifest_path,
        exit_code=exit_code,
        ended_at=_utc_now(),
        duration_ms=_duration_ms(record),
    )


def finish_node_run_failed(
    record: NodeRunRecord,
    *,
    error: str,
    inputs: Sequence[Mapping[str, Any]] = (),
    exit_code: int | None = None,
    prompt_path: str = "",
    stdout_path: str = "",
    stderr_path: str = "",
    trace_path: str = "",
    session_log_path: str = "",
    execution_manifest_path: str = "",
) -> None:
    _write_node_run_payload(
        record,
        status="failed",
        inputs=inputs,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        trace_path=trace_path,
        session_log_path=session_log_path,
        execution_manifest_path=execution_manifest_path,
        exit_code=exit_code,
        error=error,
        ended_at=_utc_now(),
        duration_ms=_duration_ms(record),
    )


def finish_node_run_blocked(
    record: NodeRunRecord,
    *,
    error: str,
    inputs: Sequence[Mapping[str, Any]] = (),
) -> None:
    _write_node_run_payload(
        record,
        status="blocked",
        inputs=inputs,
        error=error,
        ended_at=_utc_now(),
        duration_ms=_duration_ms(record),
    )


def mark_node_run_stale(workdir: str | Path, *, stale_reason: str) -> None:
    payload = _read_node_run_payload(workdir)
    payload["status"] = "stale"
    payload["stale_reason"] = stale_reason
    _write_json(Path(workdir) / "node_run.json", payload)


def _write_node_run_payload(
    record: NodeRunRecord,
    *,
    status: NodeRunStatus,
    inputs: Sequence[Mapping[str, Any]] = (),
    outputs: Sequence[Mapping[str, Any]] = (),
    prompt_path: str = "",
    stdout_path: str = "",
    stderr_path: str = "",
    trace_path: str = "",
    session_log_path: str = "",
    execution_manifest_path: str = "",
    started_at: str | None = None,
    ended_at: str = "",
    duration_ms: int = 0,
    exit_code: int | None = None,
    error: str | None = None,
    stale_reason: str = "",
) -> None:
    payload = {
        "schema": NODE_RUN_SCHEMA,
        "node_id": record.node_id,
        "node_type": record.node_type,
        "attempt_id": record.attempt_id,
        "status": status,
        "workdir": _run_relative(record.root, record.workdir),
        "provider_id": record.provider_id,
        "resource_id": record.resource_id,
        "inputs": [_jsonable(dict(item)) for item in inputs],
        "outputs": [_jsonable(dict(item)) for item in outputs],
        "prompt_path": prompt_path,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "trace_path": trace_path,
        "session_log_path": session_log_path,
        "execution_manifest_path": execution_manifest_path,
        "started_at": started_at if started_at is not None else record.started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "error": error,
        "stale_reason": stale_reason,
    }
    _write_json(record.workdir / "node_run.json", payload)


def _read_node_run_payload(workdir: str | Path) -> dict[str, Any]:
    manifest_path = Path(workdir).expanduser().resolve() / "node_run.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"node_run.json must contain an object: {manifest_path}")
    return payload


def _next_attempt_id(root: Path, node_id: str) -> str:
    runs_dir = root / "nodes" / node_id / "runs"
    if not runs_dir.exists():
        return "001"
    attempts: list[int] = []
    for path in runs_dir.iterdir():
        if path.is_dir() and path.name.isdigit():
            attempts.append(int(path.name))
    return f"{(max(attempts) if attempts else 0) + 1:03d}"


def _safe_attempt_id(attempt_id: str) -> str:
    safe_attempt_id = _safe_segment(attempt_id, field_name="attempt_id")
    if not safe_attempt_id.isdigit():
        raise ValueError(f"attempt_id must be numeric: {attempt_id}")
    return safe_attempt_id


def _safe_segment(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")
    path = Path(value)
    if (
        path.is_absolute()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{field_name} must be a safe single path segment: {value}")
    return value


def _run_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _duration_ms(record: NodeRunRecord) -> int:
    return max(0, round((time.monotonic() - record.started_monotonic) * 1000))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value
