from __future__ import annotations

import json
import os
import shutil
import threading
import time
from collections.abc import Callable
from collections.abc import Mapping
from contextlib import ExitStack, contextmanager
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

import yaml

from drawai.artifacts import DrawAiArtifactPaths, prepare_artifact_paths, write_json
from drawai.asset_manifest_utils import extend_asset_manifest_for_svg_export
from drawai.config import load_drawai_config
from drawai.ocr_provider import clamp_ocr_boxes_to_canvas
from drawai.page_spec import (
    fuse_page_specs,
    load_page_spec,
    page_spec_from_candidates,
    write_page_spec,
)
from drawai.page_spec_assets import copy_page_spec_bundle, materialize_page_spec_assets, page_spec_asset_manifest
from drawai.page_spec_svg import draft_semantic_svg_from_page_spec
from drawai.pipeline import run_drawai_pipeline_from_stage
from drawai.rmbg_client import RemoteRmbgClient
from drawai.sam3_client import run_sam3_prompt_plan
from drawai.svg_to_ppt_check import check_svg_to_ppt_compatibility
from drawai.tool_agent_runtime import DRAWAI_TOOL_AGENT_PROVIDER
from drawai.tooling import resolve_drawai_tool_command_prefix
from drawai.v2.parsers import ocr_payload_to_candidates, sam3_payload_to_candidates
from drawai.v2.packages import write_element_plan
from drawai.v2.schema import RUN_PACKAGE_SCHEMA, AssetPackage, ElementPlan, utc_now
from drawai.workflow.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
    execute_agent_prompt,
)
from drawai.workflow.agents import agent_preset_by_id, default_agent_provider_registry, render_agent_prompt
from drawai.workflow.formats import element_plans_from_payload
from drawai.workflow.llm_execution import (
    LLMExecutionRequest,
    LLMExecutionResult,
    execute_llm_prompt,
    render_llm_prompt,
)
from drawai.workflow.runner import NodeRunContext, WorkflowRunner
from drawai.workflow.schema import WorkflowEdge, WorkflowTemplate
from drawai.workflow.templates import load_workflow_template_by_id

from .assets import (
    approve_asset_plan,
    draft_from_element_plans,
    draft_from_run0_analysis,
    materialize_approved_assets,
    read_asset_draft,
    write_asset_draft,
)
from .agent_settings import (
    WorkbenchAgentSettings,
    apply_workbench_agent_settings_to_config_payload,
    apply_workbench_agent_settings_to_node_config,
    apply_workbench_llm_settings_to_node_config,
    normalize_workbench_agent_settings,
    workbench_agent_runtime_options,
)
from .case_settings_snapshot import CaseSettingsSnapshot, read_case_settings_snapshot_or_workspace
from .image_processor_providers import asset_prepare_image_providers_from_settings
from .processor_settings import resolved_processor_operation_config_from_settings
from .models import CaseRecord, WorkbenchSettings
from .store import WorkbenchStore

StageExecutor = Callable[[CaseRecord, str], None]
AgentExecutor = Callable[[AgentExecutionRequest], AgentExecutionResult]
LLMExecutor = Callable[[LLMExecutionRequest], LLMExecutionResult]
RerunStage = Literal[
    "analysis",
    "asset_analyze",
    "materialize",
    "svg",
    "export",
    "prepare",
    "parse_elements",
    "fuse_elements",
    "refine_elements",
    "plan_assets",
    "process_assets",
    "compose",
    "compose_svg",
    "package_run",
]

ANALYSIS_STAGES = (
    "prepare",
    "parse_elements",
    "fuse_elements",
    "refine_elements",
    "plan_assets",
)

STAGE_RESOURCES = {
    "parse_elements": ("sam3", "ocr"),
    "refine_elements": ("codex",),
    "process_assets": ("rmbg",),
    "compose_svg": ("codex",),
    "export": ("export",),
}

WORKFLOW_DELIVERABLE_ARTIFACTS = {
    "drawai.semantic_svg.v1": ("semantic_svg", "image/svg+xml"),
    "semantic_svg": ("semantic_svg", "image/svg+xml"),
    "drawai.pptx.v1": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
}

RERUN_STAGE_ALIASES = {
    "prepare": "analysis",
    "asset_analyze": "analysis",
    "materialize": "process_assets",
    "svg": "compose_svg",
    "compose": "compose_svg",
    "package_run": "export",
}

WORKBENCH_DEFAULT_AGENT_PROVIDER_ID = "default"
_WORKBENCH_AGENT_SETTINGS_APPLIED = "_workbench_agent_settings_applied"


class WorkbenchCaseCanceled(RuntimeError):
    pass


def _uses_workbench_default_agent_settings(node_config: Mapping[str, Any]) -> bool:
    provider_id = str(node_config.get("provider_id") or "").strip()
    return provider_id in {"", WORKBENCH_DEFAULT_AGENT_PROVIDER_ID}


def _agent_provider_concurrency_limit(
    provider_id: str,
    settings: WorkbenchSettings,
) -> int:
    if provider_id in {"codex_sdk", "codex_cli"}:
        return max(1, settings.codex_concurrency)
    provider = default_agent_provider_registry()[provider_id]
    return max(1, provider.default_max_concurrent)


def _canonical_rerun_stage(stage: str) -> str:
    return RERUN_STAGE_ALIASES.get(stage, stage)


