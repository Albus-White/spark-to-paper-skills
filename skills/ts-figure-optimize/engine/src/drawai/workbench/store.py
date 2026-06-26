from __future__ import annotations

import json
import shutil
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import (
    ArtifactRecord,
    BatchRecord,
    BatchStatus,
    CaseRecord,
    CaseStatus,
    InputMode,
    StageRunRecord,
    StageStatus,
    new_id,
    utc_now,
)


class WorkbenchStore:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.runs_root = self.workspace / "runs"
        self.uploads_root = self.workspace / "uploads"
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.workspace / "drawai_workbench.db"
        self._init_schema()

    def create_batch(
        self,
        *,
        name: str,
        input_mode: InputMode,
        max_concurrent_cases: int,
        auto_run_svg_after_analysis: bool,
        config_path: str | Path,
    ) -> BatchRecord:
        now = utc_now()
        record = BatchRecord(
            batch_id=new_id("batch"),
            name=name,
            input_mode=input_mode,
            status="queued",
            max_concurrent_cases=max_concurrent_cases,
            auto_run_svg_after_analysis=auto_run_svg_after_analysis,
            created_at=now,
            updated_at=now,
            config_path=str(Path(config_path).expanduser().resolve(strict=False)),
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO batches (
                  batch_id, name, input_mode, status, max_concurrent_cases,
                  auto_run_svg_after_analysis, created_at, updated_at, config_path,
                  error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.batch_id,
                    record.name,
                    record.input_mode,
                    record.status,
                    record.max_concurrent_cases,
                    int(record.auto_run_svg_after_analysis),
                    record.created_at,
                    record.updated_at,
                    record.config_path,
                    record.error_message,
                ),
            )
        return record

    def get_batch(self, batch_id: str) -> BatchRecord:
        row = self._one("SELECT * FROM batches WHERE batch_id = ?", (batch_id,))
        if row is None:
            raise KeyError(f"unknown batch_id: {batch_id}")
        return _batch_from_row(row)

    def list_batches(self) -> list[BatchRecord]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM batches ORDER BY created_at DESC").fetchall()
        return [_batch_from_row(row) for row in rows]

    def rename_batch(self, batch_id: str, name: str) -> BatchRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("batch name cannot be empty")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE batches SET name = ?, updated_at = ? WHERE batch_id = ?",
                (clean_name, utc_now(), batch_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"unknown batch_id: {batch_id}")
        return self.get_batch(batch_id)

    def delete_batch(self, batch_id: str) -> None:
        batch = self.get_batch(batch_id)
        with self._connect() as db:
            cursor = db.execute("DELETE FROM batches WHERE batch_id = ?", (batch_id,))
            if cursor.rowcount == 0:
                raise KeyError(f"unknown batch_id: {batch_id}")
        shutil.rmtree(self.runs_root / batch.batch_id, ignore_errors=True)
        shutil.rmtree(self.uploads_root / batch.batch_id, ignore_errors=True)

    def update_batch_status(self, batch_id: str, status: BatchStatus, *, error_message: str = "") -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE batches SET status = ?, error_message = ?, updated_at = ? WHERE batch_id = ?",
                (status, error_message, utc_now(), batch_id),
            )

    def create_case(
        self,
        *,
        batch_id: str,
        name: str,
        source_image_path: str | Path,
        config_path: str | Path,
    ) -> CaseRecord:
        batch = self.get_batch(batch_id)
        now = utc_now()
        case_id = new_id("case")
        run_root = self.runs_root / batch.batch_id / case_id
        run_root.mkdir(parents=True, exist_ok=True)
        record = CaseRecord(
            case_id=case_id,
            batch_id=batch_id,
            name=name,
            status="queued",
            phase="queued",
            stage="queued",
            source_image_path=str(Path(source_image_path).expanduser().resolve(strict=False)),
            run_root=str(run_root),
            config_path=str(Path(config_path).expanduser().resolve(strict=False)),
            created_at=now,
            updated_at=now,
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO cases (
                  case_id, batch_id, name, status, phase, stage, source_image_path,
                  run_root, config_path, created_at, updated_at, error_message,
                  stale_from_stage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.case_id,
                    record.batch_id,
                    record.name,
                    record.status,
                    record.phase,
                    record.stage,
                    record.source_image_path,
                    record.run_root,
                    record.config_path,
                    record.created_at,
                    record.updated_at,
                    record.error_message,
                    record.stale_from_stage,
                ),
            )
        return record

    def get_case(self, case_id: str) -> CaseRecord:
        row = self._one("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        if row is None:
            raise KeyError(f"unknown case_id: {case_id}")
        return _case_from_row(row)

    def list_cases(self, batch_id: str | None = None) -> list[CaseRecord]:
        with self._connect() as db:
            if batch_id is None:
                rows = db.execute("SELECT * FROM cases ORDER BY created_at ASC").fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM cases WHERE batch_id = ? ORDER BY created_at ASC",
                    (batch_id,),
                ).fetchall()
        return [_case_from_row(row) for row in rows]

    def update_case_status(
        self,
        case_id: str,
        *,
        status: CaseStatus,
        phase: str,
        stage: str,
        error_message: str = "",
        stale_from_stage: str = "",
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE cases
                SET status = ?, phase = ?, stage = ?, error_message = ?,
                    stale_from_stage = ?, updated_at = ?
                WHERE case_id = ?
                """,
                (status, phase, stage, error_message, stale_from_stage, utc_now(), case_id),
            )

    def update_case_config_path(self, case_id: str, config_path: str | Path) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE cases SET config_path = ?, updated_at = ? WHERE case_id = ?",
                (str(Path(config_path).expanduser().resolve(strict=False)), utc_now(), case_id),
            )

    def case_counts(self, batch_id: str) -> dict[str, int]:
        cases = self.list_cases(batch_id)
        return dict(Counter(case.status for case in cases))

    def start_stage_run(self, case_id: str, stage_name: str, *, log_path: str = "") -> StageRunRecord:
        attempt = self._next_stage_attempt(case_id, stage_name)
        record = StageRunRecord(
            stage_run_id=new_id("stage"),
            case_id=case_id,
            stage_name=stage_name,
            status="running",
            attempt=attempt,
            started_at=utc_now(),
            log_path=log_path,
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO stage_runs (
                  stage_run_id, case_id, stage_name, status, attempt, started_at,
                  ended_at, log_path, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.stage_run_id,
                    record.case_id,
                    record.stage_name,
                    record.status,
                    record.attempt,
                    record.started_at,
                    record.ended_at,
                    record.log_path,
                    record.error_message,
                ),
            )
        return record

    def finish_stage_run(
        self,
        stage_run_id: str,
        *,
        status: StageStatus,
        error_message: str = "",
    ) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE stage_runs SET status = ?, ended_at = ?, error_message = ? WHERE stage_run_id = ?",
                (status, utc_now(), error_message, stage_run_id),
            )

    def list_stage_runs(self, case_id: str) -> list[StageRunRecord]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM stage_runs WHERE case_id = ? ORDER BY started_at ASC, attempt ASC",
                (case_id,),
            ).fetchall()
        return [_stage_from_row(row) for row in rows]

    def register_artifact(
        self,
        case_id: str,
        *,
        label: str,
        path: str | Path,
        media_type: str = "application/octet-stream",
    ) -> ArtifactRecord:
        case = self.get_case(case_id)
        artifact_path = _resolve_inside(Path(case.run_root), path)
        token = new_id("artifact")
        record = ArtifactRecord(
            artifact_token=token,
            case_id=case_id,
            label=label,
            path=str(artifact_path),
            media_type=media_type,
            created_at=utc_now(),
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO artifacts (
                  artifact_token, case_id, label, path, media_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.artifact_token,
                    record.case_id,
                    record.label,
                    record.path,
                    record.media_type,
                    record.created_at,
                ),
            )
        return record

    def resolve_artifact(self, artifact_token: str) -> ArtifactRecord:
        row = self._one("SELECT * FROM artifacts WHERE artifact_token = ?", (artifact_token,))
        if row is None:
            raise KeyError(f"unknown artifact token: {artifact_token}")
        record = _artifact_from_row(row)
        case = self.get_case(record.case_id)
        _resolve_inside(Path(case.run_root), record.path)
        return record

    def list_artifacts(self, case_id: str) -> list[ArtifactRecord]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM artifacts WHERE case_id = ? ORDER BY created_at ASC",
                (case_id,),
            ).fetchall()
        return [_artifact_from_row(row) for row in rows]

    def write_case_json(self, case_id: str, relative_path: str | Path, payload: Any) -> Path:
        case = self.get_case(case_id)
        path = _resolve_inside(Path(case.run_root), relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def read_case_json(self, case_id: str, relative_path: str | Path) -> Any:
        case = self.get_case(case_id)
        path = _resolve_inside(Path(case.run_root), relative_path)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def _one(self, query: str, params: Iterable[Any]) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute(query, tuple(params)).fetchone()

    def _next_stage_attempt(self, case_id: str, stage_name: str) -> int:
        row = self._one(
            "SELECT COALESCE(MAX(attempt), 0) + 1 AS attempt FROM stage_runs WHERE case_id = ? AND stage_name = ?",
            (case_id, stage_name),
        )
        return int(row["attempt"]) if row is not None else 1

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS batches (
                  batch_id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  input_mode TEXT NOT NULL,
                  status TEXT NOT NULL,
                  max_concurrent_cases INTEGER NOT NULL,
                  auto_run_svg_after_analysis INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  config_path TEXT NOT NULL,
                  error_message TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS cases (
                  case_id TEXT PRIMARY KEY,
                  batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  status TEXT NOT NULL,
                  phase TEXT NOT NULL,
                  stage TEXT NOT NULL,
                  source_image_path TEXT NOT NULL,
                  run_root TEXT NOT NULL,
                  config_path TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  error_message TEXT NOT NULL DEFAULT '',
                  stale_from_stage TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS stage_runs (
                  stage_run_id TEXT PRIMARY KEY,
                  case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
                  stage_name TEXT NOT NULL,
                  status TEXT NOT NULL,
                  attempt INTEGER NOT NULL,
                  started_at TEXT NOT NULL,
                  ended_at TEXT NOT NULL DEFAULT '',
                  log_path TEXT NOT NULL DEFAULT '',
                  error_message TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                  artifact_token TEXT PRIMARY KEY,
                  case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
                  label TEXT NOT NULL,
                  path TEXT NOT NULL,
                  media_type TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                """
            )


