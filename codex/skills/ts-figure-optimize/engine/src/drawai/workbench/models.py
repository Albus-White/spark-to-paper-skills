from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from drawai.workflow.templates import DEFAULT_WORKFLOW_TEMPLATE_ID

BatchStatus = Literal["queued", "running", "waiting_review", "completed", "failed", "canceled"]
BatchExecutionMode = Literal["default", "agent", "llm"]
CaseStatus = Literal[
    "queued",
    "analysis_running",
    "assets_review",
    "svg_running",
    "completed",
    "failed",
    "canceled",
]
StageStatus = Literal["queued", "running", "ok", "failed", "canceled", "stale"]
InputMode = Literal["upload", "zip", "local_dir"]
SourceStrategy = Literal["svg_self_draw", "crop", "crop_nobg"]

SOURCE_STRATEGIES: tuple[SourceStrategy, ...] = ("svg_self_draw", "crop", "crop_nobg")


@dataclass(frozen=True)
class WorkbenchSettings:
    workspace: Path
    default_config: Path
    cloud_mode: bool = False
    max_concurrent_cases: int = 10
    sam_concurrency: int = 1
    ocr_concurrency: int = 1
    codex_concurrency: int = 5
    rmbg_concurrency: int = 1
    export_concurrency: int = 1
    sam3_base_url: str = "http://127.0.0.1:18080"
    ocr_base_url: str = "http://127.0.0.1:18080"
    rmbg_base_url: str = "http://127.0.0.1:18080"
    ocr_timeout_seconds: float | None = None


@dataclass(frozen=True)
class BatchRecord:
    batch_id: str
    name: str
    input_mode: InputMode
    status: BatchStatus
    max_concurrent_cases: int
    auto_run_svg_after_analysis: bool
    created_at: str
    updated_at: str
    config_path: str
    workflow_template_id: str = DEFAULT_WORKFLOW_TEMPLATE_ID
    execution_mode: BatchExecutionMode = "default"
    error_message: str = ""

    def to_api(self, *, case_counts: Mapping[str, int] | None = None) -> dict[str, Any]:
        payload = asdict(self)
        payload["case_counts"] = dict(case_counts or {})
        return payload


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    batch_id: str
    name: str
    status: CaseStatus
    phase: str
    stage: str
    source_image_path: str
    run_root: str
    config_path: str
    created_at: str
    updated_at: str
    error_message: str = ""
    stale_from_stage: str = ""

    def to_api(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StageRunRecord:
    stage_run_id: str
    case_id: str
    stage_name: str
    status: StageStatus
    attempt: int
    started_at: str
    ended_at: str = ""
    log_path: str = ""
    error_message: str = ""

    def to_api(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_token: str
    case_id: str
    label: str
    path: str
    media_type: str
    created_at: str

    def to_api(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("path", None)
        payload["url"] = f"/api/artifacts/{self.artifact_token}"
        return payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12).replace('-', '').replace('_', '')[:16]}"