class WorkbenchRunner:
    def __init__(
        self,
        store: WorkbenchStore,
        settings: WorkbenchSettings,
        *,
        stage_executor: StageExecutor | None = None,
        agent_executor: AgentExecutor | None = None,
        llm_executor: LLMExecutor | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.stage_executor = stage_executor
        self.agent_executor = agent_executor or execute_agent_prompt
        self.llm_executor = llm_executor or execute_llm_prompt
        self.executor = ThreadPoolExecutor(max_workers=max(1, settings.max_concurrent_cases))
        self._futures: set[Future[Any]] = set()
        self._futures_lock = threading.Lock()
        self._case_jobs: set[str] = set()
        self._case_futures: dict[str, Future[Any]] = {}
        self._case_cancel_events: dict[str, threading.Event] = {}
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
        for provider in default_agent_provider_registry().values():
            limit = _agent_provider_concurrency_limit(provider.provider_id, settings)
            self._resource_activity[provider.resource_key] = {"limit": limit, "queued": 0, "running": 0}
            self._resource_locks[provider.resource_key] = threading.Semaphore(limit)
        self._mark_interrupted_running_cases()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def wait_for_idle(self, timeout: float | None = None) -> None:
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            with self._futures_lock:
                futures = list(self._futures)
            with self._case_jobs_lock:
                case_jobs = set(self._case_jobs)
            if not futures and not case_jobs:
                self._refresh_running_batches()
                return
            if not futures:
                remaining = _idle_wait_remaining(deadline)
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("Workbench runner did not become idle before timeout.")
                time.sleep(min(0.01, remaining) if remaining is not None else 0.01)
                continue
            for future in futures:
                remaining = _idle_wait_remaining(deadline)
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("Workbench runner did not become idle before timeout.")
                future.result(timeout=remaining)

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

    def submit_workflow_rerun(self, case_id: str, node_id: str) -> None:
        clean_node_id = str(node_id or "").strip()
        if not clean_node_id:
            raise ValueError("workflow node_id cannot be empty")
        self.store.update_case_status(case_id, status="analysis_running", phase="workflow", stage=clean_node_id)
        self._submit_case(self._run_workflow_case, case_id, clean_node_id)

    def cancel_case(self, case_id: str) -> CaseRecord:
        case = self.store.get_case(case_id)
        self._request_case_cancel(case_id)
        current = self.store.get_case(case_id)
        self.store.update_case_status(
            case_id,
            status="canceled",
            phase=current.phase,
            stage=current.stage,
        )
        self._refresh_batch_status(case.batch_id)
        return self.store.get_case(case_id)

    def set_workflow_breakpoint(self, case_id: str, node_id: str) -> str:
        clean_node_id = node_id.strip()
        if not clean_node_id:
            raise ValueError("workflow breakpoint node_id cannot be empty")
        case = self.store.get_case(case_id)
        batch = self.store.get_batch(case.batch_id)
        template = load_workflow_template_by_id(self.store.workspace, batch.workflow_template_id)
        if clean_node_id not in {node.node_id for node in template.nodes}:
            raise ValueError(f"unknown workflow node_id: {clean_node_id}")
        _write_workflow_breakpoint_node_id(case.run_root, clean_node_id)
        return clean_node_id

    def clear_workflow_breakpoint(self, case_id: str) -> None:
        case = self.store.get_case(case_id)
        _clear_workflow_breakpoint_node_id(case.run_root)

    def continue_workflow_case(self, case_id: str) -> None:
        if self._case_has_active_job(case_id):
            raise RuntimeError(f"case already has an active background job: {case_id}")
        case = self.store.get_case(case_id)
        _clear_workflow_breakpoint_node_id(case.run_root)
        self.store.update_case_status(case_id, status="analysis_running", phase="analysis", stage="prepare")
        self._submit_case(self._run_workflow_case, case_id)

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
            stale_from_stage="compose_svg",
        )
        if run_svg:
            self.store.update_case_status(
                case_id,
                status="svg_running",
                phase="reconstruction",
                stage="process_assets",
                stale_from_stage="compose_svg",
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
            self._case_cancel_events[case_id] = threading.Event()
        future = self.executor.submit(fn, case_id, *args)
        with self._futures_lock:
            self._futures.add(future)
        with self._case_jobs_lock:
            self._case_futures[case_id] = future
        future.add_done_callback(lambda completed: self._discard_case_future(completed, case_id))

    def _case_has_active_job(self, case_id: str) -> bool:
        with self._case_jobs_lock:
            return case_id in self._case_jobs

    def _request_case_cancel(self, case_id: str) -> None:
        with self._case_jobs_lock:
            cancel_event = self._case_cancel_events.get(case_id)
            future = self._case_futures.get(case_id)
        if cancel_event is not None:
            cancel_event.set()
        if future is not None:
            future.cancel()

    def _case_cancel_requested(self, case_id: str) -> bool:
        with self._case_jobs_lock:
            cancel_event = self._case_cancel_events.get(case_id)
        return bool(cancel_event and cancel_event.is_set())

    def _raise_if_case_canceled(self, case_id: str) -> None:
        if self._case_cancel_requested(case_id):
            raise WorkbenchCaseCanceled("case run was canceled")

    def _mark_case_canceled(self, case_id: str) -> None:
        current = self.store.get_case(case_id)
        self.store.update_case_status(
            case_id,
            status="canceled",
            phase=current.phase,
            stage=current.stage,
        )
        self._refresh_batch_status(current.batch_id)

    @contextmanager
    def _resource_slot(self, resource: str) -> Iterator[None]:
        if resource not in self._resource_locks:
            self._resource_locks[resource] = threading.Semaphore(1)
            with self._resource_activity_lock:
                self._resource_activity[resource] = {"limit": 1, "queued": 0, "running": 0}
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
            self._case_futures.pop(case_id, None)
            self._case_cancel_events.pop(case_id, None)
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
        try:
            with batch_limit:
                self._raise_if_case_canceled(case_id)
                self._run_workflow_case(case_id)
        except WorkbenchCaseCanceled:
            self._mark_case_canceled(case_id)

    def _case_settings_snapshot(self, case: CaseRecord) -> CaseSettingsSnapshot:
        return read_case_settings_snapshot_or_workspace(case.run_root, self.store.workspace)

    def _case_owns_config_path(self, case: CaseRecord) -> bool:
        config_path = Path(case.config_path).expanduser().resolve(strict=False)
        run_root = Path(case.run_root).expanduser().resolve(strict=False)
        return config_path.is_relative_to(run_root)

    def _refresh_case_runtime_config(self, case: CaseRecord) -> CaseRecord:
        if self._case_owns_config_path(case) and Path(case.config_path).is_file():
            return case
        batch = self.store.get_batch(case.batch_id)
        settings_snapshot = self._case_settings_snapshot(case)
        config_path = create_case_config(
            base_config_path=batch.config_path,
            source_image=case.source_image_path,
            output_dir=case.run_root,
            target_path=case.config_path,
            sam3_base_url=self.settings.sam3_base_url,
            ocr_base_url=self.settings.ocr_base_url,
            ocr_timeout_seconds=self.settings.ocr_timeout_seconds,
            rmbg_base_url=self.settings.rmbg_base_url,
            agent_settings=settings_snapshot.agent_settings.to_dict(),
            execution_mode=batch.execution_mode,
        )
        self.store.update_case_config_path(case.case_id, config_path)
        return self.store.get_case(case.case_id)

    def _run_workflow_case(self, case_id: str, rerun_from_node_id: str = "") -> None:
        case = self.store.get_case(case_id)
        try:
            self._raise_if_case_canceled(case_id)
            case = self._refresh_case_runtime_config(case)
            batch = self.store.get_batch(case.batch_id)
            settings_snapshot = self._case_settings_snapshot(case)
            agent_settings = settings_snapshot.agent_settings
            template = load_workflow_template_by_id(self.store.workspace, batch.workflow_template_id)
            template = _workflow_template_with_agent_settings(
                template,
                agent_settings,
                execution_mode=batch.execution_mode,
                processor_operation_config=resolved_processor_operation_config_from_settings(
                    settings_snapshot.processor_settings,
                    api_presets=settings_snapshot.api_presets,
                ),
            )
            review_template = _workflow_until_first_human_review(template)
            run_template = template if batch.auto_run_svg_after_analysis or review_template is None else review_template
            parser_ids = _workflow_parser_ids(run_template)
            stage_state: dict[str, bool] = {}
            stage_state_lock = threading.Lock()
            runner = WorkflowRunner(
                run_template,
                handlers={
                    "input": lambda context, inputs: self._run_workflow_input_node(
                        case,
                        context,
                        inputs,
                        stage_state,
                        stage_state_lock,
                    ),
                    "parser": lambda context, inputs: self._run_workflow_parser_node(
                        case,
                        context,
                        inputs,
                        stage_state,
                        stage_state_lock,
                        parser_ids=parser_ids,
                    ),
                    "fusion": lambda context, inputs: self._run_workflow_fusion_node(
                        case,
                        context,
                        inputs,
                        stage_state,
                        stage_state_lock,
                    ),
                    "agent": lambda context, inputs: self._run_workflow_agent_node(
                        case,
                        context,
                        inputs,
                        stage_state,
                        agent_settings=agent_settings,
                    ),
                    "llm": lambda context, inputs: self._run_workflow_llm_node(
                        case,
                        context,
                        inputs,
                    ),
                    "processor": lambda context, inputs: self._run_workflow_processor_node(
                        case,
                        context,
                        inputs,
                        stage_state,
                        stage_state_lock,
                        settings_snapshot=settings_snapshot,
                    ),
                    "human_review": lambda context, inputs: self._run_workflow_review_node(
                        case,
                        context,
                        inputs,
                        auto_approve=batch.auto_run_svg_after_analysis,
                    ),
                    "export": lambda context, inputs: self._run_workflow_export_node(
                        case,
                        context,
                        inputs,
                        stage_state,
                        stage_state_lock,
                    ),
                },
            )
            result = runner.run(
                case.run_root,
                should_pause_after_node=lambda node_id: _workflow_breakpoint_node_id(case.run_root) == node_id,
                rerun_from_node_id=rerun_from_node_id,
            )
            self._raise_if_case_canceled(case_id)
            if not result.ok:
                failed = ", ".join(result.failed_node_ids or result.blocked_node_ids)
                detail = _workflow_failure_detail(result)
                raise RuntimeError(f"Workflow DAG failed: {failed}{': ' + detail if detail else ''}")
            self._register_standard_artifacts(case_id)
            updated = self.store.get_case(case_id)
            if result.paused_node_ids:
                paused_node_id = result.paused_node_ids[0]
                self.store.update_case_status(
                    case_id,
                    status="assets_review",
                    phase=updated.phase or "workflow",
                    stage=paused_node_id,
                    stale_from_stage="",
                )
                self._refresh_batch_status(case.batch_id)
                return
            if batch.auto_run_svg_after_analysis or review_template is None:
                self.store.update_case_status(case_id, status="completed", phase="reconstruction", stage="completed")
            else:
                self.store.update_case_status(
                    case_id,
                    status="assets_review",
                    phase=updated.phase or "analysis",
                    stage=_first_human_review_node_id(template) or "assets_review",
                    stale_from_stage="compose_svg",
                )
            self._refresh_batch_status(case.batch_id)
        except WorkbenchCaseCanceled:
            self._mark_case_canceled(case_id)
        except Exception as exc:  # noqa: BLE001 - background job boundary records failures.
            if self._case_cancel_requested(case_id):
                self._mark_case_canceled(case_id)
                return
            current = self.store.get_case(case_id)
            self.store.update_case_status(
                case_id,
                status="failed",
                phase=current.phase,
                stage=current.stage,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            self._refresh_batch_status(case.batch_id)

    def _run_workflow_input_node(
        self,
        case: CaseRecord,
        context: NodeRunContext,
        _inputs: tuple[Mapping[str, Any], ...],
        stage_state: dict[str, bool],
        stage_state_lock: threading.Lock,
    ) -> tuple[Mapping[str, Any], ...]:
        self._raise_if_case_canceled(case.case_id)
        self._ensure_workflow_stage(
            case,
            "prepare",
            stage_state,
            stage_state_lock=stage_state_lock,
        )
        paths = prepare_artifact_paths(case.run_root)
        source = paths.figure_image if paths.figure_image.exists() else Path(case.source_image_path)
        output_path = _copy_workflow_file(source, context.output_dir / f"image{source.suffix or '.png'}")
        self._raise_if_case_canceled(case.case_id)
        return (_workflow_output(context, "image", output_path, "image", "drawai.image.v1"),)

    def _run_workflow_parser_node(
        self,
        case: CaseRecord,
        context: NodeRunContext,
        _inputs: tuple[Mapping[str, Any], ...],
        stage_state: dict[str, bool],
        stage_state_lock: threading.Lock,
        *,
        parser_ids: frozenset[str],
    ) -> tuple[Mapping[str, Any], ...]:
        self._raise_if_case_canceled(case.case_id)
        with stage_state_lock:
            self._ensure_workflow_stage_unlocked(case, "prepare", stage_state)
            if not stage_state.get("parse_elements"):
                self._run_workflow_parse_elements(case, parser_ids)
                stage_state["parse_elements"] = True
        paths = prepare_artifact_paths(case.run_root)
        parser_id = str(context.node.config.get("parser_id") or "")
        if parser_id == "sam3_structure_parser":
            source = paths.v2_parser_outputs_dir / "sam3_candidates.json"
        elif parser_id == "ocr_text_parser":
            source = paths.v2_parser_outputs_dir / "ocr_candidates.json"
        else:
            raise ValueError(f"unsupported parser node: {parser_id or context.node.node_id}")
        if not source.exists():
            source = paths.v2_parser_outputs_dir / "element_candidates.json"
        output_path = _copy_workflow_json(source, context.output_dir / "candidates.json")
        self._raise_if_case_canceled(case.case_id)
        return (_workflow_output(context, "candidates", output_path, "element_candidates", "drawai.element_candidates.v1"),)

    def _run_workflow_parse_elements(
        self,
        case: CaseRecord,
        parser_ids: frozenset[str],
    ) -> None:
        self._raise_if_case_canceled(case.case_id)
        sam3_enabled = "sam3_structure_parser" in parser_ids
        ocr_enabled = "ocr_text_parser" in parser_ids
        if not sam3_enabled and not ocr_enabled:
            raise ValueError("workflow parse_elements requires at least one parser node")
        self.store.update_case_status(case.case_id, status="analysis_running", phase="analysis", stage="parse_elements")
        stage_run = self.store.start_stage_run(case.case_id, "parse_elements")
        resources = _workflow_parser_resources(parser_ids)
        try:
            with ExitStack() as stack:
                for resource in resources:
                    stack.enter_context(self._resource_slot(resource))
                if self.stage_executor is not None:
                    self.stage_executor(case, "parse_elements")
                else:
                    cfg = load_drawai_config(case.config_path, validate_input_exists=False)
                    parser_config = replace(
                        cfg.v2.parser,
                        sam3_enabled=sam3_enabled,
                        ocr_enabled=ocr_enabled,
                    )
                    workflow_cfg = replace(cfg, v2=replace(cfg.v2, parser=parser_config))
                    summary = run_drawai_pipeline_from_stage(
                        workflow_cfg,
                        "parse_elements",
                        to_stage="parse_elements",
                    )
                    if summary.get("status") != "ok":
                        message = _pipeline_failure_message(summary)
                        failed_stage = summary.get("failed_stage") or "parse_elements"
                        raise RuntimeError(f"DrawAI stage {failed_stage} failed: {message or summary.get('status')}")
            self._raise_if_case_canceled(case.case_id)
            self.store.finish_stage_run(stage_run.stage_run_id, status="ok")
        except WorkbenchCaseCanceled:
            self.store.finish_stage_run(stage_run.stage_run_id, status="canceled", error_message="case run was canceled")
            raise
        except Exception as exc:
            if self._case_cancel_requested(case.case_id):
                self.store.finish_stage_run(stage_run.stage_run_id, status="canceled", error_message="case run was canceled")
                raise WorkbenchCaseCanceled("case run was canceled") from exc
            self.store.finish_stage_run(stage_run.stage_run_id, status="failed", error_message=f"{type(exc).__name__}: {exc}")
            raise

    def _run_workflow_fusion_node(
        self,
        case: CaseRecord,
        context: NodeRunContext,
        _inputs: tuple[Mapping[str, Any], ...],
        stage_state: dict[str, bool],
        stage_state_lock: threading.Lock,
    ) -> tuple[Mapping[str, Any], ...]:
        self._raise_if_case_canceled(case.case_id)
        self._ensure_workflow_stage(
            case,
            "fuse_elements",
            stage_state,
            stage_state_lock=stage_state_lock,
        )
        paths = prepare_artifact_paths(case.run_root)
        output_path = _copy_workflow_json(paths.run_package_json, context.output_dir / "elements.json")
        self._raise_if_case_canceled(case.case_id)
        return (_workflow_output(context, "elements", output_path, "element_plans", "drawai.element_plans.v1"),)

    def _run_workflow_agent_node(
        self,
        case: CaseRecord,
        context: NodeRunContext,
        inputs: tuple[Mapping[str, Any], ...],
        stage_state: dict[str, bool],
        *,
        agent_settings: WorkbenchAgentSettings,
    ) -> tuple[Mapping[str, Any], ...]:
        self._raise_if_case_canceled(case.case_id)
        preset_id = str(context.node.config.get("preset_id") or "custom_agent")
        node_config = {**dict(context.node.config), "node_id": context.node.node_id}
        use_workbench_settings = bool(
            node_config.pop(_WORKBENCH_AGENT_SETTINGS_APPLIED, False)
        ) or _uses_workbench_default_agent_settings(node_config)
        if use_workbench_settings:
            node_config = apply_workbench_agent_settings_to_node_config(node_config, agent_settings)
        tool_command_prefix = resolve_drawai_tool_command_prefix(_repo_root(), cwd=context.run_root)
        prompt = render_agent_prompt(
            agent_preset_by_id(preset_id),
            inputs=inputs,
            node_config=node_config,
            runtime_context={
                "workflow_run_root": context.run_root,
                "node_workdir": context.record.workdir,
                "agent_cwd": context.run_root,
                "repo_root": _repo_root(),
                "attempt_id": context.record.attempt_id,
                "drawai_tool_command_prefix": tool_command_prefix,
            },
        )
        runtime_options = workbench_agent_runtime_options(agent_settings) if use_workbench_settings else {}
        if runtime_options:
            prompt = replace(prompt, options={**dict(prompt.options), **runtime_options})
        runtime_config = (
            _workflow_llm_runtime_config(case, node_config, prompt.provider_id)
            if prompt.provider_id == DRAWAI_TOOL_AGENT_PROVIDER
            else None
        )
        resource = f"agent_provider:{prompt.provider_id}"
        with self._resource_slot(resource):
            result = self.agent_executor(
                AgentExecutionRequest(
                    prompt=prompt,
                    workdir=context.record.workdir,
                    run_root=context.run_root,
                    node_id=context.node.node_id,
                    node_type=context.node.node_type,
                    runtime_config=runtime_config,
                )
            )
        self._raise_if_case_canceled(case.case_id)
        outputs: list[dict[str, Any]] = []
        for declared in prompt.outputs:
            output_path = context.record.workdir / str(declared["path"])
            outputs.append(
                _workflow_output(
                    context,
                    str(declared["port_id"]),
                    output_path,
                    str(declared["type"]),
                    str(declared["format_id"]),
                    deliverable=_node_output_port_is_deliverable(context, str(declared["port_id"])),
                    prompt_path=result.prompt_path,
                    stdout_path=result.stdout_path,
                    stderr_path=result.stderr_path,
                    trace_path=result.trace_path,
                    session_log_path=result.session_log_path,
                    execution_manifest_path=result.execution_manifest_path,
                    exit_code=result.exit_code,
                )
            )
        return tuple(outputs)

    def _run_workflow_llm_node(
        self,
        case: CaseRecord,
        context: NodeRunContext,
        inputs: tuple[Mapping[str, Any], ...],
    ) -> tuple[Mapping[str, Any], ...]:
        self._raise_if_case_canceled(case.case_id)
        preset_id = str(context.node.config.get("preset_id") or "custom_agent")
        node_config = {**dict(context.node.config), "node_id": context.node.node_id}
        prompt = render_llm_prompt(
            agent_preset_by_id(preset_id),
            inputs=inputs,
            node_config=node_config,
            runtime_context={
                "workflow_run_root": context.run_root,
                "node_workdir": context.record.workdir,
                "agent_cwd": context.run_root,
                "repo_root": _repo_root(),
                "attempt_id": context.record.attempt_id,
            },
        )
        runtime_config = _workflow_llm_runtime_config(case, context.node.config, prompt.provider_id)
        resource = f"llm_provider:{prompt.provider_id}"
        with self._resource_slot(resource):
            result = self.llm_executor(
                LLMExecutionRequest(
                    prompt=prompt,
                    workdir=context.record.workdir,
                    run_root=context.run_root,
                    node_id=context.node.node_id,
                    node_type=context.node.node_type,
                    runtime_config=runtime_config,
                )
            )
        self._raise_if_case_canceled(case.case_id)
        outputs: list[dict[str, Any]] = []
        for declared in prompt.outputs:
            output_path = context.record.workdir / str(declared["path"])
            outputs.append(
                _workflow_output(
                    context,
                    str(declared["port_id"]),
                    output_path,
                    str(declared["type"]),
                    str(declared["format_id"]),
                    deliverable=_node_output_port_is_deliverable(context, str(declared["port_id"])),
                    prompt_path=result.prompt_path,
                    stdout_path=result.stdout_path,
                    trace_path=result.trace_path,
                    execution_manifest_path=result.execution_manifest_path,
                    exit_code=result.exit_code,
                )
            )
        return tuple(outputs)

    def _run_workflow_processor_node(
        self,
        case: CaseRecord,
        context: NodeRunContext,
        inputs: tuple[Mapping[str, Any], ...],
        stage_state: dict[str, bool],
        stage_state_lock: threading.Lock,
        *,
        settings_snapshot: CaseSettingsSnapshot | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        self._raise_if_case_canceled(case.case_id)
        processor_id = str(context.node.config.get("processor_id") or "")
        paths = prepare_artifact_paths(case.run_root)
        if processor_id == "sam_parse":
            self._ensure_workflow_stage(
                case,
                "prepare",
                stage_state,
                stage_state_lock=stage_state_lock,
            )
            page_spec = self._run_sam_parse_page_spec(case)
            output_path = write_page_spec(context.output_dir / "sam_page_spec.json", page_spec)
            return (_workflow_output(context, "sam_page_spec", output_path, "page_spec", "drawai.page_spec.v1"),)
        if processor_id == "ocr_parse":
            self._ensure_workflow_stage(
                case,
                "prepare",
                stage_state,
                stage_state_lock=stage_state_lock,
            )
            page_spec = self._run_ocr_parse_page_spec(case)
            output_path = write_page_spec(context.output_dir / "ocr_page_spec.json", page_spec)
            return (_workflow_output(context, "ocr_page_spec", output_path, "page_spec", "drawai.page_spec.v1"),)
        if processor_id == "page_spec_fuse":
            page_specs = [
                load_page_spec(path)
                for path in _input_paths_by_type(
                    case.run_root,
                    inputs,
                    "page_spec",
                    format_id="drawai.page_spec.v1",
                )
            ]
            page_spec = fuse_page_specs(
                page_specs,
                page_id=case.case_id,
                source_image=str(paths.figure_image),
            )
            canonical_path = write_page_spec(Path(case.run_root) / "page_spec.json", page_spec)
            output_path = _copy_workflow_json(canonical_path, context.output_dir / "page_spec.json")
            return (_workflow_output(context, "page_spec", output_path, "page_spec", "drawai.page_spec.v1"),)
        if processor_id == "asset_prepare":
            page_spec_source = _input_path_by_type(
                case.run_root,
                inputs,
                "page_spec",
                format_id="drawai.page_spec.v1",
            )
            page_spec = load_page_spec(page_spec_source)
            source_image = _input_path_by_type(
                case.run_root,
                inputs,
                "image",
                format_id="drawai.image.v1",
            )
            cfg = load_drawai_config(case.config_path, validate_input_exists=False)
            rmbg_config = cfg.asset_materialization.rmbg
            rmbg_client = RemoteRmbgClient(rmbg_config.base_url) if rmbg_config.enabled else None
            case_snapshot = settings_snapshot or self._case_settings_snapshot(case)
            image_providers = asset_prepare_image_providers_from_settings(
                case_snapshot.processor_settings,
                api_presets=case_snapshot.api_presets,
            )
            materialized = materialize_page_spec_assets(
                page_spec,
                source_image_path=source_image,
                output_dir=context.output_dir,
                rmbg_config=rmbg_config,
                rmbg_client=rmbg_client,
                image_generate=image_providers.get("image_generate"),
                image_edit=image_providers.get("image_edit"),
            )
            canonical_path = write_page_spec(Path(case.run_root) / "page_spec.json", materialized)
            output_path = write_page_spec(context.output_dir / "page_spec.json", materialized)
            preview_svg = context.output_dir / "processor_preview.svg"
            draft_semantic_svg_from_page_spec(
                output_path,
                preview_svg,
                href_base_dir=Path(case.run_root) / "svg",
            )
            if canonical_path != output_path:
                write_json(
                    Path(case.run_root) / "page_spec_asset_manifest.json",
                    page_spec_asset_manifest(output_path, svg_dir=Path(case.run_root) / "svg"),
                )
            outputs = [
                _workflow_output(
                    context,
                    "page_spec",
                    output_path,
                    "page_spec",
                    "drawai.page_spec.v1",
                )
            ]
            if any(port.port_id == "processor_preview" for port in context.node.outputs):
                outputs.append(
                    _workflow_output(
                        context,
                        "processor_preview",
                        preview_svg,
                        "semantic_svg",
                        "drawai.semantic_svg.v1",
                    )
                )
            return tuple(outputs)
        if processor_id == "asset_planner":
            elements_source = Path(_first_input_path(case.run_root, inputs)).expanduser().resolve(strict=False)
            if not elements_source.is_file():
                raise FileNotFoundError(f"Run0 Agent element plans output is missing: {elements_source}")
            payload = json.loads(elements_source.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping | list):
                raise ValueError("Run0 Agent output must be a JSON object or array of element plans")
            plans = element_plans_from_payload(payload)
            draft = draft_from_element_plans(case.run_root, plans, case_id=case.case_id)
            write_asset_draft(case.run_root, draft)
            _write_workflow_run_package(case, plans, last_stage="plan_assets")
            output_path = _copy_workflow_json(paths.run_package_json, context.output_dir / "elements.json")
            return (_workflow_output(context, "elements", output_path, "element_plans", "drawai.element_plans.v1"),)
        if processor_id == "asset_processors":
            with stage_state_lock:
                if not stage_state.get("process_assets"):
                    self._run_stage(case.case_id, "process_assets")
                    stage_state["process_assets"] = True
            output_path = _write_asset_packages_artifact(
                paths.run_package_json,
                context.output_dir / "asset_packages.json",
            )
            return (_workflow_output(context, "asset_packages", output_path, "asset_packages", "drawai.asset_packages.v1"),)
        raise ValueError(f"unsupported processor node: {processor_id or context.node.node_id}")

    def _run_sam_parse_page_spec(self, case: CaseRecord) -> dict[str, Any]:
        self._raise_if_case_canceled(case.case_id)
        paths = prepare_artifact_paths(case.run_root)
        if self.stage_executor is not None:
            with self._resource_slot("sam3"):
                self.stage_executor(case, "sam_parse")
            self._raise_if_case_canceled(case.case_id)
            payload = _read_json_object(paths.v2_parser_outputs_dir / "sam3_candidates.json")
            raw_candidates = payload.get("candidates")
            if not isinstance(raw_candidates, list):
                raise ValueError("sam_parse fixture must write sam3_candidates.json with candidates")
            return page_spec_from_candidates(
                raw_candidates,
                page_id=case.case_id,
                source_image=str(paths.figure_image),
                canvas=_source_metadata_canvas(paths),
                producer="sam_parse",
            )
        cfg = load_drawai_config(case.config_path, validate_input_exists=False)
        if not cfg.v2.parser.enabled or not cfg.v2.parser.sam3_enabled:
            candidates: tuple[Any, ...] = ()
        else:
            with self._resource_slot("sam3"):
                sam3_result = run_sam3_prompt_plan(cfg.sam3, paths.figure_image, paths)
            self._raise_if_case_canceled(case.case_id)
            from drawai.pipeline import _sam_boxes_by_prompt

            write_json(paths.sam_boxes_by_prompt_json, _sam_boxes_by_prompt(sam3_result))
            sam_payload = {
                "raw_regions": list(sam3_result.raw_regions),
                "prompt_runs": [
                    {
                        "prompt_id": run.prompt_id,
                        "artifact_path": str(run.artifact_path),
                        "elapsed_ms": run.elapsed_ms,
                    }
                    for run in sam3_result.prompt_runs
                ],
            }
            candidates = sam3_payload_to_candidates(sam_payload, paths.figure_image)
        write_json(
            paths.v2_parser_outputs_dir / "sam3_candidates.json",
            {"schema": "drawai.v2.parser_outputs.v1", "candidates": [candidate.to_dict() for candidate in candidates]},
        )
        return page_spec_from_candidates(
            candidates,
            page_id=case.case_id,
            source_image=str(paths.figure_image),
            canvas=_source_metadata_canvas(paths),
            producer="sam_parse",
        )

    def _run_ocr_parse_page_spec(self, case: CaseRecord) -> dict[str, Any]:
        self._raise_if_case_canceled(case.case_id)
        paths = prepare_artifact_paths(case.run_root)
        if self.stage_executor is not None:
            with self._resource_slot("ocr"):
                self.stage_executor(case, "ocr_parse")
            self._raise_if_case_canceled(case.case_id)
            payload = _read_json_object(paths.v2_parser_outputs_dir / "ocr_candidates.json")
            raw_candidates = payload.get("candidates")
            if not isinstance(raw_candidates, list):
                raise ValueError("ocr_parse fixture must write ocr_candidates.json with candidates")
            return page_spec_from_candidates(
                raw_candidates,
                page_id=case.case_id,
                source_image=str(paths.figure_image),
                canvas=_source_metadata_canvas(paths),
                producer="ocr_parse",
            )
        cfg = load_drawai_config(case.config_path, validate_input_exists=False)
        if not cfg.v2.parser.enabled or not cfg.v2.parser.ocr_enabled:
            ocr_payload: Mapping[str, Any] = {"ocr_text_boxes": []}
        else:
            from drawai.pipeline import _extract_ocr_boxes

            with self._resource_slot("ocr"):
                ocr_payload = _extract_ocr_boxes(cfg, paths.figure_image, None)
            self._raise_if_case_canceled(case.case_id)
            canvas_width, canvas_height = _source_metadata_canvas_size(
                _read_json_object(paths.source_metadata)
            )
            ocr_payload = clamp_ocr_boxes_to_canvas(
                ocr_payload,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
        write_json(paths.ocr_boxes_json, ocr_payload)
        candidates = ocr_payload_to_candidates(ocr_payload, paths.figure_image)
        write_json(
            paths.v2_parser_outputs_dir / "ocr_candidates.json",
            {"schema": "drawai.v2.parser_outputs.v1", "candidates": [candidate.to_dict() for candidate in candidates]},
        )
        return page_spec_from_candidates(
            candidates,
            page_id=case.case_id,
            source_image=str(paths.figure_image),
            canvas=_source_metadata_canvas(paths),
            producer="ocr_parse",
        )

    def _run_workflow_review_node(
        self,
        case: CaseRecord,
        context: NodeRunContext,
        inputs: tuple[Mapping[str, Any], ...],
        *,
        auto_approve: bool,
    ) -> tuple[Mapping[str, Any], ...]:
        self._raise_if_case_canceled(case.case_id)
        source = _first_input_path(case.run_root, inputs)
        input_type = str(inputs[0].get("type") or "") if inputs else ""
        if input_type == "page_spec":
            output_path = copy_page_spec_bundle(source, context.output_dir)
            return (_workflow_output(context, "page_spec", output_path, "page_spec", "drawai.page_spec.v1"),)
        if auto_approve:
            approve_asset_plan(case.run_root, read_asset_draft(case.run_root))
        output_path = _copy_workflow_json(source, context.output_dir / "confirmed_asset_packages.json")
        self._raise_if_case_canceled(case.case_id)
        return (_workflow_output(context, "asset_packages", output_path, "asset_packages", "drawai.asset_packages.v1"),)

    def _run_workflow_export_node(
        self,
        case: CaseRecord,
        context: NodeRunContext,
        inputs: tuple[Mapping[str, Any], ...],
        stage_state: dict[str, bool],
        stage_state_lock: threading.Lock | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        self._raise_if_case_canceled(case.case_id)
        exporter_id = str(context.node.config.get("exporter_id") or "")
        if exporter_id != "svg_to_ppt":
            raise ValueError(f"unsupported export node: {exporter_id or context.node.node_id}")
        paths = prepare_artifact_paths(case.run_root)
        svg_source = _first_input_path(case.run_root, inputs)
        canonical_svg = paths.semantic_svg

        def run_export_once() -> None:
            nonlocal canonical_svg
            self._raise_if_case_canceled(case.case_id)
            if not stage_state.get("export"):
                self.store.update_case_status(
                    case.case_id,
                    status="svg_running",
                    phase="reconstruction",
                    stage="export",
                )
                canonical_svg = _copy_workflow_file(svg_source, paths.semantic_svg)
                page_spec_source = _optional_input_path_by_type(
                    case.run_root,
                    inputs,
                    "page_spec",
                    format_id="drawai.page_spec.v1",
                )
                asset_manifest = (
                    page_spec_asset_manifest(page_spec_source, svg_dir=canonical_svg.parent)
                    if page_spec_source is not None
                    else {"schema": "drawai.page_spec_asset_manifest.v1", "assets": []}
                )
                asset_manifest, manifest_extension = extend_asset_manifest_for_svg_export(paths.root, asset_manifest)
                write_json(paths.asset_manifest_json, asset_manifest)
                report = check_svg_to_ppt_compatibility(
                    canonical_svg,
                    output_dir=paths.root,
                    export_pptx=True,
                    asset_manifest=asset_manifest,
                )
                report["asset_manifest_extension"] = manifest_extension
                write_json(paths.svg_to_ppt_export_report_json, report)
                if report.get("status") != "ok":
                    raise RuntimeError(_svg_to_ppt_report_error(report))
                self._raise_if_case_canceled(case.case_id)
                stage_state["export"] = True

        if stage_state_lock is None:
            run_export_once()
        else:
            with stage_state_lock:
                run_export_once()
        pptx_path = paths.root / "svg_to_ppt" / "semantic.svg_to_ppt.pptx"
        output_path = _copy_workflow_file(pptx_path, context.output_dir / "semantic.svg_to_ppt.pptx")
        self._raise_if_case_canceled(case.case_id)
        return (_workflow_output(context, "pptx", output_path, "pptx", "drawai.pptx.v1", deliverable=True),)

    def _ensure_workflow_stage(
        self,
        case: CaseRecord,
        stage: str,
        stage_state: dict[str, bool],
        *,
        stage_state_lock: threading.Lock | None = None,
    ) -> None:
        if stage_state_lock is not None:
            with stage_state_lock:
                self._ensure_workflow_stage_unlocked(case, stage, stage_state)
            return
        self._ensure_workflow_stage_unlocked(case, stage, stage_state)

    def _ensure_workflow_stage_unlocked(
        self,
        case: CaseRecord,
        stage: str,
        stage_state: dict[str, bool],
    ) -> None:
        for required in _workflow_stage_chain(stage):
            self._raise_if_case_canceled(case.case_id)
            if stage_state.get(required):
                continue
            self._run_stage(case.case_id, required)
            stage_state[required] = True

    def _run_analysis(self, case_id: str) -> None:
        case = self.store.get_case(case_id)
        try:
            self._raise_if_case_canceled(case_id)
            case = self._refresh_case_runtime_config(case)
            self.store.update_case_status(case_id, status="analysis_running", phase="analysis", stage="prepare")
            for stage in ANALYSIS_STAGES:
                self._raise_if_case_canceled(case_id)
                self._run_stage(case_id, stage)
            self._raise_if_case_canceled(case_id)
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
                    stale_from_stage="compose_svg",
                )
                self.store.update_case_status(
                    case_id,
                    status="svg_running",
                    phase="reconstruction",
                    stage="process_assets",
                    stale_from_stage="compose_svg",
                )
                self._run_stage(case_id, "process_assets")
                self._raise_if_case_canceled(case_id)
                self._register_standard_artifacts(case_id)
                self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="compose_svg")
                self._run_svg_generation(case_id)
            else:
                self._raise_if_case_canceled(case_id)
                self.store.update_case_status(case_id, status="assets_review", phase="analysis", stage="plan_assets")
            self._refresh_batch_status(case.batch_id)
        except WorkbenchCaseCanceled:
            self._mark_case_canceled(case_id)
        except Exception as exc:  # noqa: BLE001 - background job boundary records failures.
            if self._case_cancel_requested(case_id):
                self._mark_case_canceled(case_id)
                return
            self.store.update_case_status(
                case_id,
                status="failed",
                phase="analysis",
                stage=self.store.get_case(case_id).stage,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            self._refresh_batch_status(case.batch_id)

    def _rerun_case(self, case_id: str, stage: RerunStage) -> None:
        case = self.store.get_case(case_id)
        try:
            self._raise_if_case_canceled(case_id)
            case = self._refresh_case_runtime_config(case)
            canonical_stage = _canonical_rerun_stage(stage)
            if canonical_stage in {"analysis", "parse_elements", "fuse_elements", "refine_elements", "plan_assets"}:
                self._invalidate_from(case_id, "plan_assets")
                self._run_analysis(case_id)
            elif canonical_stage == "process_assets":
                self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="process_assets")
                self._run_stage(case_id, "process_assets")
                self._register_standard_artifacts(case_id)
                self.store.update_case_status(case_id, status="assets_review", phase="reconstruction", stage="process_assets")
            elif canonical_stage == "compose_svg":
                self._archive_current_svg_outputs(case_id)
                self._invalidate_from(case_id, "compose_svg")
                self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="process_assets")
                self._run_stage(case_id, "process_assets")
                self._register_standard_artifacts(case_id)
                self._run_svg_generation(case_id)
            elif canonical_stage == "export":
                self._invalidate_from(case_id, "export")
                self._run_export(case_id)
            self._refresh_batch_status(case.batch_id)
        except WorkbenchCaseCanceled:
            self._mark_case_canceled(case_id)
        except Exception as exc:  # noqa: BLE001 - background job boundary records failures.
            if self._case_cancel_requested(case_id):
                self._mark_case_canceled(case_id)
                return
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
        case = self.store.get_case(case_id)
        try:
            self._raise_if_case_canceled(case_id)
            case = self._refresh_case_runtime_config(case)
            self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="process_assets")
            self._run_stage(case_id, "process_assets")
            self._raise_if_case_canceled(case_id)
            self._register_standard_artifacts(case_id)
            self._run_svg_generation(case_id)
            self._refresh_batch_status(case.batch_id)
        except WorkbenchCaseCanceled:
            self._mark_case_canceled(case_id)
        except Exception as exc:  # noqa: BLE001 - background job boundary records failures.
            if self._case_cancel_requested(case_id):
                self._mark_case_canceled(case_id)
                return
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
        self._raise_if_case_canceled(case_id)
        self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="compose_svg")
        self._run_stage(case_id, "compose_svg")
        self._raise_if_case_canceled(case_id)
        self._register_standard_artifacts(case_id)
        self._run_export(case_id)
        case = self.store.get_case(case_id)
        self._refresh_batch_status(case.batch_id)

    def _run_export(self, case_id: str) -> None:
        self._raise_if_case_canceled(case_id)
        self.store.update_case_status(case_id, status="svg_running", phase="reconstruction", stage="export")
        self._run_stage(case_id, "export")
        self._raise_if_case_canceled(case_id)
        self._register_standard_artifacts(case_id)
        self.store.update_case_status(case_id, status="completed", phase="reconstruction", stage="completed")

    def _run_stage(self, case_id: str, stage: str) -> None:
        self._raise_if_case_canceled(case_id)
        case = self.store.get_case(case_id)
        reconstruction_stages = {"process_assets", "compose_svg", "export"}
        self.store.update_case_status(
            case_id,
            status="svg_running" if stage in reconstruction_stages else "analysis_running",
            phase="reconstruction" if stage in reconstruction_stages else "analysis",
            stage=stage,
        )
        stage_run = self.store.start_stage_run(case_id, stage)
        resources = STAGE_RESOURCES.get(stage, ())
        try:
            self._raise_if_case_canceled(case_id)
            if resources:
                with ExitStack() as stack:
                    for resource in resources:
                        stack.enter_context(self._resource_slot(resource))
                    self._raise_if_case_canceled(case_id)
                    self._execute_stage(case, stage)
            else:
                self._execute_stage(case, stage)
            self._raise_if_case_canceled(case_id)
            self.store.finish_stage_run(stage_run.stage_run_id, status="ok")
        except WorkbenchCaseCanceled:
            self.store.finish_stage_run(stage_run.stage_run_id, status="canceled", error_message="case run was canceled")
            raise
        except Exception as exc:
            if self._case_cancel_requested(case_id):
                self.store.finish_stage_run(stage_run.stage_run_id, status="canceled", error_message="case run was canceled")
                raise WorkbenchCaseCanceled("case run was canceled") from exc
            self.store.finish_stage_run(stage_run.stage_run_id, status="failed", error_message=f"{type(exc).__name__}: {exc}")
            raise

    def _execute_stage(self, case: CaseRecord, stage: str) -> None:
        self._raise_if_case_canceled(case.case_id)
        if self.stage_executor is not None:
            self.stage_executor(case, stage)
            self._raise_if_case_canceled(case.case_id)
            return
        if stage not in {*ANALYSIS_STAGES, "process_assets", "compose_svg", "export"}:
            raise ValueError(f"unsupported stage: {stage}")
        self._prepare_refinement_analysis_if_needed(case, stage)
        summary = run_drawai_pipeline_from_stage(case.config_path, stage, to_stage=stage)
        self._raise_if_case_canceled(case.case_id)
        if summary.get("status") != "ok":
            message = _pipeline_failure_message(summary)
            failed_stage = summary.get("failed_stage") or stage
            raise RuntimeError(f"DrawAI stage {failed_stage} failed: {message or summary.get('status')}")

    def _prepare_refinement_analysis_if_needed(self, case: CaseRecord, stage: str) -> None:
        if stage != "refine_elements":
            return
        cfg = load_drawai_config(case.config_path, validate_input_exists=False)
        if not cfg.v2.enabled or not cfg.v2.refine.enabled:
            return
        if cfg.v2.refine.provider != "codex_element_refiner":
            return
        paths = prepare_artifact_paths(cfg.input.output_dir)
        if _has_external_refinement_analysis(paths):
            return
        from drawai import pipeline as drawai_pipeline

        drawai_pipeline._run_codex_run0_asset_analysis(cfg, paths)

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
            ("run_package", "drawai_package.json", "application/json"),
            ("fusion_trace", "trace/v2_fusion_trace.json", "application/json"),
            ("refine_trace", "trace/v2_refine_trace.json", "application/json"),
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
        self._register_workflow_deliverable_artifacts(case_id, root)
        for package_path in sorted((root / "elements").glob("*/asset_package.json")):
            self.store.register_artifact(
                case_id,
                label=f"asset_package:{package_path.parent.name}",
                path=package_path,
                media_type="application/json",
            )

    def _register_workflow_deliverable_artifacts(self, case_id: str, root: Path) -> None:
        manifest_path = _latest_workflow_final_outputs(root)
        if manifest_path is None:
            return
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        outputs = payload.get("outputs") if isinstance(payload, Mapping) else None
        if not isinstance(outputs, list):
            return
        for output in outputs:
            if not isinstance(output, Mapping):
                continue
            artifact_info = _workflow_deliverable_artifact_info(output)
            if artifact_info is None:
                continue
            path = _workflow_output_artifact_path(root, output)
            if path is None or not path.is_file():
                continue
            label, media_type = artifact_info
            self.store.register_artifact(case_id, label=label, path=path, media_type=media_type)

    def _invalidate_from(self, case_id: str, stage: str) -> None:
        current = self.store.get_case(case_id)
        status = "assets_review" if stage in {"plan_assets", "compose_svg"} else current.status
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

    def _refresh_running_batches(self) -> None:
        for batch in self.store.list_batches():
            if batch.status == "running":
                self._refresh_batch_status(batch.batch_id)