def _resolve_inside(root: Path, path: str | Path) -> Path:
    root_resolved = root.expanduser().resolve()
    candidate = Path(path).expanduser()
    resolved = candidate.resolve(strict=False) if candidate.is_absolute() else (root_resolved / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path is outside case root: {path}") from exc
    return resolved


def _batch_from_row(row: Mapping[str, Any]) -> BatchRecord:
    return BatchRecord(
        batch_id=str(row["batch_id"]),
        name=str(row["name"]),
        input_mode=str(row["input_mode"]),  # type: ignore[arg-type]
        status=str(row["status"]),  # type: ignore[arg-type]
        max_concurrent_cases=int(row["max_concurrent_cases"]),
        auto_run_svg_after_analysis=bool(row["auto_run_svg_after_analysis"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        config_path=str(row["config_path"]),
        error_message=str(row["error_message"]),
    )


def _case_from_row(row: Mapping[str, Any]) -> CaseRecord:
    return CaseRecord(
        case_id=str(row["case_id"]),
        batch_id=str(row["batch_id"]),
        name=str(row["name"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        phase=str(row["phase"]),
        stage=str(row["stage"]),
        source_image_path=str(row["source_image_path"]),
        run_root=str(row["run_root"]),
        config_path=str(row["config_path"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        error_message=str(row["error_message"]),
        stale_from_stage=str(row["stale_from_stage"]),
    )


def _stage_from_row(row: Mapping[str, Any]) -> StageRunRecord:
    return StageRunRecord(
        stage_run_id=str(row["stage_run_id"]),
        case_id=str(row["case_id"]),
        stage_name=str(row["stage_name"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        attempt=int(row["attempt"]),
        started_at=str(row["started_at"]),
        ended_at=str(row["ended_at"]),
        log_path=str(row["log_path"]),
        error_message=str(row["error_message"]),
    )


def _artifact_from_row(row: Mapping[str, Any]) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_token=str(row["artifact_token"]),
        case_id=str(row["case_id"]),
        label=str(row["label"]),
        path=str(row["path"]),
        media_type=str(row["media_type"]),
        created_at=str(row["created_at"]),
    )
