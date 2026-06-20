from __future__ import annotations

import json
import os
import shutil
import threading
from collections.abc import Callable
from contextlib import contextmanager
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

import yaml

from drawai.config import load_drawai_config
from drawai.pipeline import run_drawai_pipeline_from_stage
from drawai.public_stages import run_public_stage
from drawai.rmbg_client import RemoteRmbgClient

from .assets import (
    approve_asset_plan,
    draft_from_run0_analysis,
    materialize_approved_assets,
    read_asset_draft,
    write_asset_draft,
)
from .models import CaseRecord, WorkbenchSettings
from .store import WorkbenchStore

StageExecutor = Callable[[CaseRecord, str], None]
RerunStage = Literal["analysis", "asset_analyze", "materialize", "svg", "export"]

ANALYSIS_STAGES = (
    "prepare",
    "detect_structure",
    "detect_text",
    "assemble_boxir",
    "asset_plan",
    "asset_analyze",
)

STAGE_RESOURCE = {
    "detect_structure": "sam3",
    "detect_text": "ocr",
    "asset_analyze": "codex",
    "svg": "codex",
    "export": "export",
}


class WorkbenchRunner:
    def __init__(
        self,
        store: WorkbenchStore,
        settings: WorkbenchSettings,
        *,
        stage_executor: StageExecutor | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.stage_executor = stage_executor
        self.executor = ThreadPoolExecutor(max_workers=max(1, settings.max_concurrent_cases))
        self._futures: set[Future[Any]] = set()
        self._futures_lock = threading.Lock()
        self._case_jobs: set[str] = set()
        self._case_jobs_lock = threading.Lock()
        self._resource_activity_lock = threading.Lock()
        self._resource_activity = {
            "sam3": {"limit": max(1, settings.sam_concurrency), "queued": 0, "running": 0},
            "ocr": {"limit": max(1, settings.ocr_concurrency), "queued": 0, "running": 0},
            "codex": {"limit": max(1, settings.codex_concurrency), "queued": 0, "running": 0},
            "rmbg": {"limit": max(1, settings.rmbg_concurrency), "queued": 0, "running": 0},
            "export": {"limit": max(1, settings.export_concurrency), "queued": 0, "running": 0},
        }
        self._resource_locks = {
            "sam3": threading.Semaphore(max(1, settings.sam_concurrency)),
            "ocr": threading.Semaphore(max(1, settings.ocr_concurrency)),
            "codex": threading.Semaphore(max(1, settings.codex_concurrency)),
            "rmbg": threading.Semaphore(max(1, settings.rmbg_concurrency)),
            "export": threading.Semaphore(max(1, settings.export_concurrency)),
        }
        self._mark_interrupted_running_cases()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def wait_for_idle(self, timeout: float | None = None) -> None:
        with self._futures_lock:
            futures = list(self._futures)
        for future in futures:
            future.result(timeout=timeout)

    def resource_activity(self) -> dict[str, dict[str, int]]:
        with self._resource_activity_lock:
            return {key: dict(value) for key, value in self._resource_activity.items()}

    def submit_batch(self, batch_id: str) -> None:
        batch = self.store.get_batch(batch_id)
        cases = self.store.list_cases(batch_id)
        if not cases:
            self.store.update_batch_status(batch_id, "failed", error_message="Batch has no cases.")
            return
        self.store.update_batch_status(batch_id, "running")
        batch_limit = threading.Semaphore(max(1, batch.max_concurrent_cases))
        for case in cases:
            self._submit_case(self._run_case_with_limit, case.case_id, batch_limit)

    def submit_rerun(self, case_id: str, stage: RerunStage) -> None:
        self._submit_case(self._rerun_case, case_id, stage)

    def approve_case(self, case_id: str, *, run_svg: bool) -> dict[str, Any]:
        if run_svg and self._case_has_active_job(case_id):
            raise RuntimeError(f"case already has an active background job: {case_id}")
        case = self.store.get_case(case_id)
        plan = approve_asset_plan(case.run_root, read_asset_draft(case.run_root))
        self._register_standard_artifacts(case_id)
        self.store.update_case_status(
            case_id,
            status="assets_review",
            phase="analysis",
            stage="approved_asset_plan",
            stale_from_stage="svg",
        )
        if run_svg:
            self.store.update_case_status(
                case_id,
                status="svg_running",
                phase="reconstruction",
                stage="materialize",
                stale_from_stage="svg",
            )
            self._submit_case(self._materialize_and_run_svg, case_id)
        self._refresh_batch_status(case.batch_id)
        return plan

    def _submit(self, fn: Callable[..., Any], *args: Any) -> None:
        future = self.executor.submit(fn, *args)
        with self._futures_lock:
            self._futures.add(future)
        future.add_done_callback(self._discard_future)

    def _submit_case(self, fn: Callable[..., Any], case_id: str, *args: Any) -> None:
        with self._case_jobs_lock:
            if case_id in self._case_jobs:
                raise RuntimeError(f"case already has an active background job: {case_id}")
            self._case_jobs.add(case_id)
        future = self.executor.submit(fn, case_id, *args)
        with self._futures_lock:
            self._futures.add(future)
        future.add_done_callback(lambda completed: self._discard_case_future(completed, case_id))

    def _case_has_active_job(self, case_id: str) -> bool:
        with self._case_jobs_lock:
            return case_id in self._case_jobs

    @contextmanager
    def _resource_slot(self, resource: str) -> Iterator[None]:
        lock = self._resource_locks[resource]
        self._change_resource_activity(resource, queued=1)
        lock.acquire()
        self._change_resource_activity(resource, queued=-1, running=1)
        try:
            yield
        finally:
            self._change_resource_activity(resource, running=-1)
            lock.release()

    def _change_resource_activity(self, resource: str, *, queued: int = 0, running: int = 0) -> None:
        with self._resource_activity_lock:
            activity = self._resource_activity[resource]
            activity["queued"] = max(0, activity["queued"] + queued)
            activity["running"] = max(0, activity["running"] + running)

    def _discard_future(self, future: Future[Any]) -> None:
        with self._futures_lock:
            self._futures.discard(future)

    def _discard_case_future(self, future: Future[Any], case_id: str) -> None:
        with self._case_jobs_lock:
            self._case_jobs.discard(case_id)
        self._discard_future(future)

    def _mark_interrupted_running_cases(self) -> None:
        interrupted_batches: set[str] = set()
        for case in self.store.list_cases():
            message = "Workbench restarted while this case was running; previous job was interrupted."
            case_was_running = case.status in {"analysis_running", "svg_running"}
            if case_was_running:
                self.store.update_case_status(
                    case.case_id,
                    status="failed",
                    phase=case.phase,
                    stage=case.stage,
                    error_message=message,
                )
            for stage_run in self.store.list_stage_runs(case.case_id):
                if stage_run.status == "running":
                    self.store.finish_stage_run(
                        stage_run.stage_run_id,
                        status="failed",
                        error_message=message,
                    )
                    interrupted_batches.add(case.batch_id)
            if case_was_running:
                interrupted_batches.add(case.batch_id)
        for batch_id in interrupted_batches:
            self._refresh_batch_status(batch_id)

    def _run_case_with_limit(self, case_id: str, batch_limit: threading.Semaphore) -> None:
        with batch_limit:
            self._run_analysis(case_id)

    def _refresh_case_runtime_config(self, case: CaseRecord) -> CaseRecord:
        batch = self.store.get_batch(case.batch_id)
        config_path = create_case_config(
            base_config_path=batch.config_path,
            source_image=case.source_image_path,
            output_dir=case.run_root,
            target_path=case.config_path,
            sam3_base_url=self.settings.sam3_base_url,
            ocr_base_url=self.settings.ocr_base_url,
            ocr_timeout_seconds=self.settings.ocr_timeout_seconds,
            rmbg_base_url=self.settings.rmbg_base_url,
        )
        self.store.update_case_config_path(case.case_id, config_path)
        return self.store.get_case(case.case_id)

    def _run_analysis(self, case_id: str) -> None:
        case = self._refresh_case_runtime_config(self.store.get_case(case_id))
        self.store.update_case_status(case_id, status="analysis_running", phase="analysis", stage="prepare")
        try:
            for stage in ANALYSIS_STAGES:
                self._run_stage(case_id, stage)
            draft = draft_from_run0_analysis(case.run_root, case_id=case_id)
            write_asset_draft(case.run_root, draft)
            self._register_standard_artifacts(case_id)
            batch = self.store.get_batch(case.batch_id)
            if batch.auto_run_svg_after_analysis:
                approve_asset_plan(case.run_root, draft)
                self._register_standard_artifacts(case_id)
                self.store.update_case_status(
                    case_id,
                    status="assets_review",
                    phase="analysis",
                    stage="approved_asset_plan",
                    stale_from_stage="svg",
                )
                self.store.update_case_status(
                    case_id,
                    status="svg_running",
                    phase="reconstruction",
                    stage="materialize",
                    stale_from_stage="svg",
                )
                self._materialize_approved_assets(case)
                self._register_standard_artifacts(case_id)
                self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="svg")
                self._run_svg_generation(case_id)
            else:
                self.store.update_case_status(case_id, status="assets_review", phase="analysis", stage="asset_analyze")
            self._refresh_batch_status(case.batch_id)
        except Exception as exc:  # noqa: BLE001 - background job boundary records failures.
            self.store.update_case_status(
                case_id,
                status="failed",
                phase="analysis",
                stage=self.store.get_case(case_id).stage,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            self._refresh_batch_status(case.batch_id)

    def _rerun_case(self, case_id: str, stage: RerunStage) -> None:
        case = self._refresh_case_runtime_config(self.store.get_case(case_id))
        try:
            if stage in {"analysis", "asset_analyze"}:
                self._invalidate_from(case_id, "asset_analyze")
                self._run_analysis(case_id)
            elif stage == "materialize":
                self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="materialize")
                self._materialize_approved_assets(case)
                self._register_standard_artifacts(case_id)
                self.store.update_case_status(case_id, status="assets_review", phase="reconstruction", stage="approved_asset_plan")
            elif stage == "svg":
                self._archive_current_svg_outputs(case_id)
                self._invalidate_from(case_id, "svg")
                self._run_svg_generation(case_id)
            elif stage == "export":
                self._invalidate_from(case_id, "export")
                self._run_export(case_id)
            self._refresh_batch_status(case.batch_id)
        except Exception as exc:  # noqa: BLE001 - background job boundary records failures.
            current = self.store.get_case(case_id)
            self.store.update_case_status(
                case_id,
                status="failed",
                phase=current.phase,
                stage=current.stage,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            self._refresh_batch_status(case.batch_id)

    def _materialize_and_run_svg(self, case_id: str) -> None:
        case = self._refresh_case_runtime_config(self.store.get_case(case_id))
        try:
            self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="materialize")
            self._materialize_approved_assets(case)
            self._register_standard_artifacts(case_id)
            self._run_svg_generation(case_id)
            self._refresh_batch_status(case.batch_id)
        except Exception as exc:  # noqa: BLE001 - background job boundary records failures.
            current = self.store.get_case(case_id)
            self.store.update_case_status(
                case_id,
                status="failed",
                phase=current.phase,
                stage=current.stage,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            self._refresh_batch_status(case.batch_id)

    def _run_svg_generation(self, case_id: str) -> None:
        self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="svg")
        self._run_stage(case_id, "svg")
        self._register_standard_artifacts(case_id)
        self._run_export(case_id)
        case = self.store.get_case(case_id)
        self._refresh_batch_status(case.batch_id)

    def _run_export(self, case_id: str) -> None:
        self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="export")
        self._run_stage(case_id, "export")
        self._register_standard_artifacts(case_id)
        self.store.update_case_status(case_id, status="completed", phase="reconstruction", stage="completed")

    def _run_stage(self, case_id: str, stage: str) -> None:
        case = self.store.get_case(case_id)
        self.store.update_case_status(
            case_id,
            status="svg_running" if stage in {"svg", "export"} else "analysis_running",
            phase="reconstruction" if stage in {"svg", "export"} else "analysis",
            stage=stage,
        )
        stage_run = self.store.start_stage_run(case_id, stage)
        resource = STAGE_RESOURCE.get(stage)
        try:
            if resource is None:
                self._execute_stage(case, stage)
            else:
                with self._resource_slot(resource):
                    self._execute_stage(case, stage)
            self.store.finish_stage_run(stage_run.stage_run_id, status="ok")
        except Exception as exc:
            self.store.finish_stage_run(stage_run.stage_run_id, status="failed", error_message=f"{type(exc).__name__}: {exc}")
            raise

    def _execute_stage(self, case: CaseRecord, stage: str) -> None:
        if self.stage_executor is not None:
            self.stage_executor(case, stage)
            return
        if stage in ANALYSIS_STAGES:
            summary = run_public_stage(case.config_path, stage)
        elif stage == "svg":
            summary = run_drawai_pipeline_from_stage(case.config_path, "svg_generated", to_stage="svg_generated")
        elif stage == "export":
            summary = run_drawai_pipeline_from_stage(case.config_path, "svg_to_ppt_exported", to_stage="svg_to_ppt_exported")
        else:
            raise ValueError(f"unsupported stage: {stage}")
        if summary.get("status") != "ok":
            message = _pipeline_failure_message(summary)
            failed_stage = summary.get("failed_stage") or stage
            raise RuntimeError(f"DrawAI stage {failed_stage} failed: {message or summary.get('status')}")

    def _materialize_approved_assets(self, case: CaseRecord) -> dict[str, Any]:
        cfg = load_drawai_config(case.config_path, validate_input_exists=False)
        rmbg_config = cfg.asset_materialization.rmbg
        rmbg_client = None
        if rmbg_config.enabled:
            rmbg_client = RemoteRmbgClient((rmbg_config.base_url or self.settings.rmbg_base_url).rstrip("/"))
            with self._resource_slot("rmbg"):
                return materialize_approved_assets(case.run_root, rmbg_config=rmbg_config, rmbg_client=rmbg_client)
        return materialize_approved_assets(case.run_root, rmbg_config=rmbg_config, rmbg_client=rmbg_client)

    def _register_standard_artifacts(self, case_id: str) -> None:
        case = self.store.get_case(case_id)
        root = Path(case.run_root)
        artifacts = (
            ("figure", "inputs/figure.png", "image/png"),
            ("asset_draft", "reports/workbench/asset_draft.json", "application/json"),
            ("approved_asset_plan", "reports/workbench/approved_asset_plan.json", "application/json"),
            ("element_analysis", "reports/element_analysis_codex/element_analysis.json", "application/json"),
            ("asset_manifest", "svg_to_ppt/assets/asset_manifest.json", "application/json"),
            ("semantic_svg", "svg/semantic.svg", "image/svg+xml"),
            ("rendered_png", "svg/rendered.png", "image/png"),
            ("svg_validation_report", "reports/svg_validation_report.json", "application/json"),
            ("pptx_export_report", "reports/svg_to_ppt_export_report.json", "application/json"),
            ("pptx", "svg_to_ppt/semantic.svg_to_ppt.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        )
        for label, relative_path, media_type in artifacts:
            path = root / relative_path
            if path.exists():
                self.store.register_artifact(case_id, label=label, path=path, media_type=media_type)

    def _invalidate_from(self, case_id: str, stage: str) -> None:
        current = self.store.get_case(case_id)
        status = "assets_review" if stage in {"asset_analyze", "svg"} else current.status
        self.store.update_case_status(
            case_id,
            status=status,
            phase=current.phase,
            stage=current.stage,
            stale_from_stage=stage,
        )

    def _archive_current_svg_outputs(self, case_id: str) -> Path | None:
        case = self.store.get_case(case_id)
        root = Path(case.run_root)
        sources = [
            root / "svg",
            root / "reports" / "svg_validation_report.json",
            root / "reports" / "svg_to_ppt_export_report.json",
            root / "svg_to_ppt" / "semantic.svg_to_ppt.pptx",
            root / "svg_to_ppt" / "svg_to_ppt_report.json",
        ]
        existing_sources = [path for path in sources if path.exists()]
        if not existing_sources:
            return None
        archive_dir = _next_svg_archive_dir(root)
        copied: list[str] = []
        for source in existing_sources:
            target = archive_dir / source.relative_to(root)
            if source.is_dir():
                copied.extend(_copy_svg_archive_dir(source, target, archive_dir))
            else:
                _make_archive_dir(target.parent)
                shutil.copy2(_archive_fs_path(source), _archive_fs_path(target))
                copied.append(str(target.relative_to(archive_dir)))
        manifest_path = archive_dir / "archive_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": "drawai.workbench.svg_rerun_archive.v1",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "before_svg_rerun",
                    "files": copied,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.store.register_artifact(case_id, label="svg_rerun_archive", path=manifest_path, media_type="application/json")
        return archive_dir

    def _refresh_batch_status(self, batch_id: str) -> None:
        cases = self.store.list_cases(batch_id)
        statuses = {case.status for case in cases}
        if any(status in statuses for status in {"queued", "analysis_running", "svg_running"}):
            self.store.update_batch_status(batch_id, "running")
        elif statuses == {"completed"}:
            self.store.update_batch_status(batch_id, "completed")
        elif "assets_review" in statuses:
            self.store.update_batch_status(batch_id, "waiting_review")
        elif "failed" in statuses:
            failed_case = next((case for case in cases if case.status == "failed" and case.error_message), None)
            self.store.update_batch_status(batch_id, "failed", error_message=failed_case.error_message if failed_case else "")
        elif "canceled" in statuses:
            self.store.update_batch_status(batch_id, "canceled")


def _next_svg_archive_dir(root: Path) -> Path:
    archive_root = root / "archives" / "svg_runs"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for index in range(1000):
        suffix = "" if index == 0 else f"_{index:03d}"
        candidate = archive_root / f"{timestamp}_before_svg_rerun{suffix}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
    raise RuntimeError(f"could not allocate SVG archive directory under {archive_root}")


def _copy_svg_archive_dir(source: Path, target: Path, archive_dir: Path) -> list[str]:
    copied: list[str] = []
    for current_root, dir_names, file_names in os.walk(source):
        dir_names[:] = [name for name in dir_names if not _is_svg_archive_transient_name(name)]
        current_path = Path(current_root)
        relative_dir = current_path.relative_to(source)
        target_dir = target / relative_dir
        _make_archive_dir(target_dir)
        for file_name in file_names:
            if _is_svg_archive_transient_name(file_name):
                continue
            source_file = current_path / file_name
            target_file = target_dir / file_name
            _make_archive_dir(target_file.parent)
            shutil.copy2(_archive_fs_path(source_file), _archive_fs_path(target_file))
            copied.append(str(target_file.relative_to(archive_dir)))
    return sorted(copied)


def _is_svg_archive_transient_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in {
        ".playwright",
        "chrome-profile",
        "chrome-profile-test",
        "playwright-report",
        "test-results",
    } or lowered.startswith("chrome-profile-")


def _make_archive_dir(path: Path) -> None:
    os.makedirs(_archive_fs_path(path), exist_ok=True)


def _archive_fs_path(path: Path) -> str:
    resolved = str(path.resolve(strict=False))
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


def _pipeline_failure_message(summary: dict[str, Any]) -> str:
    exception = summary.get("exception")
    if isinstance(exception, dict):
        message = exception.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    error = summary.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return ""


def create_case_config(
    *,
    base_config_path: str | Path,
    source_image: str | Path,
    output_dir: str | Path,
    target_path: str | Path,
    sam3_base_url: str = "",
    ocr_base_url: str = "",
    ocr_timeout_seconds: float | None = None,
    rmbg_base_url: str = "",
) -> Path:
    base_path = Path(base_config_path).expanduser().resolve()
    with base_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"DrawAI config must be a mapping: {base_path}")
    input_config = payload.get("input")
    if not isinstance(input_config, dict):
        input_config = {}
    input_config["image"] = str(Path(source_image).expanduser().resolve(strict=False))
    input_config["output_dir"] = str(Path(output_dir).expanduser().resolve(strict=False))
    payload["input"] = input_config
    if sam3_base_url:
        sam3_config = payload.get("sam3")
        if not isinstance(sam3_config, dict):
            sam3_config = {}
        sam3_config["base_url"] = sam3_base_url.rstrip("/")
        payload["sam3"] = sam3_config
    if ocr_base_url or ocr_timeout_seconds is not None:
        ocr_config = payload.get("ocr")
        if not isinstance(ocr_config, dict):
            ocr_config = {}
        remote_config = ocr_config.get("remote_paddleocr")
        if not isinstance(remote_config, dict):
            remote_config = {}
        if ocr_base_url:
            remote_config["base_url"] = ocr_base_url.rstrip("/")
        if ocr_timeout_seconds is not None:
            timeout_seconds = float(ocr_timeout_seconds)
            if timeout_seconds <= 0:
                raise ValueError("ocr_timeout_seconds must be positive")
            remote_config["timeout_seconds"] = timeout_seconds
        ocr_config["remote_paddleocr"] = remote_config
        payload["ocr"] = ocr_config
    if rmbg_base_url:
        materialization_config = payload.get("asset_materialization")
        if not isinstance(materialization_config, dict):
            materialization_config = {}
        rmbg_config = materialization_config.get("rmbg")
        if not isinstance(rmbg_config, dict):
            rmbg_config = {}
        rmbg_config["base_url"] = rmbg_base_url.rstrip("/")
        materialization_config["rmbg"] = rmbg_config
        payload["asset_materialization"] = materialization_config
    target = Path(target_path).expanduser().resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    load_drawai_config(target, validate_input_exists=False)
    return target


def copy_source_image(source: str | Path, target_dir: str | Path) -> Path:
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"source image does not exist: {source_path}")
    target_root = Path(target_dir).expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / source_path.name
    shutil.copy2(source_path, target)
    return target