def _idle_wait_remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return deadline - time.monotonic()


def _workflow_failure_detail(result: Any) -> str:
    for summary in getattr(result, "node_runs", ()):
        error = getattr(summary, "error", "")
        status = getattr(summary, "status", "")
        if status == "failed" and error:
            return str(error)
    for summary in getattr(result, "node_runs", ()):
        error = getattr(summary, "error", "")
        if error:
            return str(error)
    return ""


def _workflow_llm_runtime_config(
    case: CaseRecord,
    node_config: Mapping[str, Any],
    provider_id: str,
) -> dict[str, Any]:
    cfg = load_drawai_config(case.config_path, validate_input_exists=False)
    runtime = cfg.model_runtime.to_runtime_dict()
    runtime["provider"] = provider_id
    runtime["connection_id"] = provider_id
    model = str(node_config.get("model") or "").strip()
    if model:
        runtime["model_name"] = model
    timeout = node_config.get("timeout_seconds")
    if timeout not in (None, ""):
        runtime["timeout_seconds"] = timeout
    for key in ("base_url", "api_key", "api_key_env", "wire_api", "extra_body"):
        value = node_config.get(key)
        if value not in (None, ""):
            runtime[key] = value
    return runtime


def _has_external_refinement_analysis(paths: DrawAiArtifactPaths) -> bool:
    if not paths.element_analysis_json.is_file():
        return False
    status_path = paths.element_analysis_json.parent / "run_status.json"
    if status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if isinstance(status, dict) and status.get("status") != "ok":
            return False
    analysis = json.loads(paths.element_analysis_json.read_text(encoding="utf-8"))
    if not isinstance(analysis, dict):
        raise ValueError("Codex element refinement analysis must be a JSON object")
    source = str(analysis.get("source") or "")
    return not source.startswith("v2.")


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


def _workflow_template_with_agent_settings(
    template: WorkflowTemplate,
    settings: WorkbenchAgentSettings,
    *,
    execution_mode: str = "default",
    processor_operation_config: Mapping[str, Any] | None = None,
) -> WorkflowTemplate:
    mode = execution_mode.strip().lower()
    if mode not in {"default", "agent", "llm"}:
        raise ValueError(f"unsupported execution_mode: {execution_mode!r}. Expected one of: default, agent, llm")
    nodes = []
    for node in template.nodes:
        if node.node_type not in {"agent", "llm"}:
            nodes.append(node)
            continue
        base_config = {**dict(node.config), "node_id": node.node_id}
        if node.node_id == "page_spec_refine" and processor_operation_config:
            base_config.update(processor_operation_config)
        effective_type = node.node_type if mode == "default" else mode
        if effective_type == "llm":
            nodes.append(
                replace(
                    node,
                    node_type="llm",
                    config=apply_workbench_llm_settings_to_node_config(base_config, settings),
                )
            )
        else:
            config = dict(base_config)
            if _uses_workbench_default_agent_settings(config):
                config = apply_workbench_agent_settings_to_node_config(config, settings)
                config[_WORKBENCH_AGENT_SETTINGS_APPLIED] = True
            nodes.append(
                replace(
                    node,
                    node_type="agent",
                    config=config,
                )
            )
    return replace(template, nodes=tuple(nodes))


def _workflow_until_first_human_review(template: WorkflowTemplate) -> WorkflowTemplate | None:
    review_node_id = _first_human_review_node_id(template)
    if not review_node_id:
        return None
    upstream_ids = _upstream_node_ids(template, review_node_id)
    nodes = tuple(node for node in template.nodes if node.node_id in upstream_ids)
    edges = tuple(
        edge
        for edge in template.edges
        if edge.source_node_id in upstream_ids and edge.target_node_id in upstream_ids
    )
    return WorkflowTemplate(
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        version=template.version,
        schema=template.schema,
        defaults=template.defaults,
        nodes=nodes,
        edges=edges,
    )


def _first_human_review_node_id(template: WorkflowTemplate) -> str:
    node = next((item for item in template.nodes if item.node_type == "human_review"), None)
    return node.node_id if node is not None else ""


def _workflow_parser_ids(template: WorkflowTemplate) -> frozenset[str]:
    return frozenset(
        str(node.config.get("parser_id") or "")
        for node in template.nodes
        if node.node_type == "parser"
    )


def _workflow_parser_resources(parser_ids: frozenset[str]) -> tuple[str, ...]:
    resources: list[str] = []
    if "sam3_structure_parser" in parser_ids:
        resources.append("sam3")
    if "ocr_text_parser" in parser_ids:
        resources.append("ocr")
    return tuple(resources)


def workflow_breakpoint_node_id(run_root: str | Path) -> str:
    return _workflow_breakpoint_node_id(run_root)


def _workflow_breakpoint_node_id(run_root: str | Path) -> str:
    path = _workflow_breakpoint_path(run_root)
    if not path.is_file():
        return ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"workflow breakpoint file must be a mapping: {path}")
    return str(payload.get("node_id") or "")


def _write_workflow_breakpoint_node_id(run_root: str | Path, node_id: str) -> Path:
    path = _workflow_breakpoint_path(run_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "drawai.workflow_breakpoint.v1",
                "node_id": node_id,
                "updated_at": utc_now(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _clear_workflow_breakpoint_node_id(run_root: str | Path) -> None:
    path = _workflow_breakpoint_path(run_root)
    if path.exists():
        path.unlink()


def _workflow_breakpoint_path(run_root: str | Path) -> Path:
    return Path(run_root) / "reports" / "workbench" / "workflow_breakpoint.json"


def _upstream_node_ids(template: WorkflowTemplate, node_id: str) -> set[str]:
    incoming: dict[str, list[WorkflowEdge]] = {}
    for edge in template.edges:
        incoming.setdefault(edge.target_node_id, []).append(edge)
    seen: set[str] = set()

    def visit(current_id: str) -> None:
        if current_id in seen:
            return
        seen.add(current_id)
        for edge in incoming.get(current_id, ()):
            visit(edge.source_node_id)

    visit(node_id)
    return seen


def _workflow_stage_chain(stage: str) -> tuple[str, ...]:
    chains = {
        "prepare": ("prepare",),
        "parse_elements": ("prepare", "parse_elements"),
        "fuse_elements": ("prepare", "parse_elements", "fuse_elements"),
        "refine_elements": ("prepare", "parse_elements", "fuse_elements", "refine_elements"),
        "plan_assets": ("prepare", "parse_elements", "fuse_elements", "refine_elements", "plan_assets"),
        "process_assets": (
            "prepare",
            "parse_elements",
            "fuse_elements",
            "refine_elements",
            "plan_assets",
            "process_assets",
        ),
        "compose_svg": (
            "prepare",
            "parse_elements",
            "fuse_elements",
            "refine_elements",
            "plan_assets",
            "process_assets",
            "compose_svg",
        ),
        "export": (
            "prepare",
            "parse_elements",
            "fuse_elements",
            "refine_elements",
            "plan_assets",
            "process_assets",
            "compose_svg",
            "export",
        ),
    }
    if stage not in chains:
        raise ValueError(f"unsupported workflow-backed stage: {stage}")
    return chains[stage]


def _latest_workflow_final_outputs(root: Path) -> Path | None:
    output_runs = root / "nodes" / "output" / "runs"
    if not output_runs.is_dir():
        return None
    candidates = sorted(
        (
            run_dir / "output" / "final_outputs.json"
            for run_dir in output_runs.iterdir()
            if run_dir.is_dir()
        ),
        key=lambda path: path.parent.parent.name,
        reverse=True,
    )
    return next((path for path in candidates if path.is_file()), None)


def _workflow_deliverable_artifact_info(output: Mapping[str, Any]) -> tuple[str, str] | None:
    for key in (str(output.get("format_id") or ""), str(output.get("type") or "")):
        if key in WORKFLOW_DELIVERABLE_ARTIFACTS:
            return WORKFLOW_DELIVERABLE_ARTIFACTS[key]
    return None


def _workflow_output_artifact_path(root: Path, output: Mapping[str, Any]) -> Path | None:
    for key in ("mirror_path", "path"):
        raw = output.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        path = Path(raw)
        resolved = path.expanduser().resolve(strict=False) if path.is_absolute() else (root / path).resolve(strict=False)
        try:
            resolved.relative_to(root.resolve(strict=False))
        except ValueError:
            continue
        return resolved
    return None


def _copy_workflow_json(source: str | Path, target: str | Path) -> Path:
    source_path = Path(source).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise FileNotFoundError(f"workflow JSON artifact does not exist: {source_path}")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    target_path = Path(target).expanduser().resolve(strict=False)
    write_json(target_path, payload)
    return target_path


def _write_asset_packages_artifact(source: str | Path, target: str | Path) -> Path:
    source_path = Path(source).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise FileNotFoundError(f"workflow asset package source does not exist: {source_path}")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        raw_packages = payload.get("asset_packages")
        metadata = {
            "source_schema": str(payload.get("schema") or ""),
            "run_id": str(payload.get("run_id") or ""),
        }
    elif isinstance(payload, list):
        raw_packages = payload
        metadata = {}
    else:
        raise ValueError(f"workflow asset package source must be a JSON object or array: {source_path}")
    if isinstance(raw_packages, str) or not isinstance(raw_packages, list):
        raise ValueError("workflow asset package source must contain an asset_packages list")
    target_path = Path(target).expanduser().resolve(strict=False)
    write_json(
        target_path,
        {
            "schema": "drawai.asset_packages.v1",
            "asset_packages": raw_packages,
            "metadata": metadata,
        },
    )
    return target_path


def _read_optional_workflow_json(path: str | Path) -> Mapping[str, Any] | list[Any] | None:
    source_path = Path(path).expanduser().resolve(strict=False)
    if not source_path.is_file():
        return None
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping | list):
        return payload
    raise ValueError(f"workflow JSON artifact must be an object or array: {source_path}")


def _read_json_object(path: str | Path) -> dict[str, Any]:
    source_path = Path(path).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise FileNotFoundError(f"JSON artifact does not exist: {source_path}")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON artifact must be an object: {source_path}")
    return dict(payload)


def _svg_to_ppt_report_error(report: Mapping[str, Any]) -> str:
    failure_class = str(report.get("failure_class") or "unknown")
    issues = report.get("issues")
    if isinstance(issues, list) and issues:
        first_issue = issues[0]
        if isinstance(first_issue, Mapping):
            code = str(first_issue.get("code") or "issue")
            message = str(first_issue.get("message") or "")
            return f"SVG-to-PPTX export failed ({failure_class}): {code}{': ' + message if message else ''}"
    return f"SVG-to-PPTX export failed ({failure_class})"


def _copy_workflow_file(source: str | Path, target: str | Path) -> Path:
    source_path = Path(source).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise FileNotFoundError(f"workflow artifact does not exist: {source_path}")
    target_path = Path(target).expanduser().resolve(strict=False)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return target_path


def _write_workflow_run_package(
    case: CaseRecord,
    plans: tuple[ElementPlan, ...],
    *,
    last_stage: str,
) -> Path:
    root = Path(case.run_root).expanduser().resolve()
    paths = prepare_artifact_paths(root)
    source_metadata = json.loads(paths.source_metadata.read_text(encoding="utf-8"))
    if not isinstance(source_metadata, Mapping):
        raise ValueError("source_metadata.json must be a JSON object")
    width, height = _source_metadata_canvas_size(source_metadata)
    for plan in plans:
        write_element_plan(root, plan)
    pending_packages = tuple(
        AssetPackage.empty(
            asset_id=f"A{index:03d}",
            element_id=plan.element_id,
            processor_type=plan.processing_intent.processing_type,
        )
        for index, plan in enumerate(plans, start=1)
    )
    payload = {
        "schema": RUN_PACKAGE_SCHEMA,
        "run_id": case.case_id,
        "root": str(root),
        "source_image": str(paths.figure_image),
        "canvas": {"width": width, "height": height},
        "created_at": utc_now(),
        "metadata": {"last_stage": last_stage, "v2_enabled": True},
        "elements": [plan.to_dict() for plan in plans],
        "asset_packages": [package.to_dict() for package in pending_packages],
    }
    write_json(paths.run_package_json, payload)
    return paths.run_package_json


def _source_metadata_canvas(paths: DrawAiArtifactPaths) -> dict[str, float]:
    metadata = _read_json_object(paths.source_metadata)
    width, height = _source_metadata_canvas_size(metadata)
    return {"width_px": width, "height_px": height}


def _source_metadata_canvas_size(source_metadata: Mapping[str, Any]) -> tuple[float, float]:
    raw_size = source_metadata.get("normalized_size")
    if isinstance(raw_size, list | tuple) and len(raw_size) >= 2:
        width = float(raw_size[0])
        height = float(raw_size[1])
    else:
        canvas = source_metadata.get("canvas")
        if isinstance(canvas, Mapping):
            width = float(canvas.get("width") or 0)
            height = float(canvas.get("height") or 0)
        else:
            width = float(source_metadata.get("width") or 0)
            height = float(source_metadata.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("source metadata must contain normalized_size [width, height] or positive width/height")
    return width, height


def _node_output_port_is_deliverable(context: NodeRunContext, port_id: str) -> bool:
    for port in context.node.outputs:
        if port.port_id == port_id:
            return "deliverable" in port.description.lower()
    return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _workflow_output(
    context: NodeRunContext,
    port_id: str,
    path: str | Path,
    artifact_type: str,
    format_id: str,
    *,
    deliverable: bool = False,
    prompt_path: str | Path | None = None,
    stdout_path: str | Path | None = None,
    stderr_path: str | Path | None = None,
    trace_path: str | Path | None = None,
    session_log_path: str | Path | None = None,
    execution_manifest_path: str | Path | None = None,
    exit_code: int = 0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "port_id": port_id,
        "path": context.relative_path(path),
        "format_id": format_id,
        "type": artifact_type,
    }
    if deliverable:
        payload["deliverable"] = True
    if prompt_path is not None:
        payload["prompt_path"] = context.relative_path(prompt_path)
    if stdout_path is not None:
        payload["stdout_path"] = context.relative_path(stdout_path)
    if stderr_path is not None:
        payload["stderr_path"] = context.relative_path(stderr_path)
    if trace_path is not None:
        payload["trace_path"] = context.relative_path(trace_path)
    if session_log_path is not None:
        payload["session_log_path"] = context.relative_path(session_log_path)
    if execution_manifest_path is not None:
        payload["execution_manifest_path"] = context.relative_path(execution_manifest_path)
    payload["exit_code"] = int(exit_code)
    return payload


def _first_input_path(run_root: str | Path, inputs: tuple[Mapping[str, Any], ...]) -> Path:
    if not inputs:
        raise ValueError("workflow review node requires an input artifact")
    path = inputs[0].get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("workflow input artifact path is missing")
    path_obj = Path(path)
    return path_obj if path_obj.is_absolute() else Path(run_root) / path_obj


def _input_path_by_type(
    run_root: str | Path,
    inputs: tuple[Mapping[str, Any], ...],
    artifact_type: str,
    *,
    format_id: str = "",
) -> Path:
    for item in inputs:
        if item.get("type") != artifact_type:
            continue
        if format_id and item.get("format_id") != format_id:
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"workflow {artifact_type} input artifact path is missing")
        path_obj = Path(path)
        return path_obj if path_obj.is_absolute() else Path(run_root) / path_obj
    expected = f"{artifact_type} ({format_id})" if format_id else artifact_type
    raise ValueError(f"workflow node requires an input artifact of type {expected}")


def _optional_input_path_by_type(
    run_root: str | Path,
    inputs: tuple[Mapping[str, Any], ...],
    artifact_type: str,
    *,
    format_id: str = "",
) -> Path | None:
    for item in inputs:
        if item.get("type") != artifact_type:
            continue
        if format_id and item.get("format_id") != format_id:
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"workflow {artifact_type} input artifact path is missing")
        path_obj = Path(path)
        return path_obj if path_obj.is_absolute() else Path(run_root) / path_obj
    return None


def _input_paths_by_type(
    run_root: str | Path,
    inputs: tuple[Mapping[str, Any], ...],
    artifact_type: str,
    *,
    format_id: str = "",
) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        if item.get("type") != artifact_type:
            continue
        if format_id and item.get("format_id") != format_id:
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"workflow {artifact_type} input artifact path is missing")
        path_obj = Path(path)
        paths.append(path_obj if path_obj.is_absolute() else Path(run_root) / path_obj)
    if not paths:
        expected = f"{artifact_type} ({format_id})" if format_id else artifact_type
        raise ValueError(f"workflow node requires at least one input artifact of type {expected}")
    return paths


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
    agent_settings: Mapping[str, Any] | None = None,
    execution_mode: str = "default",
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
    if agent_settings is not None:
        apply_workbench_agent_settings_to_config_payload(
            payload,
            normalize_workbench_agent_settings(agent_settings),
            execution_mode=execution_mode,
        )
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
