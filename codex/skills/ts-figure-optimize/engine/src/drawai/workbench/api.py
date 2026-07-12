from __future__ import annotations

import argparse
import base64
import binascii
import json
import mimetypes
import os
import posixpath
import re
import shutil
import sqlite3
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from lxml import etree
from PIL import Image

from ..artifacts import write_json
from .assets import process_asset_plan_elements, read_asset_draft, validate_asset_plan, write_asset_draft
from .agent_settings import (
    discover_workbench_agents,
    normalize_workbench_agent_settings,
    read_workbench_agent_settings,
    workbench_agent_settings_payload,
    write_workbench_agent_settings,
)
from .api_presets import (
    ApiPreset,
    api_preset_by_id,
    read_workbench_api_presets,
    resolve_api_preset_logo_url,
    workbench_api_presets_payload,
    write_workbench_api_presets,
)
from .case_settings_snapshot import (
    case_settings_snapshot_from_workspace,
    read_case_settings_snapshot_or_workspace,
    write_case_settings_snapshot,
)
from .image_processor_providers import images_api_edit_provider as _shared_images_api_edit_provider
from .processor_settings import (
    PROCESSOR_DRIVER_DEFINITIONS,
    ProcessorSetting,
    require_processor_configured,
    resolved_processor_operation_config_from_settings,
    workbench_processor_settings_payload,
    write_workbench_processor_settings,
)
from .status_overview import workbench_status_overview_payload
from ..codex_python_sdk_imagegen import (
    CodexPythonSdkImageGenError,
    CodexImageGenResult,
    invoke_codex_python_sdk_image_edit,
    invoke_codex_python_sdk_image_reference_context,
    invoke_codex_python_sdk_imagegen,
)
from ..config import load_drawai_config
from ..http_utils import urlopen_direct_for_loopback
from ..rmbg_client import RemoteRmbgClient
from ..slide_image_prompt import (
    build_slide_image_api_generation_prompt,
    build_slide_image_generation_prompt,
    codex_imagegen_context_payload,
    merge_codex_imagegen_context,
)
from ..slide_template_library import list_template_cards, recommend_template_cards
from ..v2.packages import classify_run_root, element_dir
from ..v2.workbench import (
    LegacyReadOnlyCaseError,
    V2PackageUnavailableError,
    activate_case_asset_result,
    case_asset_package_payload,
    case_elements_payload,
    case_package_payload,
    ensure_v2_mutation_allowed,
    fork_v2_case_from_source,
    process_case_asset,
)
from .agent_settings import WORKBENCH_SELECTABLE_AGENT_PROVIDER_IDS
from .models import BatchExecutionMode, CaseRecord, WorkbenchSettings
from .runner import WorkbenchRunner, create_case_config, workflow_breakpoint_node_id, _workflow_template_with_agent_settings
from .store import WorkbenchStore
from drawai.workflow.agents import (
    agent_preset_by_id,
    default_agent_provider_registry,
    render_agent_prompt,
)
from drawai.workflow.templates import (
    DEFAULT_WORKFLOW_TEMPLATE_ID,
    copy_builtin_template_to_workspace,
    list_workflow_templates,
    load_workflow_template_by_id,
    save_workflow_template,
    workflow_template_from_dict,
)
from drawai.workflow.validation import validate_workflow_template
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ARCHIVE_EXTENSIONS = {".zip"}
MAX_SVG_SOURCE_BYTES = 5 * 1024 * 1024
MAX_GENERATED_IMAGE_BYTES = 50 * 1024 * 1024
GENERATED_IMAGE_URL_FIELDS = {"generated_image_urls", "image_urls"}
SVG_NS = "http://www.w3.org/2000/svg"
UNSAFE_SVG_TAGS = {"script", "foreignObject", "iframe", "object", "embed"}
IMAGEGEN_OPENAI_API_URL = "https://api.openai.com/v1/images/generations"
IMAGEGEN_DEFAULT_MODEL = "gpt-image-2"
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
PPT_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
PPT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PPT_SLIDE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
PPT_SLIDE_LAYOUT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
PPT_SLIDE_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
IMAGEGEN_ALLOWED_FIELDS = {
    "model",
    "prompt",
    "size",
    "quality",
    "background",
    "moderation",
    "output_format",
    "output_compression",
    "n",
    "partial_images",
    "stream",
    "source_image_path",
    "reference_image_path",
    "reference_image_paths",
    "image_path",
}
SLIDE_TEMPLATE_GALLERY_SCHEMA = "drawai.workbench.slide_template_gallery.v1"
SLIDE_TEMPLATE_GALLERY_DEFAULT_DIR = (
    Path(__file__).resolve().parents[3] / "outputs" / "ppt_template_gallery_category_sample"
)
SLIDE_TEMPLATE_GALLERY_FILE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".json", ".md", ".txt"}

urlopen_external = urllib.request.urlopen


def create_app(
    settings: WorkbenchSettings | None = None,
    *,
    store: WorkbenchStore | None = None,
    runner: WorkbenchRunner | None = None,
    runtime_probe: Callable[[str, str], dict[str, Any]] | None = None,
    rmbg_client: Any = None,
) -> FastAPI:
    resolved_settings = settings or settings_from_env()
    resolved_store = store or WorkbenchStore(resolved_settings.workspace)
    resolved_runner = runner or WorkbenchRunner(resolved_store, resolved_settings)
    app = FastAPI(title="DrawAI Workbench API", version="0.1.0")
    app.state.settings = resolved_settings
    app.state.store = resolved_store
    app.state.runner = resolved_runner
    app.state.rmbg_client = rmbg_client
    app.state.workbench_agent_discovery_snapshot = discover_workbench_agents()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ],
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        runtime_services = _runtime_services_status(resolved_settings, runtime_probe=runtime_probe)
        return {
            "status": "ok" if _runtime_services_online(runtime_services) else "degraded",
            "workspace": str(resolved_store.workspace),
            "cloud_mode": resolved_settings.cloud_mode,
            "runtime_services": runtime_services,
            "runtime_activity": resolved_runner.resource_activity(),
        }

    @app.get("/api/workflow/templates")
    def list_workflow_template_api() -> dict[str, Any]:
        return {
            "templates": [
                template.to_dict()
                for template in list_workflow_templates(resolved_store.workspace)
            ]
        }

    @app.post("/api/workflow/templates/copy")
    async def copy_workflow_template_api(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="workflow template copy payload must be an object")
        template_id = str(payload.get("template_id") or "")
        name = str(payload.get("name") or "").strip()
        if not template_id:
            raise HTTPException(status_code=400, detail="template_id is required")
        if not name:
            raise HTTPException(status_code=400, detail="template name is required")
        try:
            template = copy_builtin_template_to_workspace(
                resolved_store.workspace,
                template_id,
                name=name,
                overwrite=_as_bool(payload.get("overwrite", True)),
            )
        except (FileExistsError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"template": template.to_dict()}

    @app.post("/api/workflow/templates/validate")
    async def validate_workflow_template_api(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="workflow template payload must be an object")
        try:
            template = workflow_template_from_dict(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = validate_workflow_template(template)
        return {"validation": result.to_dict(), "template": template.to_dict()}

    @app.get("/api/workflow/templates/{template_id}")
    def get_workflow_template_api(template_id: str) -> dict[str, Any]:
        try:
            template = load_workflow_template_by_id(resolved_store.workspace, template_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"template": template.to_dict()}

    @app.put("/api/workflow/templates/{template_id}")
    async def save_workflow_template_api(template_id: str, request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="workflow template payload must be an object")
        try:
            template = workflow_template_from_dict(payload)
            if template.template_id != template_id:
                raise ValueError("template_id path and payload must match")
            path = save_workflow_template(resolved_store.workspace, template)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"template": template.to_dict(), "path": str(path)}

    @app.get("/api/workflow/providers")
    def list_workflow_agent_providers_api() -> dict[str, Any]:
        selectable = set(WORKBENCH_SELECTABLE_AGENT_PROVIDER_IDS)
        return {
            "providers": [
                provider.to_dict()
                for provider in default_agent_provider_registry().values()
                if provider.provider_id in selectable
            ]
        }

    @app.get("/api/workbench/agent-settings")
    def get_workbench_agent_settings_api(request: Request) -> dict[str, Any]:
        include_agents = _include_agents_param(request)
        agents = _workbench_agent_discovery_snapshot(app, refresh=_refresh_agents_param(request)) if include_agents else []
        return workbench_agent_settings_payload(
            resolved_store.workspace,
            include_agents=include_agents,
            agents=agents,
        )

    @app.put("/api/workbench/agent-settings")
    async def save_workbench_agent_settings_api(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Workbench agent settings payload must be an object")
        try:
            write_workbench_agent_settings(resolved_store.workspace, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        include_agents = _include_agents_param(request)
        agents = _workbench_agent_discovery_snapshot(app, refresh=_refresh_agents_param(request)) if include_agents else []
        return workbench_agent_settings_payload(
            resolved_store.workspace,
            include_agents=include_agents,
            agents=agents,
        )

    @app.get("/api/workbench/api-presets")
    def get_workbench_api_presets_api() -> dict[str, Any]:
        return workbench_api_presets_payload(resolved_store.workspace)

    @app.get("/api/workbench/api-preset-logo")
    def get_workbench_api_preset_logo_api(base_url: str) -> dict[str, str]:
        normalized_base_url = base_url.strip()
        if not normalized_base_url:
            raise HTTPException(status_code=400, detail="base_url is required")
        return {"icon_url": resolve_api_preset_logo_url(normalized_base_url)}

    @app.put("/api/workbench/api-presets")
    async def save_workbench_api_presets_api(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Workbench API presets payload must be an object")
        try:
            write_workbench_api_presets(resolved_store.workspace, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return workbench_api_presets_payload(resolved_store.workspace)

    @app.get("/api/workbench/processor-settings")
    def get_workbench_processor_settings_api() -> dict[str, Any]:
        return workbench_processor_settings_payload(resolved_store.workspace)

    @app.put("/api/workbench/processor-settings")
    async def save_workbench_processor_settings_api(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Workbench processor settings payload must be an object")
        try:
            write_workbench_processor_settings(resolved_store.workspace, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return workbench_processor_settings_payload(resolved_store.workspace)

    @app.get("/api/workbench/status-overview")
    def get_workbench_status_overview_api() -> dict[str, Any]:
        runtime_services = _runtime_services_status(resolved_settings, runtime_probe=runtime_probe)
        return workbench_status_overview_payload(
            resolved_store.workspace,
            settings=resolved_settings,
            runtime_services=runtime_services,
        )

    @app.post("/api/workflow/agent-prompt-preview")
    async def workflow_agent_prompt_preview_api(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Agent prompt payload must be an object")
        preset_id = str(payload.get("preset_id") or "")
        inputs = payload.get("inputs", [])
        node_config = payload.get("node_config", {})
        if not preset_id:
            raise HTTPException(status_code=400, detail="preset_id is required")
        if not isinstance(inputs, list):
            raise HTTPException(status_code=400, detail="inputs must be an array")
        if not isinstance(node_config, dict):
            raise HTTPException(status_code=400, detail="node_config must be an object")
        try:
            prompt = render_agent_prompt(
                agent_preset_by_id(preset_id),
                inputs=tuple(item for item in inputs if isinstance(item, dict)),
                node_config=node_config,
                runtime_context={
                    "workflow_run_root": "<workflow_run_root>",
                    "node_workdir": f"<workflow_run_root>/nodes/{node_config.get('node_id') or '<agent_node_id>'}/runs/<attempt_id>",
                    "agent_cwd": "<workflow_run_root>",
                    "repo_root": str(Path(__file__).resolve().parents[3]),
                    "attempt_id": "<attempt_id>",
                    "drawai_tool_command_prefix": "<drawai_tool_command_prefix>",
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"prompt": prompt.to_dict()}

    @app.get("/api/slide-template-cards")
    def slide_template_cards(q: str = "", limit: int = 0) -> dict[str, Any]:
        cards = recommend_template_cards(q, limit=limit) if q.strip() and limit else list_template_cards()
        if limit and not q.strip():
            cards = cards[: max(1, int(limit))]
        return {
            "schema": "drawai.workbench.slide_template_cards.v1",
            "count": len(cards),
            "cards": cards,
        }

    @app.get("/api/slide-template-cards/recommend")
    def recommended_slide_template_cards(q: str = "", limit: int = 8) -> dict[str, Any]:
        cards = recommend_template_cards(q, limit=max(1, int(limit or 8)))
        return {
            "schema": "drawai.workbench.slide_template_card_recommendations.v1",
            "query": q,
            "count": len(cards),
            "cards": cards,
        }

    @app.get("/api/slide-template-gallery")
    def slide_template_gallery() -> dict[str, Any]:
        return _slide_template_gallery_payload()

    @app.get("/api/slide-template-gallery/files/{relative_path:path}")
    def slide_template_gallery_file(relative_path: str) -> FileResponse:
        root = _slide_template_gallery_root()
        path = _resolve_slide_template_gallery_file(root, relative_path)
        return FileResponse(path, media_type=_media_type(path), filename=path.name)

    @app.post("/api/imagegen/generations")
    async def generate_images(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="image generation payload must be an object")
        provider = _image_generation_provider(payload)
        if provider != "codex" and _image_generation_source_image_path(payload):
            raise HTTPException(status_code=400, detail="reference image generation currently requires provider=codex")
        normalized = _normalize_image_generation_payload(payload)
        if provider == "codex":
            return _call_codex_image_generation(
                merge_codex_imagegen_context(normalized, payload),
                store=resolved_store,
                settings=resolved_settings,
            )
        api_url = _image_generation_api_url(payload.get("api_base_url") or payload.get("base_url"))
        api_key = str(payload.get("api_key") or "").strip() or None
        return _call_image_generation_upstream(
            _api_image_generation_payload(normalized, payload),
            api_url=api_url,
            api_key=api_key,
        )

    @app.post("/api/imagegen/edits")
    async def edit_image(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="image edit payload must be an object")
        if _image_generation_provider(payload) != "codex":
            raise HTTPException(status_code=400, detail="image edits currently require provider=codex")
        normalized = _normalize_image_edit_payload(payload)
        return _call_codex_image_edit(normalized, store=resolved_store, settings=resolved_settings)

    @app.post("/api/batches")
    async def create_batch(request: Request) -> dict[str, Any]:
        payload, upload_files = await _parse_batch_request(request)
        input_mode = str(payload.get("input_mode") or ("local_dir" if payload.get("local_dir") else "upload"))
        if input_mode not in {"upload", "zip", "local_dir"}:
            raise HTTPException(status_code=400, detail="input_mode must be upload, zip, or local_dir")
        if resolved_settings.cloud_mode and input_mode == "local_dir":
            raise HTTPException(status_code=400, detail="local_dir input is disabled in cloud mode")
        max_cases = int(payload.get("max_concurrent_cases") or resolved_settings.max_concurrent_cases)
        if max_cases <= 0:
            raise HTTPException(status_code=400, detail="max_concurrent_cases must be positive")
        base_config = Path(str(payload.get("base_config_path") or resolved_settings.default_config)).expanduser().resolve(strict=False)
        if not base_config.exists():
            raise HTTPException(status_code=400, detail=f"base config does not exist: {base_config}")
        workflow_template_id = str(payload.get("workflow_template_id") or DEFAULT_WORKFLOW_TEMPLATE_ID)
        try:
            load_workflow_template_by_id(resolved_store.workspace, workflow_template_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"workflow template is not available: {workflow_template_id}") from exc
        execution_mode = _batch_execution_mode(payload.get("execution_mode"))
        try:
            agent_settings = _batch_agent_settings(payload.get("agent_settings"), resolved_store.workspace)
            settings_snapshot = case_settings_snapshot_from_workspace(
                resolved_store.workspace,
                agent_settings=agent_settings,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        batch = resolved_store.create_batch(
            name=str(payload.get("name") or "DrawAI batch"),
            input_mode=input_mode,  # type: ignore[arg-type]
            max_concurrent_cases=max_cases,
            auto_run_svg_after_analysis=_as_bool(payload.get("auto_run_svg_after_analysis")),
            config_path=base_config,
            workflow_template_id=workflow_template_id,
            execution_mode=execution_mode,
        )
        try:
            sources = await _collect_sources(
                resolved_store,
                batch.batch_id,
                input_mode=input_mode,
                local_dir=payload.get("local_dir"),
                upload_files=upload_files,
                generated_image_urls=_string_list_field(payload.get("generated_image_urls") or payload.get("image_urls")),
            )
        except HTTPException as exc:
            resolved_store.update_batch_status(batch.batch_id, "failed", error_message=str(exc.detail))
            raise
        for source in sources:
            case = resolved_store.create_case(
                batch_id=batch.batch_id,
                name=source.name,
                source_image_path=source,
                config_path=base_config,
            )
            write_case_settings_snapshot(case.run_root, settings_snapshot)
            config_path = create_case_config(
                base_config_path=base_config,
                source_image=source,
                output_dir=case.run_root,
                target_path=Path(case.run_root) / "drawai.config.yaml",
                sam3_base_url=resolved_settings.sam3_base_url,
                ocr_base_url=resolved_settings.ocr_base_url,
                ocr_timeout_seconds=resolved_settings.ocr_timeout_seconds,
                rmbg_base_url=resolved_settings.rmbg_base_url,
                agent_settings=settings_snapshot.agent_settings.to_dict(),
                execution_mode=execution_mode,
            )
            resolved_store.update_case_config_path(case.case_id, config_path)
        resolved_runner.submit_batch(batch.batch_id)
        return {
            "batch": resolved_store.get_batch(batch.batch_id).to_api(case_counts=resolved_store.case_counts(batch.batch_id)),
            "cases": [_case_to_api_with_preview(resolved_store, case) for case in resolved_store.list_cases(batch.batch_id)],
        }

    @app.get("/api/batches")
    def list_batches() -> dict[str, Any]:
        return {
            "batches": [
                batch.to_api(case_counts=resolved_store.case_counts(batch.batch_id))
                for batch in resolved_store.list_batches()
            ]
        }

    @app.get("/api/batches/{batch_id}")
    def get_batch(batch_id: str) -> dict[str, Any]:
        batch = _get_batch_or_404(resolved_store, batch_id)
        return _batch_detail_payload(resolved_store, batch.batch_id)

    @app.get("/api/batches/{batch_id}/pptx")
    def download_batch_pptx(batch_id: str) -> FileResponse:
        batch = _get_batch_or_404(resolved_store, batch_id)
        pptx_paths = _completed_batch_pptx_paths(resolved_store, batch.batch_id)
        output_dir = resolved_store.workspace / "exports" / batch.batch_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{_safe_download_stem(batch.name)}.pptx"
        _merge_pptx_files(pptx_paths, output_path)
        return FileResponse(output_path, media_type=PPTX_MEDIA_TYPE, filename=output_path.name)

    @app.patch("/api/batches/{batch_id}")
    async def update_batch(batch_id: str, request: Request) -> dict[str, Any]:
        _get_batch_or_404(resolved_store, batch_id)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="batch payload must be an object")
        name = payload.get("name")
        if not isinstance(name, str):
            raise HTTPException(status_code=400, detail="batch name must be a string")
        try:
            batch = resolved_store.rename_batch(batch_id, name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _batch_detail_payload(resolved_store, batch.batch_id)

    @app.delete("/api/batches/{batch_id}")
    def delete_batch(batch_id: str) -> dict[str, Any]:
        _get_batch_or_404(resolved_store, batch_id)
        running_cases = _active_cases(resolved_store.list_cases(batch_id))
        if running_cases:
            raise HTTPException(status_code=409, detail="cannot delete a task while cases are running")
        resolved_store.delete_batch(batch_id)
        return {"batch_id": batch_id}

    @app.post("/api/batches/{batch_id}/run")
    def run_batch(batch_id: str) -> dict[str, Any]:
        _get_batch_or_404(resolved_store, batch_id)
        cases = resolved_store.list_cases(batch_id)
        if not cases:
            raise HTTPException(status_code=400, detail="task has no cases to run")
        running_cases = _active_cases(cases)
        if running_cases:
            raise HTTPException(status_code=409, detail="task already has running cases")
        resolved_store.update_batch_status(batch_id, "running")
        try:
            for case in cases:
                if _case_has_asset_draft(case):
                    resolved_runner.approve_case(case.case_id, run_svg=True)
                else:
                    resolved_runner.submit_rerun(case.case_id, "analysis")
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _batch_detail_payload(resolved_store, batch_id)

    @app.get("/api/batches/{batch_id}/cases")
    def list_cases(batch_id: str) -> dict[str, Any]:
        _get_batch_or_404(resolved_store, batch_id)
        return {"cases": [_case_to_api_with_preview(resolved_store, case) for case in resolved_store.list_cases(batch_id)]}

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        return {
            "case": _case_to_api_with_preview(resolved_store, case),
            "stage_runs": [stage.to_api() for stage in resolved_store.list_stage_runs(case_id)],
            "artifacts": [artifact.to_api() for artifact in resolved_store.list_artifacts(case_id)],
        }

    @app.get("/api/cases/{case_id}/progress")
    def get_case_progress(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        root = Path(case.run_root)
        stage_runs = [stage.to_api() for stage in resolved_store.list_stage_runs(case_id)]
        return {
            "case": _case_to_api_with_preview(resolved_store, case),
            "stage_runs": stage_runs,
            "workflow_node_runs": _workflow_node_runs_progress(root),
            "workflow_nodes": _workflow_node_metadata(resolved_store, case),
            "files": _standard_progress_files(case_id, root),
            "svg_attempts": _svg_attempts_progress(case_id, root),
            "pptx_export": _pptx_export_progress(case_id, root),
        }

    @app.get("/api/cases/{case_id}/source-image")
    def get_case_source_image(case_id: str) -> FileResponse:
        case = _get_case_or_404(resolved_store, case_id)
        path = Path(case.source_image_path).expanduser().resolve(strict=False)
        if not path.exists() or not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(status_code=404, detail="case source image is missing")
        return FileResponse(path, media_type=_media_type(path), filename=path.name)

    @app.get("/api/cases/{case_id}/files/{relative_path:path}")
    def get_case_file(case_id: str, relative_path: str) -> FileResponse:
        case = _get_case_or_404(resolved_store, case_id)
        path = _resolve_case_path(Path(case.run_root), relative_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="case file is missing")
        return FileResponse(path, media_type=_media_type(path), filename=path.name)

    @app.get("/api/cases/{case_id}/artifacts")
    def list_artifacts(case_id: str) -> dict[str, Any]:
        _get_case_or_404(resolved_store, case_id)
        return {"artifacts": [artifact.to_api() for artifact in resolved_store.list_artifacts(case_id)]}

    @app.get("/api/cases/{case_id}/assets")
    def get_assets(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        try:
            return {"asset_plan": read_asset_draft(case.run_root)}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="asset draft is not available yet") from exc

    @app.get("/api/cases/{case_id}/package")
    def get_case_package(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        try:
            return case_package_payload(case)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/cases/{case_id}/elements")
    def get_case_elements(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        try:
            return case_elements_payload(case)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/cases/{case_id}/elements/{element_id}/asset-package")
    def get_case_asset_package(case_id: str, element_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        try:
            return case_asset_package_payload(case, element_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/cases/{case_id}/workflow/nodes/{node_id}/viewer")
    def get_workflow_node_viewer(case_id: str, node_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        try:
            return _workflow_node_viewer_payload(case, node_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/cases/{case_id}/workflow/breakpoint")
    async def set_workflow_breakpoint(case_id: str, request: Request) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        _reject_legacy_case_mutation(case)
        payload = await request.json()
        node_id = str(payload.get("node_id") or "")
        try:
            resolved_runner.set_workflow_breakpoint(case_id, node_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"case": _case_to_api_with_preview(resolved_store, resolved_store.get_case(case_id))}

    @app.delete("/api/cases/{case_id}/workflow/breakpoint")
    def clear_workflow_breakpoint(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        _reject_legacy_case_mutation(case)
        resolved_runner.clear_workflow_breakpoint(case_id)
        return {"case": _case_to_api_with_preview(resolved_store, resolved_store.get_case(case_id))}

    @app.post("/api/cases/{case_id}/workflow/continue")
    def continue_workflow_case(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        _reject_legacy_case_mutation(case)
        try:
            resolved_runner.continue_workflow_case(case_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"case": _case_to_api_with_preview(resolved_store, resolved_store.get_case(case_id))}

    @app.post("/api/cases/{case_id}/elements/{element_id}/process")
    async def process_case_element(case_id: str, element_id: str, request: Request) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="asset process payload must be an object")
        processor = payload.get("processor")
        if not isinstance(processor, str) or not processor:
            raise HTTPException(status_code=400, detail="processor must be a non-empty string")
        try:
            processor_setting = require_processor_configured(resolved_store.workspace, processor)
            asset_package = process_case_asset(
                case,
                element_id,
                processor,
                providers=_asset_processor_providers(
                    case,
                    processor,
                    resolved_settings,
                    app.state.rmbg_client,
                    processor_setting=processor_setting,
                ),
            )
        except LegacyReadOnlyCaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except V2PackageUnavailableError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            _mark_asset_outputs_stale_if_failed_package(resolved_store, case_id, element_id, processor)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _mark_asset_outputs_stale(resolved_store, case_id)
        return {"asset_package": asset_package, "case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/elements/{element_id}/active-result")
    async def activate_case_element_result(case_id: str, element_id: str, request: Request) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="active-result payload must be an object")
        result_id = payload.get("result_id")
        if not isinstance(result_id, str) or not result_id:
            raise HTTPException(status_code=400, detail="result_id must be a non-empty string")
        try:
            asset_package = activate_case_asset_result(case, element_id, result_id)
        except LegacyReadOnlyCaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except V2PackageUnavailableError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _mark_asset_outputs_stale(resolved_store, case_id)
        return {"asset_package": asset_package, "case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/compose")
    def compose_case(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        try:
            ensure_v2_mutation_allowed(case)
            resolved_runner.submit_rerun(case_id, "compose")
        except LegacyReadOnlyCaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except V2PackageUnavailableError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/export")
    def export_case(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        try:
            ensure_v2_mutation_allowed(case)
            resolved_runner.submit_rerun(case_id, "export")
        except LegacyReadOnlyCaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except V2PackageUnavailableError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/fork-v2-from-source")
    def fork_case_v2_from_source(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        try:
            forked = fork_v2_case_from_source(resolved_store, resolved_runner, case)
        except (LegacyReadOnlyCaseError, V2PackageUnavailableError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"case": forked.to_api()}

    @app.get("/api/cases/{case_id}/svg-source")
    def get_svg_source(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        path = Path(case.run_root) / "svg" / "semantic.svg"
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="semantic SVG is not available yet")
        return _svg_source_payload(resolved_store, case_id, path)

    @app.patch("/api/cases/{case_id}/svg-source")
    async def update_svg_source(case_id: str, request: Request) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        _reject_legacy_case_mutation(case)
        if case.status in {"analysis_running", "svg_running"}:
            raise HTTPException(status_code=409, detail="cannot edit SVG while the case is running")
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="SVG payload must be an object")
        svg_source = payload.get("svg")
        if not isinstance(svg_source, str):
            raise HTTPException(status_code=400, detail="SVG payload field 'svg' must be a string")
        _validate_svg_source(svg_source)
        path = Path(case.run_root) / "svg" / "semantic.svg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg_source.strip() + "\n", encoding="utf-8")
        _clear_v2_run_package_outputs(case, "export_outputs")
        resolved_store.register_artifact(case_id, label="semantic_svg", path=path, media_type="image/svg+xml")
        resolved_store.update_case_status(
            case_id,
            status="completed",
            phase="reconstruction",
            stage="svg_edit",
            stale_from_stage="export",
        )
        _refresh_batch_status_from_cases(resolved_store, case.batch_id)
        return _svg_source_payload(resolved_store, case_id, path)

    @app.patch("/api/cases/{case_id}/asset-draft")
    async def update_asset_draft(case_id: str, request: Request) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        _reject_legacy_case_mutation(case)
        plan = await request.json()
        if not isinstance(plan, dict):
            raise HTTPException(status_code=400, detail="asset draft payload must be an object")
        validated = validate_asset_plan(plan)
        path = write_asset_draft(case.run_root, validated)
        resolved_store.register_artifact(case_id, label="asset_draft", path=path, media_type="application/json")
        resolved_store.update_case_status(
            case_id,
            status="assets_review",
            phase="analysis",
            stage="asset_draft",
            stale_from_stage="svg",
        )
        return {"asset_plan": validated}

    @app.post("/api/cases/{case_id}/asset-processing")
    async def process_asset_elements(case_id: str, request: Request) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        _reject_legacy_case_mutation(case)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="asset processing payload must be an object")
        raw_ids = payload.get("asset_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise HTTPException(status_code=400, detail="asset_ids must be a non-empty list")
        plan = payload.get("asset_plan")
        if plan is None:
            plan = read_asset_draft(case.run_root)
        if not isinstance(plan, dict):
            raise HTTPException(status_code=400, detail="asset_plan must be an object")
        cfg = load_drawai_config(case.config_path, validate_input_exists=False)
        rmbg_config = cfg.asset_materialization.rmbg
        rmbg = app.state.rmbg_client or RemoteRmbgClient((rmbg_config.base_url or resolved_settings.rmbg_base_url).rstrip("/"))
        try:
            processed = process_asset_plan_elements(
                case.run_root,
                plan,
                [str(asset_id) for asset_id in raw_ids],
                figure_image_path=_case_figure_path(case),
                rmbg_client=rmbg,
                rmbg_timeout_s=rmbg_config.timeout_seconds,
                rmbg_model_path=rmbg_config.model_path,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        path = write_asset_draft(case.run_root, processed["asset_plan"])
        resolved_store.register_artifact(case_id, label="asset_draft", path=path, media_type="application/json")
        resolved_store.update_case_status(
            case_id,
            status="assets_review",
            phase="analysis",
            stage="asset_processing",
            stale_from_stage="svg",
        )
        assets_with_urls = [
            {**asset, "url": _case_file_url(case_id, str(asset["relative_path"]))}
            for asset in processed["processed_assets"]
        ]
        return {"asset_plan": processed["asset_plan"], "processed_assets": assets_with_urls}

    @app.post("/api/cases/{case_id}/approve-assets")
    async def approve_assets(case_id: str, request: Request) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        _reject_legacy_case_mutation(case)
        payload = await _optional_json(request)
        run_svg = _as_bool(payload.get("run_svg")) if payload else False
        try:
            plan = resolved_runner.approve_case(case_id, run_svg=run_svg)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"asset_plan": plan, "case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/run-stage")
    async def run_stage(case_id: str, request: Request) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        payload = await request.json()
        stage = str(payload.get("stage") or "")
        node_id = str(payload.get("node_id") or "").strip()
        accepted_stages = {
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
        }
        if stage not in accepted_stages:
            raise HTTPException(status_code=400, detail="stage is not supported")
        try:
            if node_id and _case_has_workflow_node_runs(case):
                resolved_runner.submit_workflow_rerun(case_id, node_id)
            else:
                _reject_legacy_case_mutation(case)
                resolved_runner.submit_rerun(case_id, stage)  # type: ignore[arg-type]
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/cancel")
    def cancel_case(case_id: str) -> dict[str, Any]:
        _get_case_or_404(resolved_store, case_id)
        resolved_runner.cancel_case(case_id)
        return {"case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/retry")
    def retry_case(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        _reject_legacy_case_mutation(case)
        resolved_runner.submit_rerun(case_id, "analysis")
        return {"case": resolved_store.get_case(case_id).to_api()}

    @app.get("/api/artifacts/{artifact_token}")
    def get_artifact(artifact_token: str) -> FileResponse:
        try:
            artifact = resolved_store.resolve_artifact(artifact_token)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        path = Path(artifact.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="artifact file is missing")
        return FileResponse(path, media_type=artifact.media_type, filename=path.name)

    return app


def _slide_template_gallery_root() -> Path:
    configured = str(os.environ.get("DRAWAI_SLIDE_TEMPLATE_GALLERY_DIR") or "").strip()
    root = Path(configured).expanduser() if configured else SLIDE_TEMPLATE_GALLERY_DEFAULT_DIR
    return root.resolve(strict=False)


def _slide_template_gallery_payload() -> dict[str, Any]:
    root = _slide_template_gallery_root()
    summary_path = root / "summary.json"
    if not summary_path.exists() or not summary_path.is_file():
        return {
            "schema": SLIDE_TEMPLATE_GALLERY_SCHEMA,
            "status": "missing",
            "output_dir": str(root),
            "count": 0,
            "templates": [],
            "contact_sheet_url": "",
            "summary_url": "",
            "message": "template gallery summary.json is not available yet",
        }
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"template gallery summary is invalid: {exc}") from exc

    templates = [
        _slide_template_gallery_card(root, template, index=index)
        for index, template in enumerate(summary.get("templates") or [], start=1)
        if isinstance(template, Mapping)
    ]
    return {
        "schema": SLIDE_TEMPLATE_GALLERY_SCHEMA,
        "status": str(summary.get("status") or "ok"),
        "output_dir": str(root),
        "user_prompt": str(summary.get("user_prompt") or ""),
        "template_count": int(summary.get("template_count") or len(templates)),
        "pages_per_template": int(summary.get("pages_per_template") or 0),
        "count": len(templates),
        "templates": templates,
        "contact_sheet_url": _slide_template_gallery_file_url(root, summary.get("contact_sheet_path") or root / "contact_sheet.jpg"),
        "summary_url": _slide_template_gallery_file_url(root, summary_path),
        "summary_md_url": _slide_template_gallery_file_url(root, root / "summary.md"),
    }


def _slide_template_gallery_card(root: Path, template: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    template_id = str(template.get("template_id") or "").strip()
    template_dir = Path(str(template.get("template_dir") or root / f"{index:02d}_{template_id}")).expanduser().resolve(strict=False)
    pages = [
        _slide_template_gallery_page(root, page)
        for page in template.get("pages") or []
        if isinstance(page, Mapping)
    ]
    ok_count = len([page for page in pages if page.get("status") == "ok"])
    return {
        "template_id": template_id,
        "template_name": str(template.get("template_name") or template_id),
        "category": str(template.get("category") or ""),
        "reason": str(template.get("reason") or ""),
        "template_dir": str(template_dir),
        "page_count": len(pages),
        "ok_count": ok_count,
        "status": "ok" if pages and ok_count == len(pages) else "partial",
        "contact_sheet_url": _slide_template_gallery_file_url(
            root,
            template.get("contact_sheet_path") or template_dir / "contact_sheet.jpg",
        ),
        "pages": pages,
    }


def _slide_template_gallery_page(root: Path, page: Mapping[str, Any]) -> dict[str, Any]:
    image_path = page.get("image_path") or ""
    prompt_path = page.get("prompt_path") or ""
    payload_path = page.get("payload_path") or ""
    case_dir = page.get("case_dir") or ""
    record_path = Path(str(case_dir)).expanduser().resolve(strict=False) / "record.json" if case_dir else ""
    return {
        "page_id": str(page.get("page_id") or ""),
        "page_title": str(page.get("page_title") or ""),
        "page_index": int(page.get("page_index") or 0),
        "page_count": int(page.get("page_count") or 0),
        "status": str(page.get("status") or ""),
        "image_url": _slide_template_gallery_file_url(root, image_path),
        "prompt_url": _slide_template_gallery_file_url(root, prompt_path),
        "payload_url": _slide_template_gallery_file_url(root, payload_path),
        "record_url": _slide_template_gallery_file_url(root, record_path),
    }


def _slide_template_gallery_file_url(root: Path, raw_path: object) -> str:
    if not raw_path:
        return ""
    path = Path(str(raw_path)).expanduser().resolve(strict=False)
    try:
        relative = path.relative_to(root)
    except ValueError:
        return ""
    if path.suffix.lower() not in SLIDE_TEMPLATE_GALLERY_FILE_EXTENSIONS:
        return ""
    return "/api/slide-template-gallery/files/" + urllib.parse.quote(relative.as_posix())


def _resolve_slide_template_gallery_file(root: Path, relative_path: str) -> Path:
    if not relative_path:
        raise HTTPException(status_code=404, detail="gallery file is missing")
    posix = PurePosixPath(relative_path)
    if posix.is_absolute() or ".." in posix.parts:
        raise HTTPException(status_code=400, detail="invalid gallery file path")
    path = (root / Path(*posix.parts)).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid gallery file path") from exc
    if path.suffix.lower() not in SLIDE_TEMPLATE_GALLERY_FILE_EXTENSIONS:
        raise HTTPException(status_code=404, detail="unsupported gallery file type")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="gallery file is missing")
    return path


def settings_from_env() -> WorkbenchSettings:
    workspace = Path(os.environ.get("DRAWAI_WORKBENCH_WORKSPACE", ".local/workbench")).expanduser().resolve(strict=False)
    default_config = Path(os.environ.get("DRAWAI_WORKBENCH_DEFAULT_CONFIG", "configs/drawai/config.yaml")).expanduser().resolve(strict=False)
    return WorkbenchSettings(
        workspace=workspace,
        default_config=default_config,
        cloud_mode=_as_bool(os.environ.get("DRAWAI_WORKBENCH_CLOUD_MODE")),
        max_concurrent_cases=int(os.environ.get("DRAWAI_WORKBENCH_MAX_CONCURRENT_CASES", "10")),
        sam_concurrency=int(os.environ.get("DRAWAI_WORKBENCH_SAM_CONCURRENCY", "1")),
        ocr_concurrency=int(os.environ.get("DRAWAI_WORKBENCH_OCR_CONCURRENCY", "1")),
        codex_concurrency=int(os.environ.get("DRAWAI_WORKBENCH_CODEX_CONCURRENCY", "5")),
        rmbg_concurrency=int(os.environ.get("DRAWAI_WORKBENCH_RMBG_CONCURRENCY", "1")),
        export_concurrency=int(os.environ.get("DRAWAI_WORKBENCH_EXPORT_CONCURRENCY", "1")),
        sam3_base_url=os.environ.get("DRAWAI_SAM3_BASE_URL", "http://127.0.0.1:18080"),
        ocr_base_url=os.environ.get("DRAWAI_OCR_BASE_URL", "http://127.0.0.1:18080"),
        rmbg_base_url=os.environ.get("DRAWAI_RMBG_BASE_URL", "http://127.0.0.1:18080"),
        ocr_timeout_seconds=_optional_positive_float_env("DRAWAI_WORKBENCH_OCR_TIMEOUT_SECONDS"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the DrawAI Workbench FastAPI server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8890)
    parser.add_argument("--workspace", default=os.environ.get("DRAWAI_WORKBENCH_WORKSPACE", ".local/workbench"))
    parser.add_argument("--config", default=os.environ.get("DRAWAI_WORKBENCH_DEFAULT_CONFIG", "configs/drawai/config.yaml"))
    args = parser.parse_args(argv)
    os.environ["DRAWAI_WORKBENCH_WORKSPACE"] = args.workspace
    os.environ["DRAWAI_WORKBENCH_DEFAULT_CONFIG"] = args.config
    import uvicorn

    uvicorn.run(create_app(settings_from_env()), host=args.host, port=args.port)
    return 0


async def _parse_batch_request(request: Request) -> tuple[dict[str, Any], list[Any]]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        upload_files = [*form.getlist("files"), *form.getlist("file")]
        generated_image_urls = [
            str(value)
            for field in GENERATED_IMAGE_URL_FIELDS
            for value in form.getlist(field)
            if str(value).strip()
        ]
        payload: dict[str, Any] = {
            key: value
            for key, value in form.items()
            if key not in {"files", "file", *GENERATED_IMAGE_URL_FIELDS}
        }
        if generated_image_urls:
            payload["generated_image_urls"] = generated_image_urls
        return payload, upload_files
    payload = await _optional_json(request)
    return payload, []


async def _optional_json(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        return {}
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON payload must be an object")
    return payload


def _reject_legacy_case_mutation(case: CaseRecord) -> None:
    if classify_run_root(case.run_root).mode == "legacy_readonly":
        raise HTTPException(status_code=409, detail="legacy_readonly_case")


def _case_has_workflow_node_runs(case: CaseRecord) -> bool:
    return any((Path(case.run_root) / "nodes").glob("*/runs/*/node_run.json"))


def _mark_asset_outputs_stale(store: WorkbenchStore, case_id: str) -> None:
    case = store.get_case(case_id)
    store.update_case_status(
        case_id,
        status="assets_review",
        phase="analysis",
        stage="asset_package_updated",
        stale_from_stage="compose_svg",
    )
    _refresh_batch_status_from_cases(store, case.batch_id)


def _mark_asset_outputs_stale_if_failed_package(
    store: WorkbenchStore,
    case_id: str,
    element_id: str,
    processor: str,
) -> None:
    case = store.get_case(case_id)
    try:
        package_path = element_dir(case.run_root, element_id) / "asset_package.json"
    except ValueError:
        return
    if not package_path.is_file():
        return
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    if (
        isinstance(payload, dict)
        and payload.get("status") == "failed"
        and payload.get("processor_type") == processor
    ):
        _mark_asset_outputs_stale(store, case_id)


def _clear_v2_run_package_outputs(case: CaseRecord, *keys: str) -> None:
    if classify_run_root(case.run_root).mode != "v2":
        return
    package_path = Path(case.run_root) / "drawai_package.json"
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("v2 run package must be a JSON object")
    changed = False
    for key in keys:
        if key in payload:
            payload.pop(key, None)
            changed = True
    if changed:
        write_json(package_path, payload)


def _asset_processor_providers(
    case: CaseRecord,
    processor: str,
    settings: WorkbenchSettings,
    rmbg_client: Any,
    *,
    processor_setting: ProcessorSetting | None = None,
) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    if processor == "crop_nobg":
        if rmbg_client is not None:
            providers["rmbg_client"] = rmbg_client
        else:
            cfg = load_drawai_config(case.config_path, validate_input_exists=False)
            base_url = cfg.asset_materialization.rmbg.base_url or settings.rmbg_base_url
            providers["rmbg_client"] = RemoteRmbgClient(base_url.rstrip("/"))
    if (
        processor == "image_generate"
        and processor_setting is not None
        and processor_setting.driver_id == "openai_images_api"
    ):
        preset = _processor_api_preset(settings.workspace, processor, processor_setting)
        providers["image_generate"] = _images_api_generate_provider(preset)
    if (
        processor == "image_edit"
        and processor_setting is not None
        and processor_setting.driver_id == "openai_images_api"
    ):
        preset = _processor_api_preset(settings.workspace, processor, processor_setting)
        providers["image_edit"] = _images_api_edit_provider(preset)
    return providers


def _processor_api_preset(
    workspace: str | Path,
    processor: str,
    processor_setting: ProcessorSetting,
) -> ApiPreset:
    preset = api_preset_by_id(read_workbench_api_presets(workspace), processor_setting.api_preset_id)
    if preset is None:
        raise ValueError(f"API preset not found for {processor}: {processor_setting.api_preset_id or '<empty>'}")
    return preset


def _images_api_generate_provider(preset: ApiPreset) -> Callable[..., Mapping[str, Any]]:
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
        request_payload = _images_api_generation_payload(preset, prompt, runtime_config=runtime_config)
        response_payload = _call_image_generation_upstream(
            request_payload,
            api_url=_image_generation_api_url(preset.base_url),
            api_key=_api_preset_key(preset),
        )
        image_payload = _materialize_first_images_api_image(
            response_payload,
            output_dir=output_path,
            output_stem=output_stem,
        )
        return {
            "schema": "drawai.workbench.images_api_provider_result.v1",
            "runner": "images_api",
            "task_name": task_name,
            "operation": "generate",
            "provider": preset.id,
            "model": preset.model,
            "prompt": prompt,
            "output_dir": str(output_path),
            "images": [image_payload],
            "upstream": _images_api_response_metadata(response_payload),
        }

    return generate


def _images_api_edit_provider(preset: ApiPreset) -> Callable[..., Mapping[str, Any]]:
    return _shared_images_api_edit_provider(preset)


def _images_api_generation_payload(
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
) -> dict[str, Any]:
    for index, record in enumerate(_image_generation_payload_records(payload), start=1):
        image_bytes, suffix = _images_api_record_bytes(record)
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


def _images_api_record_bytes(record: Mapping[str, Any]) -> tuple[bytes, str]:
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
        return _read_generated_image_value(raw_url)
    return b"", ".png"


def _images_api_response_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    records = _image_generation_payload_records(payload)
    return {
        "created": payload.get("created"),
        "record_count": len(records),
        "statuses": [
            str(record.get("status") or record.get("state") or "")
            for record in records
            if record.get("status") or record.get("state")
        ],
        "revised_prompts": [
            str(record.get("revised_prompt"))
            for record in records
            if record.get("revised_prompt")
        ],
    }


async def _collect_sources(
    store: WorkbenchStore,
    batch_id: str,
    *,
    input_mode: str,
    local_dir: Any,
    upload_files: list[Any],
    generated_image_urls: list[str],
) -> list[Path]:
    if input_mode == "local_dir":
        if not local_dir:
            raise HTTPException(status_code=400, detail="local image path or directory is required")
        root = Path(str(local_dir)).expanduser().resolve(strict=False)
        if root.is_file():
            if root.suffix.lower() not in IMAGE_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"local path is not a supported image file: {root}")
            sources = [root]
        elif root.is_dir():
            sources = sorted(path for path in root.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS and path.is_file())
        else:
            raise HTTPException(status_code=400, detail=f"local path does not exist: {root}")
    else:
        upload_root = store.uploads_root / batch_id
        upload_root.mkdir(parents=True, exist_ok=True)
        sources = []
        for upload in upload_files:
            filename = str(getattr(upload, "filename", "") or "upload.png")
            suffix = Path(filename).suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                target = _unique_upload_path(upload_root / _safe_upload_relative_path(filename))
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as handle:
                    shutil.copyfileobj(upload.file, handle)
                sources.append(target)
                continue
            if suffix not in ARCHIVE_EXTENSIONS:
                continue
            target = _unique_upload_path(upload_root / _safe_filename(filename))
            with target.open("wb") as handle:
                shutil.copyfileobj(upload.file, handle)
            sources.extend(_extract_zip_image_sources(target, upload_root / f"{target.stem}_extracted"))
        sources.extend(_materialize_generated_image_urls(generated_image_urls, upload_root))
    if not sources:
        raise HTTPException(status_code=400, detail="no supported image files found")
    return sources


def _materialize_generated_image_urls(values: list[str], upload_root: Path) -> list[Path]:
    sources: list[Path] = []
    for index, value in enumerate(values, start=1):
        image_bytes, suffix = _read_generated_image_value(value)
        target = _unique_upload_path(upload_root / f"generated-{index:03d}{suffix}")
        target.write_bytes(image_bytes)
        sources.append(target)
    return sources


def _read_generated_image_value(value: str) -> tuple[bytes, str]:
    text = value.strip()
    if text.startswith("data:"):
        return _read_data_image_url(text)
    return _download_generated_image_url(text)


def _read_data_image_url(value: str) -> tuple[bytes, str]:
    match = re.fullmatch(r"data:(image/[A-Za-z0-9.+-]+);base64,(.*)", value, flags=re.DOTALL)
    if not match:
        raise HTTPException(status_code=400, detail="generated image data URL must be an image base64 data URL")
    mime_type = match.group(1).lower()
    suffix = _image_suffix_from_mime(mime_type)
    encoded = "".join(match.group(2).split())
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="generated image data URL is not valid base64") from exc
    if len(image_bytes) > MAX_GENERATED_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="generated image is too large")
    return image_bytes, suffix


def _download_generated_image_url(value: str) -> tuple[bytes, str]:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="generated image URL must use http, https, or data")
    request = urllib.request.Request(value, headers={"User-Agent": "DrawAI Workbench"})
    try:
        with urlopen_external(request, timeout=600) as response:
            image_bytes = response.read(MAX_GENERATED_IMAGE_BYTES + 1)
            content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=400, detail=f"could not download generated image: {exc}") from exc
    if len(image_bytes) > MAX_GENERATED_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="generated image is too large")
    suffix = _image_suffix_from_mime(content_type) if content_type.startswith("image/") else Path(parsed.path).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"generated image URL is not a supported image type: {content_type or suffix}")
    return image_bytes, suffix


def _image_suffix_from_mime(mime_type: str) -> str:
    suffix = mimetypes.guess_extension(mime_type) or ""
    if suffix in {".jpe", ".jfif"}:
        suffix = ".jpg"
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"generated image type is not supported: {mime_type}")
    return suffix


def _string_list_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise HTTPException(status_code=400, detail="image URL list must be a JSON array")
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in text.splitlines() if item.strip()]
    return [str(value).strip()]


def _get_batch_or_404(store: WorkbenchStore, batch_id: str):
    try:
        return store.get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="batch not found") from exc


def _batch_detail_payload(store: WorkbenchStore, batch_id: str) -> dict[str, Any]:
    batch = store.get_batch(batch_id)
    return {
        "batch": batch.to_api(case_counts=store.case_counts(batch_id)),
        "cases": [_case_to_api_with_preview(store, case) for case in store.list_cases(batch_id)],
    }


def _completed_batch_pptx_paths(store: WorkbenchStore, batch_id: str) -> list[Path]:
    cases = store.list_cases(batch_id)
    if not cases:
        raise HTTPException(status_code=400, detail="task has no cases to download")
    incomplete = [case.name for case in cases if case.status != "completed"]
    if incomplete:
        raise HTTPException(status_code=409, detail=f"all cases must be completed before batch download: {', '.join(incomplete[:3])}")
    pptx_paths = [_case_pptx_path(store, case) for case in cases]
    missing = [case.name for case, path in zip(cases, pptx_paths) if path is None]
    if missing:
        raise HTTPException(status_code=409, detail=f"some completed cases do not have PPTX exports yet: {', '.join(missing[:3])}")
    return [path for path in pptx_paths if path is not None]


def _case_pptx_path(store: WorkbenchStore, case: CaseRecord) -> Path | None:
    for artifact in reversed(store.list_artifacts(case.case_id)):
        if artifact.label == "pptx":
            path = Path(artifact.path).expanduser().resolve(strict=False)
            if path.is_file():
                return path
    fallback = Path(case.run_root) / "svg_to_ppt" / "semantic.svg_to_ppt.pptx"
    if fallback.is_file():
        return fallback
    return None


def _merge_pptx_files(source_paths: list[Path], output_path: Path) -> None:
    if not source_paths:
        raise HTTPException(status_code=400, detail="no PPTX files to merge")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if len(source_paths) == 1:
        shutil.copy2(source_paths[0], output_path)
        return
    package_parts: dict[str, bytes] = {}
    with zipfile.ZipFile(source_paths[0], "r") as base_package:
        package_parts = {name: base_package.read(name) for name in base_package.namelist()}
        presentation = etree.fromstring(package_parts["ppt/presentation.xml"])
        presentation_rels = etree.fromstring(package_parts["ppt/_rels/presentation.xml.rels"])
        content_types = etree.fromstring(package_parts["[Content_Types].xml"])
        base_layout_target = _first_slide_layout_target(base_package)

    slide_id_list = presentation.find(f"{{{PPT_NS}}}sldIdLst")
    if slide_id_list is None:
        slide_id_list = etree.SubElement(presentation, f"{{{PPT_NS}}}sldIdLst")
    used_parts = set(package_parts)
    next_slide_index = _next_package_slide_index(used_parts)
    next_slide_id = _next_presentation_slide_id(slide_id_list)
    next_rel_id = _next_relationship_id(presentation_rels)
    for source_path in source_paths[1:]:
        with zipfile.ZipFile(source_path, "r") as source_package:
            source_content_types = etree.fromstring(source_package.read("[Content_Types].xml"))
            for source_slide in _ordered_slide_parts(source_package):
                slide_part = f"ppt/slides/slide{next_slide_index}.xml"
                source_rels = _pptx_part_rels_path(source_slide)
                target_rels = _pptx_part_rels_path(slide_part)
                package_parts[slide_part] = source_package.read(source_slide)
                used_parts.add(slide_part)
                _copy_part_content_type(source_content_types, content_types, source_slide, slide_part)
                if source_rels in source_package.namelist():
                    package_parts[target_rels] = _copied_slide_relationships(
                        source_package,
                        source_content_types,
                        content_types,
                        source_slide,
                        slide_part,
                        package_parts,
                        used_parts,
                        base_layout_target,
                    )
                    used_parts.add(target_rels)
                rel_id = f"rId{next_rel_id}"
                etree.SubElement(
                    presentation_rels,
                    f"{{{PKG_REL_NS}}}Relationship",
                    Id=rel_id,
                    Type=PPT_SLIDE_REL_TYPE,
                    Target=f"slides/slide{next_slide_index}.xml",
                )
                etree.SubElement(
                    slide_id_list,
                    f"{{{PPT_NS}}}sldId",
                    id=str(next_slide_id),
                    attrib={f"{{{PPT_REL_NS}}}id": rel_id},
                )
                _ensure_slide_content_type(content_types, slide_part)
                next_slide_index += 1
                next_slide_id += 1
                next_rel_id += 1
    package_parts["ppt/presentation.xml"] = _xml_bytes(presentation)
    package_parts["ppt/_rels/presentation.xml.rels"] = _xml_bytes(presentation_rels)
    package_parts["[Content_Types].xml"] = _xml_bytes(content_types)
    tmp_path = output_path.with_suffix(".tmp.pptx")
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as output_package:
        for name, data in package_parts.items():
            output_package.writestr(name, data)
    tmp_path.replace(output_path)


def _ordered_slide_parts(package: zipfile.ZipFile) -> list[str]:
    presentation = etree.fromstring(package.read("ppt/presentation.xml"))
    presentation_rels = etree.fromstring(package.read("ppt/_rels/presentation.xml.rels"))
    rel_targets = {
        rel.get("Id"): rel.get("Target")
        for rel in presentation_rels.findall(f"{{{PKG_REL_NS}}}Relationship")
        if rel.get("Type") == PPT_SLIDE_REL_TYPE and rel.get("Target")
    }
    slide_id_list = presentation.find(f"{{{PPT_NS}}}sldIdLst")
    if slide_id_list is None:
        return []
    slide_parts: list[str] = []
    for slide_id in slide_id_list.findall(f"{{{PPT_NS}}}sldId"):
        rel_id = slide_id.get(f"{{{PPT_REL_NS}}}id")
        target = rel_targets.get(rel_id)
        if target:
            slide_parts.append(_normalize_package_part(posixpath.join("ppt", target)))
    return slide_parts


def _copied_slide_relationships(
    source_package: zipfile.ZipFile,
    source_content_types: etree._Element,
    target_content_types: etree._Element,
    source_slide: str,
    target_slide: str,
    package_parts: dict[str, bytes],
    used_parts: set[str],
    base_layout_target: str,
) -> bytes:
    source_rels = etree.fromstring(source_package.read(_pptx_part_rels_path(source_slide)))
    for rel in source_rels.findall(f"{{{PKG_REL_NS}}}Relationship"):
        target = rel.get("Target")
        if not target or rel.get("TargetMode") == "External":
            continue
        if rel.get("Type") == PPT_SLIDE_LAYOUT_REL_TYPE:
            rel.set("Target", base_layout_target)
            continue
        source_part = _resolve_package_relationship_target(source_slide, target)
        if source_part not in source_package.namelist():
            continue
        target_part = _unique_package_part(used_parts, source_part)
        _copy_pptx_part_with_relationships(
            source_package,
            source_content_types,
            target_content_types,
            source_part,
            target_part,
            package_parts,
            used_parts,
        )
        rel.set("Target", _relative_package_target(target_slide, target_part))
    return _xml_bytes(source_rels)


def _copy_pptx_part_with_relationships(
    source_package: zipfile.ZipFile,
    source_content_types: etree._Element,
    target_content_types: etree._Element,
    source_part: str,
    target_part: str,
    package_parts: dict[str, bytes],
    used_parts: set[str],
) -> None:
    package_parts[target_part] = source_package.read(source_part)
    used_parts.add(target_part)
    _copy_part_content_type(source_content_types, target_content_types, source_part, target_part)
    source_rels_path = _pptx_part_rels_path(source_part)
    if source_rels_path not in source_package.namelist():
        return
    target_rels_path = _pptx_part_rels_path(target_part)
    rels = etree.fromstring(source_package.read(source_rels_path))
    for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship"):
        target = rel.get("Target")
        if not target or rel.get("TargetMode") == "External":
            continue
        source_child = _resolve_package_relationship_target(source_part, target)
        if source_child not in source_package.namelist():
            continue
        target_child = _unique_package_part(used_parts, source_child)
        _copy_pptx_part_with_relationships(
            source_package,
            source_content_types,
            target_content_types,
            source_child,
            target_child,
            package_parts,
            used_parts,
        )
        rel.set("Target", _relative_package_target(target_part, target_child))
    package_parts[target_rels_path] = _xml_bytes(rels)
    used_parts.add(target_rels_path)


def _first_slide_layout_target(package: zipfile.ZipFile) -> str:
    first_slide = _ordered_slide_parts(package)[0]
    rels_path = _pptx_part_rels_path(first_slide)
    if rels_path not in package.namelist():
        return "../slideLayouts/slideLayout1.xml"
    rels = etree.fromstring(package.read(rels_path))
    for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship"):
        if rel.get("Type") == PPT_SLIDE_LAYOUT_REL_TYPE and rel.get("Target"):
            return str(rel.get("Target"))
    return "../slideLayouts/slideLayout1.xml"


def _next_package_slide_index(parts: set[str]) -> int:
    indexes = []
    for part in parts:
        match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", part)
        if match:
            indexes.append(int(match.group(1)))
    return max(indexes, default=0) + 1


def _next_presentation_slide_id(slide_id_list: etree._Element) -> int:
    values = []
    for slide_id in slide_id_list.findall(f"{{{PPT_NS}}}sldId"):
        raw = slide_id.get("id")
        if raw and raw.isdigit():
            values.append(int(raw))
    return max(values, default=255) + 1


def _next_relationship_id(rels: etree._Element) -> int:
    values = []
    for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship"):
        raw = str(rel.get("Id") or "")
        if raw.startswith("rId") and raw[3:].isdigit():
            values.append(int(raw[3:]))
    return max(values, default=0) + 1


def _ensure_slide_content_type(content_types: etree._Element, slide_part: str) -> None:
    part_name = f"/{slide_part}"
    for override in content_types.findall(f"{{{CONTENT_TYPES_NS}}}Override"):
        if override.get("PartName") == part_name:
            return
    etree.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Override",
        PartName=part_name,
        ContentType=PPT_SLIDE_CONTENT_TYPE,
    )


def _copy_part_content_type(
    source_content_types: etree._Element,
    target_content_types: etree._Element,
    source_part: str,
    target_part: str,
) -> None:
    source_part_name = f"/{source_part}"
    target_part_name = f"/{target_part}"
    for override in source_content_types.findall(f"{{{CONTENT_TYPES_NS}}}Override"):
        if override.get("PartName") == source_part_name and override.get("ContentType"):
            _ensure_content_type_override(target_content_types, target_part_name, str(override.get("ContentType")))
            return
    extension = Path(source_part).suffix.lower().lstrip(".")
    if not extension:
        return
    for default in source_content_types.findall(f"{{{CONTENT_TYPES_NS}}}Default"):
        if default.get("Extension", "").lower() == extension and default.get("ContentType"):
            _ensure_content_type_default(target_content_types, extension, str(default.get("ContentType")))
            return


def _ensure_content_type_override(content_types: etree._Element, part_name: str, content_type: str) -> None:
    for override in content_types.findall(f"{{{CONTENT_TYPES_NS}}}Override"):
        if override.get("PartName") == part_name:
            override.set("ContentType", content_type)
            return
    etree.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Override",
        PartName=part_name,
        ContentType=content_type,
    )


def _ensure_content_type_default(content_types: etree._Element, extension: str, content_type: str) -> None:
    for default in content_types.findall(f"{{{CONTENT_TYPES_NS}}}Default"):
        if default.get("Extension", "").lower() == extension:
            return
    etree.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Default",
        Extension=extension,
        ContentType=content_type,
    )


def _pptx_part_rels_path(part: str) -> str:
    dirname = posixpath.dirname(part)
    basename = posixpath.basename(part)
    return f"{dirname}/_rels/{basename}.rels"


def _resolve_package_relationship_target(source_part: str, target: str) -> str:
    return _normalize_package_part(posixpath.join(posixpath.dirname(source_part), target))


def _relative_package_target(source_part: str, target_part: str) -> str:
    return posixpath.relpath(target_part, start=posixpath.dirname(source_part))


def _normalize_package_part(part: str) -> str:
    return posixpath.normpath(part).lstrip("/")


def _unique_package_part(used_parts: set[str], source_part: str) -> str:
    normalized = _normalize_package_part(source_part)
    if normalized not in used_parts:
        return normalized
    dirname = posixpath.dirname(normalized)
    stem = Path(posixpath.basename(normalized)).stem or "part"
    suffix = Path(posixpath.basename(normalized)).suffix
    index = 2
    while True:
        candidate = f"{dirname}/{stem}_{index}{suffix}" if dirname else f"{stem}_{index}{suffix}"
        if candidate not in used_parts:
            return candidate
        index += 1


def _xml_bytes(element: etree._Element) -> bytes:
    return etree.tostring(element, xml_declaration=True, encoding="UTF-8", standalone=False)


def _active_cases(cases: list[CaseRecord]) -> list[CaseRecord]:
    return [case for case in cases if case.status in {"analysis_running", "svg_running"}]


def _case_has_asset_draft(case: CaseRecord) -> bool:
    return (Path(case.run_root) / "reports" / "workbench" / "asset_draft.json").is_file()


def _get_case_or_404(store: WorkbenchStore, case_id: str):
    try:
        return store.get_case(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc


def _svg_source_payload(store: WorkbenchStore, case_id: str, path: Path) -> dict[str, Any]:
    stat = path.stat()
    artifact = _latest_registered_artifact(store, case_id, label="semantic_svg", path=path)
    if artifact is None:
        artifact = store.register_artifact(case_id, label="semantic_svg", path=path, media_type="image/svg+xml")
    return {
        "svg": path.read_text(encoding="utf-8"),
        "size_bytes": stat.st_size,
        "updated_at": int(stat.st_mtime),
        "artifact": artifact.to_api(),
        "case": store.get_case(case_id).to_api(),
    }


def _latest_registered_artifact(store: WorkbenchStore, case_id: str, *, label: str, path: Path):
    resolved_path = str(path.expanduser().resolve(strict=False))
    return next(
        (
            artifact
            for artifact in reversed(store.list_artifacts(case_id))
            if artifact.label == label and str(Path(artifact.path).expanduser().resolve(strict=False)) == resolved_path
        ),
        None,
    )


def _validate_svg_source(svg_source: str) -> None:
    if not svg_source.strip():
        raise HTTPException(status_code=400, detail="SVG source cannot be empty")
    if len(svg_source.encode("utf-8")) > MAX_SVG_SOURCE_BYTES:
        raise HTTPException(status_code=400, detail="SVG source is too large")
    upper_source = svg_source.upper()
    if "<!DOCTYPE" in upper_source or "<!ENTITY" in upper_source:
        raise HTTPException(status_code=400, detail="SVG source cannot contain DOCTYPE or ENTITY declarations")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    try:
        root = etree.fromstring(svg_source.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"SVG source is not well-formed XML: {exc}") from exc
    if _local_xml_name(root.tag) != "svg" or _xml_namespace(root.tag) != SVG_NS:
        raise HTTPException(status_code=400, detail="SVG source root must be <svg xmlns=\"http://www.w3.org/2000/svg\">")
    for element in root.iter():
        if _local_xml_name(element.tag) in UNSAFE_SVG_TAGS:
            raise HTTPException(status_code=400, detail="SVG source contains unsupported active content")
        for attr_name, attr_value in element.attrib.items():
            local_attr = _local_xml_name(attr_name).lower()
            if local_attr.startswith("on"):
                raise HTTPException(status_code=400, detail="SVG source cannot contain event handler attributes")
            if local_attr in {"href", "src"} and str(attr_value).strip().lower().startswith("javascript:"):
                raise HTTPException(status_code=400, detail="SVG source cannot contain javascript URLs")


def _local_xml_name(value: Any) -> str:
    text = str(value)
    return text.rsplit("}", 1)[-1] if text.startswith("{") else text


def _xml_namespace(value: Any) -> str:
    text = str(value)
    return text[1:].split("}", 1)[0] if text.startswith("{") and "}" in text else ""


def _refresh_batch_status_from_cases(store: WorkbenchStore, batch_id: str) -> None:
    cases = store.list_cases(batch_id)
    statuses = {case.status for case in cases}
    if any(status in statuses for status in {"queued", "analysis_running", "svg_running"}):
        store.update_batch_status(batch_id, "running")
    elif statuses == {"completed"}:
        store.update_batch_status(batch_id, "completed")
    elif "assets_review" in statuses:
        store.update_batch_status(batch_id, "waiting_review")
    elif "failed" in statuses:
        failed_case = next((case for case in cases if case.status == "failed" and case.error_message), None)
        store.update_batch_status(batch_id, "failed", error_message=failed_case.error_message if failed_case else "")
    elif "canceled" in statuses:
        store.update_batch_status(batch_id, "canceled")


def _normalize_image_generation_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {key: value for key, value in payload.items() if key in IMAGEGEN_ALLOWED_FIELDS}
    prompt = str(normalized.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    normalized["prompt"] = prompt
    normalized["model"] = str(normalized.get("model") or IMAGEGEN_DEFAULT_MODEL)
    normalized["size"] = str(normalized.get("size") or "1024x1024")
    normalized["quality"] = str(normalized.get("quality") or "auto")
    normalized["background"] = str(normalized.get("background") or "auto")
    normalized["moderation"] = str(normalized.get("moderation") or "auto")
    normalized["output_format"] = str(normalized.get("output_format") or "png")
    try:
        n = int(normalized.get("n") or 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="n must be an integer from 1 to 10") from exc
    if n < 1 or n > 10:
        raise HTTPException(status_code=400, detail="n must be an integer from 1 to 10")
    normalized["n"] = n
    if "output_compression" in normalized:
        try:
            compression = int(normalized["output_compression"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="output_compression must be an integer from 0 to 100") from exc
        if compression < 0 or compression > 100:
            raise HTTPException(status_code=400, detail="output_compression must be an integer from 0 to 100")
        normalized["output_compression"] = compression
    if "partial_images" in normalized:
        try:
            partial_images = int(normalized["partial_images"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="partial_images must be an integer from 0 to 3") from exc
        if partial_images < 0 or partial_images > 3:
            raise HTTPException(status_code=400, detail="partial_images must be an integer from 0 to 3")
        normalized["partial_images"] = partial_images
    if "stream" in normalized:
        normalized["stream"] = bool(normalized["stream"])
    source_image_path = _image_generation_source_image_path(normalized)
    if source_image_path:
        normalized["source_image_path"] = source_image_path
        normalized["reference_image_path"] = source_image_path
        normalized.pop("image_path", None)
        normalized.pop("reference_image_paths", None)
    return normalized


def _api_image_generation_payload(normalized_payload: Mapping[str, Any], raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    api_payload = dict(normalized_payload)
    context_payload = codex_imagegen_context_payload(raw_payload)
    if not context_payload:
        return api_payload
    api_payload["prompt"] = build_slide_image_api_generation_prompt(
        merge_codex_imagegen_context(normalized_payload, raw_payload)
    )
    return api_payload


def _normalize_image_edit_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    source_image_path = _image_generation_source_image_path(payload)
    if not source_image_path:
        raise HTTPException(status_code=400, detail="source_image_path is required")
    return {
        "prompt": prompt,
        "source_image_path": source_image_path,
        "model": str(payload.get("model") or "").strip(),
        "size": str(payload.get("size") or "").strip(),
        "quality": str(payload.get("quality") or "").strip(),
        "background": str(payload.get("background") or "").strip(),
        "output_format": str(payload.get("output_format") or "png").strip() or "png",
    }


def _image_generation_source_image_path(payload: Mapping[str, Any]) -> str:
    direct = str(
        payload.get("source_image_path")
        or payload.get("reference_image_path")
        or payload.get("image_path")
        or ""
    ).strip()
    if direct:
        return direct
    reference_paths = payload.get("reference_image_paths")
    if reference_paths is None:
        return ""
    if isinstance(reference_paths, str):
        return reference_paths.strip()
    if not isinstance(reference_paths, Sequence) or isinstance(reference_paths, (bytes, bytearray)):
        raise HTTPException(status_code=400, detail="reference_image_paths must be a string or an array of strings")
    paths = [str(path).strip() for path in reference_paths if str(path).strip()]
    if len(paths) > 1:
        raise HTTPException(status_code=400, detail="only one reference image is supported for Codex image generation")
    return paths[0] if paths else ""


def _image_generation_provider(payload: Mapping[str, Any]) -> str:
    provider = str(payload.get("provider") or payload.get("image_provider") or "api").strip().lower()
    if provider in {"openai", "images", "image-api"}:
        return "api"
    if provider == "codex":
        return "codex"
    if provider and provider != "api":
        raise HTTPException(status_code=400, detail="provider must be api or codex")
    return "api"


def _call_codex_image_generation(
    payload: Mapping[str, Any],
    *,
    store: WorkbenchStore,
    settings: WorkbenchSettings,
) -> dict[str, Any]:
    n = int(payload.get("n") or 1)
    output_root = _codex_imagegen_output_dir(store.workspace, "generations")
    runtime_config = _codex_imagegen_runtime_config(payload, settings=settings)
    source_image_path = _image_generation_source_image_path(payload)
    image_context = bool(source_image_path)
    results: list[CodexImageGenResult] = []
    try:
        for index in range(1, n + 1):
            output_dir = output_root / f"variant-{index:03d}"
            output_dir.mkdir(parents=True, exist_ok=True)
            if source_image_path:
                prompt = _codex_generation_prompt(payload, variant_index=index, variant_count=n)
                results.append(
                    invoke_codex_python_sdk_image_reference_context(
                        source_image_path=source_image_path,
                        prompt=_codex_reference_context_prompt(
                            prompt,
                            source_image_path=source_image_path,
                        ),
                        output_dir=output_dir,
                        task_name="drawai.workbench.imagegen.codex.image_context.v1",
                        output_stem=f"codex-image-context-{index:03d}",
                        runtime_config=runtime_config,
                        isolated_cwd=store.workspace,
                    )
                )
            else:
                prompt = _codex_generation_prompt(payload, variant_index=index, variant_count=n)
                results.append(
                    invoke_codex_python_sdk_imagegen(
                        prompt=prompt,
                        output_dir=output_dir,
                        task_name="drawai.workbench.imagegen.codex.generate.v1",
                        output_stem=f"codex-generated-{index:03d}",
                        runtime_config=runtime_config,
                        isolated_cwd=store.workspace,
                    )
                )
    except CodexPythonSdkImageGenError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _codex_imagegen_response(
        results,
        provider="codex",
        prompt=_codex_generation_prompt(payload, variant_index=1, variant_count=n),
        image_context=image_context,
    )


def _call_codex_image_edit(
    payload: Mapping[str, Any],
    *,
    store: WorkbenchStore,
    settings: WorkbenchSettings,
) -> dict[str, Any]:
    output_dir = _codex_imagegen_output_dir(store.workspace, "edits")
    runtime_config = _codex_imagegen_runtime_config(payload, settings=settings)
    prompt = _codex_edit_prompt(payload)
    try:
        result = invoke_codex_python_sdk_image_edit(
            source_image_path=str(payload["source_image_path"]),
            prompt=prompt,
            output_dir=output_dir,
            task_name="drawai.workbench.imagegen.codex.edit.v1",
            output_stem="codex-edited",
            runtime_config=runtime_config,
            isolated_cwd=store.workspace,
        )
    except CodexPythonSdkImageGenError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _codex_imagegen_response([result], provider="codex", prompt=prompt)


def _codex_imagegen_runtime_config(payload: Mapping[str, Any], *, settings: WorkbenchSettings) -> dict[str, Any]:
    runtime_config = _default_model_runtime_config(settings)
    timeout = (
        _optional_positive_float_env("DRAWAI_CODEX_IMAGEGEN_TIMEOUT_SECONDS")
        or _optional_positive_float_env("DRAWAI_IMAGEGEN_TIMEOUT_SECONDS")
        or 300.0
    )
    runtime_config["timeout_seconds"] = timeout
    reasoning_effort = str(os.environ.get("DRAWAI_CODEX_IMAGEGEN_REASONING_EFFORT") or "").strip()
    if reasoning_effort:
        runtime_config["reasoning_effort"] = reasoning_effort
    runtime_config.pop("model_name", None)
    model_name = _codex_imagegen_model_name(payload)
    if model_name:
        runtime_config["model_name"] = model_name
    return runtime_config


def _default_model_runtime_config(settings: WorkbenchSettings) -> dict[str, Any]:
    try:
        cfg = load_drawai_config(settings.default_config, validate_input_exists=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to load DrawAI config: {exc}") from exc
    return cfg.model_runtime.to_runtime_dict()


def _codex_imagegen_model_name(payload: Mapping[str, Any]) -> str:
    model_name = str(payload.get("codex_model") or payload.get("model") or "").strip()
    if model_name.startswith("gpt-image-"):
        return ""
    return model_name


def _codex_generation_prompt(payload: Mapping[str, Any], *, variant_index: int, variant_count: int) -> str:
    return build_slide_image_generation_prompt(
        payload,
        variant_index=variant_index,
        variant_count=variant_count,
    )


def _codex_reference_context_prompt(prompt: str, *, source_image_path: str) -> str:
    return "\n".join(
        [
            prompt,
            "",
            "Image as context:",
            "- A real local image is supplied to Codex as LocalImageInput, but the requested output is a new PPT image, not a literal edit of the original bitmap.",
            f"- source_image_path: {source_image_path}",
            "- Use the supplied image for layout/style/color/typography context only unless the primary request explicitly asks for content preservation.",
            "- Replace the visible topic and slide copy with the user's requested content.",
        ]
    )


def _codex_edit_prompt(payload: Mapping[str, Any]) -> str:
    lines = [
        "DrawAI image editing request.",
        f"Primary edit request: {str(payload.get('prompt') or '').strip()}",
        "",
        "Editing settings selected in the DrawAI UI or API:",
    ]
    if payload.get("size"):
        lines.append(f"- Requested size/aspect: {payload.get('size')}")
    if payload.get("quality"):
        lines.append(f"- Quality preference: {payload.get('quality')}")
    if payload.get("background"):
        lines.append(f"- Background preference: {payload.get('background')}")
    lines.extend([
        "",
        "Edit only the supplied image input. Preserve unrelated content, layout, and identity as much as possible.",
        "Do not render these settings as visible text unless the primary edit request explicitly asks for text.",
    ])
    return "\n".join(lines)


def _codex_imagegen_response(
    results: list[CodexImageGenResult],
    *,
    provider: str,
    prompt: str,
    image_context: bool = False,
) -> dict[str, Any]:
    data: list[dict[str, Any]] = []
    for result in results:
        for image in result.images:
            image_bytes = image.path.read_bytes()
            data.append({
                "id": image.image_id,
                "provider": provider,
                "b64_json": base64.b64encode(image_bytes).decode("ascii"),
                "size": f"{image.width}x{image.height}",
                "width": image.width,
                "height": image.height,
                "mime_type": image.mime_type,
                "path": str(image.path),
                "revised_prompt": image.revised_prompt,
                "operation": result.operation,
                "source_image_path": str(result.source_image_path) if result.source_image_path is not None else None,
                "image_context": image_context,
            })
    return {
        "created": int(time.time()),
        "provider": provider,
        "prompt": prompt,
        "data": data,
        "codex": {
            "result_count": len(results),
            "image_count": len(data),
            "output_dirs": [str(result.output_dir) for result in results],
            "archives": [str(result.archive_dir) for result in results],
            "operations": [result.operation for result in results],
            "image_context": image_context,
            "source_image_paths": [
                str(result.source_image_path) if result.source_image_path is not None else None
                for result in results
            ],
        },
    }


def _codex_imagegen_output_dir(workspace: Path, operation: str) -> Path:
    root = workspace / "imagegen" / "codex" / operation
    root.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    for index in range(1, 10_000):
        suffix = "" if index == 1 else f"-{index}"
        candidate = root / f"{stamp}{suffix}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
    raise HTTPException(status_code=500, detail="could not allocate Codex image output directory")


def _image_generation_api_url(base_url: Any = None) -> str:
    raw = str(base_url or _default_image_generation_api_url()).strip()
    if not raw:
        raise HTTPException(status_code=503, detail="image generation API URL is empty")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="image generation Base URL must be an http(s) URL")
    path = parsed.path.rstrip("/")
    if path.endswith("/images/generations"):
        endpoint_path = path
    elif path.endswith("/v1"):
        endpoint_path = f"{path}/images/generations"
    elif path:
        endpoint_path = f"{path}/v1/images/generations"
    else:
        endpoint_path = "/v1/images/generations"
    return urllib.parse.urlunparse(parsed._replace(path=endpoint_path))


def _call_image_generation_upstream(payload: Mapping[str, Any], *, api_url: str, api_key: str | None = None) -> dict[str, Any]:
    api_key = api_key or os.environ.get("DRAWAI_IMAGEGEN_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="DRAWAI_IMAGEGEN_API_KEY or OPENAI_API_KEY is required for image generation")
    body = json.dumps(dict(payload)).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    timeout = _optional_positive_float_env("DRAWAI_IMAGEGEN_TIMEOUT_SECONDS") or 600.0
    try:
        with urlopen_external(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = _image_generation_error_detail(exc)
        raise HTTPException(status_code=exc.code or 502, detail=detail) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"image generation request failed: {exc}") from exc
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
    try:
        with urlopen_external(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = _image_generation_error_detail(exc)
        raise HTTPException(status_code=exc.code or 502, detail=detail) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"image generation task polling failed: {exc}") from exc
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
    marker = "/images/generations"
    if path.endswith(marker):
        base_path = path[: -len(marker)]
    else:
        base_path = "/v1"
    task_path = f"{base_path.rstrip('/')}/tasks/{urllib.parse.quote(task_id)}"
    return urllib.parse.urlunparse(parsed._replace(path=task_path, params="", query="", fragment=""))


def _default_image_generation_api_url() -> str:
    configured = os.environ.get("DRAWAI_IMAGEGEN_API_URL")
    if configured:
        return configured
    return IMAGEGEN_OPENAI_API_URL


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


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(value).name).strip("._")
    return name or "upload.png"


def _safe_download_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return stem or "drawai_batch"


def _safe_upload_relative_path(value: str) -> Path:
    parts = []
    for part in PurePosixPath(value.replace("\\", "/")).parts:
        if part in {"", "/", ".", ".."}:
            continue
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", part).strip("._")
        if safe:
            parts.append(safe)
    if not parts:
        return Path(_safe_filename(value))
    return Path(*parts)


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


def _extract_zip_image_sources(archive_path: Path, target_root: Path) -> list[Path]:
    sources: list[Path] = []
    target_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir() or Path(member.filename).suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                target = _unique_upload_path(target_root / _safe_upload_relative_path(member.filename))
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                sources.append(target)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"invalid zip file: {archive_path.name}") from exc
    return sources


def _runtime_services_status(
    settings: WorkbenchSettings,
    *,
    runtime_probe: Callable[[str, str], dict[str, Any]] | None,
) -> dict[str, Any]:
    probe = runtime_probe or _probe_runtime_service
    return {
        "sam3": probe("sam3", settings.sam3_base_url),
        "ocr": probe("ocr", settings.ocr_base_url),
        "rmbg": probe("rmbg", settings.rmbg_base_url),
    }


def _runtime_services_online(runtime_services: Mapping[str, Any]) -> bool:
    return bool(runtime_services) and all(
        isinstance(service, Mapping) and service.get("status") == "online"
        for service in runtime_services.values()
    )


def _probe_runtime_service(name: str, base_url: str) -> dict[str, Any]:
    normalized_base = str(base_url or "").rstrip("/")
    health_url = f"{normalized_base}/health" if normalized_base else ""
    payload: dict[str, Any] = {
        "name": name,
        "base_url": normalized_base,
        "health_url": health_url,
        "status": "offline",
    }
    if not health_url:
        payload["error"] = "base_url is empty"
        return payload
    request = urllib.request.Request(health_url, headers={"Accept": "application/json"})
    try:
        with urlopen_direct_for_loopback(request, health_url, timeout=1.5) as response:
            body = response.read(4096)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        payload["error"] = str(exc)
        return payload
    try:
        decoded = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        decoded = {}
    if isinstance(decoded, dict):
        payload["details"] = decoded
        health_status = str(decoded.get("status") or "").strip().lower()
        if health_status and health_status not in {"ok", "online", "healthy"}:
            payload["error"] = f"health status is {health_status}"
            return payload
        service_error = _runtime_service_health_error(decoded, name)
        if service_error:
            payload["error"] = service_error
            return payload
    payload["status"] = "online"
    return payload


def _runtime_service_health_error(decoded: Mapping[str, Any], name: str) -> str:
    services = decoded.get("services")
    if not isinstance(services, Mapping) or name not in services:
        return ""
    service = services.get(name)
    if not isinstance(service, Mapping):
        return f"{name} health payload is invalid"
    if service.get("error"):
        return str(service.get("error"))
    status = str(service.get("status") or "").strip().lower()
    if status and status not in {"ok", "online", "healthy", "ready"}:
        return f"{name} status is {status}"
    return ""


def _case_to_api_with_preview(store: WorkbenchStore, case: CaseRecord) -> dict[str, Any]:
    payload = case.to_api()
    classification = classify_run_root(case.run_root)
    source_path = Path(case.source_image_path).expanduser().resolve(strict=False)
    source_preview_url = (
        f"/api/cases/{case.case_id}/source-image"
        if source_path.is_file() and source_path.suffix.lower() in IMAGE_EXTENSIONS
        else ""
    )
    artifacts = store.list_artifacts(case.case_id)
    preview = next(
        (
            artifact
            for artifact in reversed(artifacts)
            if artifact.label == "figure" and artifact.media_type.startswith("image/")
        ),
        None,
    )
    payload["preview_url"] = source_preview_url or (preview.to_api()["url"] if preview else "")
    payload["editor_ready"] = (Path(case.run_root) / "reports" / "workbench" / "asset_draft.json").is_file()
    payload["compatibility_mode"] = (
        classification.mode
        if classification.mode in {"v2", "legacy_readonly"}
        else "none"
    )
    payload["can_fork_from_source"] = classification.can_fork_from_source
    payload["workflow_breakpoint_node_id"] = workflow_breakpoint_node_id(case.run_root)
    return payload


STANDARD_PROGRESS_FILES = (
    ("figure", "inputs/figure.png"),
    ("asset_draft", "reports/workbench/asset_draft.json"),
    ("approved_asset_plan", "reports/workbench/approved_asset_plan.json"),
    ("element_analysis", "reports/element_analysis_codex/element_analysis.json"),
    ("asset_manifest", "svg_to_ppt/assets/asset_manifest.json"),
    ("semantic_svg", "svg/semantic.svg"),
    ("rendered_png", "svg/rendered.png"),
    ("svg_validation_report", "reports/svg_validation_report.json"),
    ("pptx_export_report", "reports/svg_to_ppt_export_report.json"),
    ("pptx", "svg_to_ppt/semantic.svg_to_ppt.pptx"),
)

SVG_ATTEMPT_FILES = (
    ("prompt", "prompt.txt"),
    ("request_context", "request_context.json"),
    ("validator_context", "validator_context.json"),
    ("semantic_svg", "semantic.svg"),
    ("rendered_png", "rendered.png"),
    ("validation_report", "validation_report.json"),
    ("model_response", "model_response.txt"),
    ("final_report", "final_report.json"),
    ("iteration_log", "iteration_log.md"),
    ("codex_session_manifest", "codex_session_log/manifest.json"),
)


def _standard_progress_files(case_id: str, root: Path) -> list[dict[str, Any]]:
    return [_case_file_record(case_id, root, label, relative_path) for label, relative_path in STANDARD_PROGRESS_FILES]


def _svg_attempts_progress(case_id: str, root: Path) -> list[dict[str, Any]]:
    attempts_root = root / "svg" / "attempts"
    if not attempts_root.exists():
        return []
    attempts: list[dict[str, Any]] = []
    for attempt_dir in sorted(path for path in attempts_root.glob("*/*") if path.is_dir()):
        relative_attempt_dir = attempt_dir.relative_to(root).as_posix()
        files = [
            _case_file_record(case_id, root, label, f"{relative_attempt_dir}/{relative_path}")
            for label, relative_path in SVG_ATTEMPT_FILES
            if (attempt_dir / relative_path).exists()
        ]
        summary = _svg_attempt_summary(attempt_dir, files)
        attempts.append(
            {
                "phase": attempt_dir.parent.name,
                "attempt": attempt_dir.name,
                "relative_path": relative_attempt_dir,
                "status": summary["status"],
                "issue_count": summary["issue_count"],
                "issue_summaries": summary["issue_summaries"],
                "error_message": summary["error_message"],
                "updated_at": summary["updated_at"],
                "files": files,
            }
        )
    return attempts


def _workflow_node_runs_progress(root: Path) -> list[dict[str, Any]]:
    nodes_root = root / "nodes"
    if not nodes_root.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for run_path in sorted(nodes_root.glob("*/runs/*/node_run.json")):
        payload = _read_json_file(run_path)
        if not isinstance(payload, dict):
            continue
        node_id = str(payload.get("node_id") or run_path.parents[2].name)
        attempt_id = str(payload.get("attempt_id") or run_path.parent.name)
        provider_id = str(payload.get("provider_id") or "")
        if not provider_id:
            manifest = _workflow_node_execution_manifest(root, payload)
            provider_id = str(manifest.get("provider_id") or "") if manifest else ""
        resource_id = str(payload.get("resource_id") or "")
        runs.append(
            {
                "node_id": node_id,
                "attempt_id": attempt_id,
                "status": str(payload.get("status") or ""),
                "provider_id": provider_id,
                "provider_label": _workflow_provider_label(provider_id),
                "resource_id": resource_id,
                "started_at": str(payload.get("started_at") or ""),
                "ended_at": str(payload.get("ended_at") or ""),
                "error_message": str(payload.get("error") or ""),
                "workdir": _case_relative_path(root, run_path.parent),
            }
        )
    return runs


def _workflow_node_metadata(store: WorkbenchStore, case: CaseRecord) -> list[dict[str, Any]]:
    batch = store.get_batch(case.batch_id)
    template = load_workflow_template_by_id(store.workspace, batch.workflow_template_id)
    settings_snapshot = read_case_settings_snapshot_or_workspace(case.run_root, store.workspace)
    effective = _workflow_template_with_agent_settings(
        template,
        settings_snapshot.agent_settings,
        execution_mode=batch.execution_mode,
        processor_operation_config=resolved_processor_operation_config_from_settings(
            settings_snapshot.processor_settings,
            api_presets=settings_snapshot.api_presets,
        ),
    )
    api_presets = settings_snapshot.api_presets
    processor_api_presets = _workflow_processor_api_preset_summaries(settings_snapshot.processor_settings, api_presets)
    processor_types = _workflow_processor_types_for_refine(settings_snapshot.processor_settings, api_presets)
    metadata: list[dict[str, Any]] = []
    for node in effective.nodes:
        config = dict(node.config)
        provider_id = str(config.get("provider_id") or "")
        model = str(config.get("model") or config.get("model_name") or "")
        node_api_presets = list(_workflow_node_api_preset_summaries(config, api_presets))
        if node.node_id == "asset_prepare":
            node_api_presets.extend(processor_api_presets)
        metadata.append(
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "provider_id": provider_id,
                "provider_label": _workflow_provider_label(provider_id),
                "model": model,
                "api_presets": _dedupe_api_preset_summaries(node_api_presets),
                "processor_types": processor_types if node.node_id == "page_spec_refine" else [],
            }
        )
    return metadata


def _workflow_provider_label(provider_id: str) -> str:
    if not provider_id:
        return ""
    provider = default_agent_provider_registry().get(provider_id)
    if provider is not None:
        return provider.label
    if provider_id == "openai_compatible":
        return "OpenAI Compatible API"
    return provider_id.replace("_", " ").title()


def _workflow_processor_api_preset_summaries(
    settings: Mapping[str, ProcessorSetting],
    api_presets: Sequence[ApiPreset],
) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for processing_type, setting in settings.items():
        if not setting.enabled or not setting.api_preset_id:
            continue
        driver = PROCESSOR_DRIVER_DEFINITIONS[setting.driver_id]
        if not driver.required_api_preset_type:
            continue
        preset = api_preset_by_id(api_presets, setting.api_preset_id)
        if preset is None:
            continue
        summaries.append(
            {
                "processing_type": processing_type,
                "api_preset_id": preset.id,
                "api_preset_label": preset.label or preset.id,
            }
        )
    return summaries


def _workflow_processor_types_for_refine(
    settings: Mapping[str, ProcessorSetting],
    api_presets: Sequence[ApiPreset],
) -> list[str]:
    operation_config = resolved_processor_operation_config_from_settings(settings, api_presets=api_presets)
    return [
        processing_type
        for item in operation_config.get("page_spec_processing_types", [])
        if (processing_type := str(item).strip())
    ]


def _workflow_node_api_preset_summaries(
    config: Mapping[str, Any],
    api_presets: Sequence[ApiPreset],
) -> list[dict[str, str]]:
    api_preset_id = str(config.get("api_preset_id") or "")
    if api_preset_id:
        preset = api_preset_by_id(api_presets, api_preset_id)
        if preset is not None:
            return [{"processing_type": "", "api_preset_id": preset.id, "api_preset_label": preset.label or preset.id}]
        return [{"processing_type": "", "api_preset_id": api_preset_id, "api_preset_label": api_preset_id}]
    base_url = str(config.get("base_url") or "").strip().rstrip("/")
    model = str(config.get("model") or config.get("model_name") or "").strip()
    if not base_url or not model:
        return []
    summaries: list[dict[str, str]] = []
    for preset in api_presets:
        if preset.type not in {"llm_chat_completions", "llm_responses"}:
            continue
        if preset.base_url.strip().rstrip("/") == base_url and preset.model.strip() == model:
            summaries.append({"processing_type": "", "api_preset_id": preset.id, "api_preset_label": preset.label or preset.id})
    return summaries


def _dedupe_api_preset_summaries(items: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in items:
        processing_type = str(item.get("processing_type") or "")
        preset_id = str(item.get("api_preset_id") or "")
        preset_label = str(item.get("api_preset_label") or preset_id)
        key = (processing_type, preset_id)
        if not preset_id or key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "processing_type": processing_type,
                "api_preset_id": preset_id,
                "api_preset_label": preset_label,
            }
        )
    return result


def _workflow_node_execution_manifest(root: Path, node_run: Mapping[str, Any]) -> dict[str, Any]:
    candidates: list[str] = []
    raw_manifest = node_run.get("execution_manifest_path")
    if isinstance(raw_manifest, str) and raw_manifest:
        candidates.append(raw_manifest)
    outputs = node_run.get("outputs")
    if isinstance(outputs, Sequence) and not isinstance(outputs, (str, bytes)):
        for output in outputs:
            if not isinstance(output, Mapping):
                continue
            raw = output.get("execution_manifest_path")
            if isinstance(raw, str) and raw:
                candidates.append(raw)
    for candidate in candidates:
        path = _resolve_case_path(root, candidate)
        payload = _read_json_file(path)
        if isinstance(payload, dict):
            return payload
    return {}


def _svg_attempt_summary(attempt_dir: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    validation_report = _read_json_file(attempt_dir / "validation_report.json")
    final_report = _read_json_file(attempt_dir / "final_report.json")
    report = validation_report or final_report
    status = str(report.get("status") or "") if isinstance(report, dict) else ""
    raw_issues = report.get("issues") if isinstance(report, dict) else []
    issue_summaries = _issue_summaries(raw_issues)

    if not status:
        semantic = attempt_dir / "semantic.svg"
        model_response = attempt_dir / "model_response.txt"
        if semantic.exists() and semantic.stat().st_size > 0:
            status = "validating"
        elif model_response.exists():
            status = "extracting_svg"
        else:
            status = "running"
    elif status != "ok":
        status = "failed"

    updated_times = [item["updated_at"] for item in files if item.get("updated_at") is not None]
    return {
        "status": status,
        "issue_count": len(raw_issues) if isinstance(raw_issues, list) else len(issue_summaries),
        "issue_summaries": issue_summaries,
        "error_message": "; ".join(issue_summaries[:3]),
        "updated_at": max(updated_times) if updated_times else None,
    }


def _pptx_export_progress(case_id: str, root: Path) -> dict[str, Any]:
    report_path = root / "reports" / "svg_to_ppt_export_report.json"
    report = _read_json_file(report_path)
    if not report:
        return {
            "status": "missing",
            "export_backend": "",
            "requested_export_mode": "",
            "effective_export_mode": "",
            "export_mode": "",
            "editable_surface": "",
            "report_url": "",
        }

    export_backend = str(report.get("export_backend") or report.get("backend") or "")
    effective_export_mode = str(
        report.get("effective_export_mode") or report.get("export_mode") or _pptx_export_mode_for_backend(export_backend) or ""
    )
    return {
        "status": str(report.get("status") or ""),
        "export_backend": export_backend,
        "requested_export_mode": str(report.get("requested_export_mode") or effective_export_mode),
        "effective_export_mode": effective_export_mode,
        "export_mode": effective_export_mode,
        "editable_surface": str(report.get("editable_surface") or _pptx_editable_surface_for_backend(export_backend) or ""),
        "report_url": _case_file_url(case_id, "reports/svg_to_ppt_export_report.json") if report_path.exists() else "",
    }


def _pptx_export_mode_for_backend(export_backend: str) -> str:
    if export_backend == "drawai_native_shapes":
        return "native_shapes"
    return ""


def _pptx_editable_surface_for_backend(export_backend: str) -> str:
    if export_backend == "drawai_native_shapes":
        return "native_shapes"
    return ""


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _issue_summaries(raw_issues: Any) -> list[str]:
    if not isinstance(raw_issues, list):
        return []
    summaries: list[str] = []
    for issue in raw_issues:
        if isinstance(issue, dict):
            parts = [str(issue.get(key) or "").strip() for key in ("code", "message", "detail")]
            text = ": ".join(part for part in parts if part)
        else:
            text = str(issue).strip()
        if text:
            summaries.append(_truncate_progress_text(text, limit=320))
    return summaries


def _truncate_progress_text(value: str, *, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def _workflow_node_viewer_payload(case: CaseRecord, node_id: str) -> dict[str, Any]:
    safe_node_id = _safe_workflow_node_id(node_id)
    root = Path(case.run_root).expanduser().resolve()
    run_dir = _latest_workflow_node_run_dir(root, safe_node_id)
    source_image = _workflow_viewer_source_image(case, root)
    base_payload: dict[str, Any] = {
        "case_id": case.case_id,
        "node_id": safe_node_id,
        "available": False,
        "kind": "none",
        "title": safe_node_id,
        "message": "这个节点还没有可视化产物。",
        "source_image": source_image,
        "workdir": "",
        "attempt_id": "",
        "node_run": None,
        "input_manifest": None,
        "files": [],
        "artifacts": [],
        "primary_artifact_id": "",
        "agent_logs": {
            "files": [],
            "trace_events": [],
            "session_summary": {},
            "session_events": [],
            "runtime_log_tail": [],
        },
        "elements": [],
        "asset_packages": [],
    }
    if run_dir is None:
        base_payload["message"] = "这个节点还没有运行记录。"
        return base_payload

    node_run = _read_json_object_if_exists(run_dir / "node_run.json")
    input_manifest = _read_json_object_if_exists(run_dir / "input_manifest.json")
    workdir = _case_relative_path(root, run_dir)
    output_files = _workflow_node_output_files(case, root, run_dir, node_run)
    agent_logs = _workflow_node_agent_logs(case, root, run_dir, node_run)
    base_payload.update(
        {
            "title": str((node_run or {}).get("node_id") or safe_node_id),
            "workdir": workdir,
            "attempt_id": run_dir.name,
            "node_run": node_run,
            "input_manifest": input_manifest,
            "files": output_files,
            "agent_logs": agent_logs,
        }
    )

    overlay_source = _workflow_node_overlay_source(root, run_dir, node_run)
    artifacts = _workflow_node_artifacts(case, root, output_files, agent_logs, node_run, overlay_source)
    base_payload.update(
        {
            "artifacts": artifacts,
            "primary_artifact_id": _workflow_node_primary_artifact_id(artifacts),
        }
    )
    if overlay_source is None:
        if artifacts:
            base_payload["message"] = "这个节点没有 bbox 叠加产物，已显示节点输出文件。"
        else:
            base_payload["message"] = "这个节点的输出文件暂时没有可绘制的 bbox。"
        return base_payload

    kind, relative_path, payload = overlay_source
    element_kind = kind
    asset_packages = _workflow_viewer_asset_packages_from_payload(payload) if kind == "asset_packages" else []
    if safe_node_id == "asset_prepare":
        asset_packages = asset_packages or _workflow_viewer_asset_packages_from_output(root, run_dir)
        if asset_packages:
            kind = "asset_packages"
    elements = _workflow_viewer_elements_from_payload(payload, element_kind, root=root)
    if not elements:
        base_payload["message"] = "这个节点产物已生成，但没有可绘制的 bbox。"
        base_payload["kind"] = kind
        base_payload["source_path"] = relative_path
        base_payload["asset_packages"] = asset_packages
        return base_payload

    base_payload.update(
        {
            "available": True,
            "kind": kind,
            "message": "",
            "source_path": relative_path,
            "elements": elements,
            "asset_packages": asset_packages,
        }
    )
    return base_payload


def _safe_workflow_node_id(value: str) -> str:
    node_id = str(value or "").strip()
    if not node_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", node_id):
        raise ValueError(f"workflow node_id must be a safe path segment: {value}")
    if node_id in {".", ".."}:
        raise ValueError(f"workflow node_id must be a safe path segment: {value}")
    return node_id


def _latest_workflow_node_run_dir(root: Path, node_id: str) -> Path | None:
    runs_dir = _resolve_case_path(root, Path("nodes") / node_id / "runs")
    if not runs_dir.is_dir():
        return None
    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not run_dirs:
        return None
    return sorted(run_dirs, key=lambda path: (path.name, path.stat().st_mtime))[-1]


def _workflow_viewer_source_image(case: CaseRecord, root: Path) -> dict[str, str]:
    figure = _case_figure_path(case).expanduser().resolve(strict=False)
    try:
        relative_path = _case_relative_path(root, figure)
    except ValueError:
        return {"relative_path": "", "url": f"/api/cases/{case.case_id}/source-image"}
    return {"relative_path": relative_path, "url": _case_file_url(case.case_id, relative_path)}


def _workflow_node_output_files(
    case: CaseRecord,
    root: Path,
    run_dir: Path,
    node_run: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    relative_paths: list[str] = []
    if node_run:
        for item in _json_list(node_run.get("outputs")):
            path = item.get("path")
            if isinstance(path, str) and path:
                relative_paths.append(path)
            for key in (
                "prompt_path",
                "stdout_path",
                "stderr_path",
                "trace_path",
                "session_log_path",
                "execution_manifest_path",
            ):
                path = item.get(key)
                if isinstance(path, str) and path:
                    relative_paths.append(path)
        for key in (
            "prompt_path",
            "stdout_path",
            "stderr_path",
            "trace_path",
            "session_log_path",
            "execution_manifest_path",
        ):
            path = node_run.get(key)
            if isinstance(path, str) and path:
                relative_paths.append(path)
    output_dir = run_dir / "output"
    if output_dir.is_dir():
        for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
            relative_paths.append(_case_relative_path(root, path))

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative_path in relative_paths:
        if relative_path in seen:
            continue
        seen.add(relative_path)
        if _resolve_case_path(root, relative_path).is_dir():
            continue
        records.append(_case_file_record(case.case_id, root, Path(relative_path).name, relative_path))
    return records


def _workflow_node_artifacts(
    case: CaseRecord,
    root: Path,
    output_files: list[dict[str, Any]],
    agent_logs: Mapping[str, Any],
    node_run: Mapping[str, Any] | None,
    overlay_source: tuple[str, str, Mapping[str, Any] | list[Any]] | None,
) -> list[dict[str, Any]]:
    output_meta_by_path = _workflow_node_output_meta_by_path(node_run)
    artifacts: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    if overlay_source is not None:
        overlay_kind, relative_path, _ = overlay_source
        file_record = _case_file_record(case.case_id, root, _workflow_artifact_overlay_label(overlay_kind), relative_path)
        artifacts.append(
            _workflow_node_artifact_record(
                file_record,
                kind=_workflow_artifact_overlay_kind(overlay_kind),
                role="primary",
                source="overlay",
                priority=0,
            )
        )
        seen_paths.add(relative_path)

    for file_record in output_files:
        relative_path = str(file_record.get("relative_path") or "")
        if not relative_path or relative_path in seen_paths or not file_record.get("exists"):
            continue
        seen_paths.add(relative_path)
        meta = output_meta_by_path.get(relative_path, {})
        output_type = str(meta.get("type") or "")
        format_id = str(meta.get("format_id") or "")
        kind = _workflow_artifact_kind(relative_path, output_type, format_id, str(file_record.get("media_type") or ""))
        role = _workflow_artifact_role(relative_path, kind, output_type, format_id, source="output")
        artifacts.append(
            _workflow_node_artifact_record(
                file_record,
                kind=kind,
                role=role,
                source="output",
                priority=_workflow_artifact_priority(relative_path, kind, role),
            )
        )

    if _workflow_agent_logs_available(agent_logs):
        artifacts.append(_workflow_node_agent_log_artifact(agent_logs))

    return sorted(
        artifacts,
        key=lambda item: (
            int(item.get("priority") or 100),
            str(item.get("relative_path") or ""),
        ),
    )


def _workflow_node_output_meta_by_path(node_run: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not node_run:
        return {}
    output_meta: dict[str, Mapping[str, Any]] = {}
    for item in _json_list(node_run.get("outputs")):
        path = item.get("path")
        if isinstance(path, str) and path:
            output_meta[path] = item
    return output_meta


def _workflow_node_artifact_record(
    file_record: Mapping[str, Any],
    *,
    kind: str,
    role: str,
    source: str,
    priority: int,
) -> dict[str, Any]:
    relative_path = str(file_record.get("relative_path") or "")
    label = str(file_record.get("label") or Path(relative_path).name)
    return {
        "artifact_id": f"{source}:{relative_path}",
        "kind": kind,
        "role": role,
        "source": source,
        "priority": priority,
        "label": label,
        "relative_path": relative_path,
        "exists": bool(file_record.get("exists")),
        "media_type": str(file_record.get("media_type") or ""),
        "size_bytes": int(file_record.get("size_bytes") or 0),
        "updated_at": file_record.get("updated_at"),
        "url": str(file_record.get("url") or ""),
    }


def _workflow_node_agent_log_artifact(agent_logs: Mapping[str, Any]) -> dict[str, Any]:
    event_count = (
        len(_json_list(agent_logs.get("session_events")))
        or len(_json_list(agent_logs.get("trace_events")))
        or len(_json_list(agent_logs.get("runtime_log_tail")))
    )
    file_count = len([file for file in _json_list(agent_logs.get("files")) if file.get("exists")])
    return {
        "artifact_id": "agent_log:timeline",
        "kind": "agent_log",
        "role": "log",
        "source": "agent_log",
        "priority": 90,
        "label": "Agent log",
        "relative_path": "",
        "exists": True,
        "media_type": "application/vnd.drawai.agent-log+json",
        "size_bytes": 0,
        "updated_at": None,
        "url": "",
        "event_count": event_count,
        "file_count": file_count,
    }


def _workflow_agent_logs_available(agent_logs: Mapping[str, Any]) -> bool:
    if any(file.get("exists") for file in _json_list(agent_logs.get("files"))):
        return True
    if _json_list(agent_logs.get("session_events")):
        return True
    if _json_list(agent_logs.get("trace_events")):
        return True
    if _json_list(agent_logs.get("runtime_log_tail")):
        return True
    summary = agent_logs.get("session_summary")
    return isinstance(summary, Mapping) and bool(summary.get("final_response"))


def _workflow_node_primary_artifact_id(artifacts: list[dict[str, Any]]) -> str:
    for role in ("primary", "accepted", "preview", "validation", "output", "script"):
        for artifact in artifacts:
            if artifact.get("role") == role and artifact.get("exists"):
                return str(artifact.get("artifact_id") or "")
    for artifact in artifacts:
        if artifact.get("exists") and artifact.get("role") != "log":
            return str(artifact.get("artifact_id") or "")
    for artifact in artifacts:
        if artifact.get("exists"):
            return str(artifact.get("artifact_id") or "")
    return ""


def _workflow_artifact_overlay_kind(overlay_kind: str) -> str:
    if overlay_kind == "asset_packages":
        return "asset_packages"
    return "bbox_overlay"


def _workflow_artifact_overlay_label(overlay_kind: str) -> str:
    return {
        "page_spec": "PageSpec overlay",
        "element_plans": "Element plans overlay",
        "element_candidates": "Candidate overlay",
        "element_analysis": "Element analysis overlay",
        "asset_packages": "Asset packages",
    }.get(overlay_kind, "Overlay")


def _workflow_artifact_kind(relative_path: str, output_type: str, format_id: str, media_type: str) -> str:
    path = Path(relative_path)
    name = path.name.lower()
    suffix = path.suffix.lower()
    probe = f"{output_type} {format_id} {relative_path} {media_type}".lower()
    if "validation_report" in name:
        return "validation_report"
    if "semantic_svg" in probe or "drawai.semantic_svg" in probe or suffix == ".svg":
        return "svg"
    if "drawai.pptx" in probe or output_type == "pptx" or suffix == ".pptx":
        return "pptx"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".py":
        return "script"
    if suffix in {".txt", ".log"}:
        return "text"
    if suffix in {".sqlite", ".db"}:
        return "sqlite"
    return "file"


def _workflow_artifact_role(relative_path: str, kind: str, output_type: str, format_id: str, *, source: str) -> str:
    if source == "agent_log":
        return "log"
    name = Path(relative_path).name.lower()
    probe = f"{output_type} {format_id}".lower()
    if "drawai.semantic_svg" in probe or "drawai.pptx" in probe or output_type in {"semantic_svg", "pptx"}:
        return "accepted"
    if name in {"semantic.svg", "semantic_svg.svg", "slide_deck.pptx"}:
        return "accepted"
    if name.startswith("semantic_") and name.endswith(".svg"):
        return "intermediate"
    if name.startswith("rendered") and kind == "image":
        return "preview"
    if kind == "validation_report":
        return "validation"
    if kind == "script":
        return "script"
    if kind in {"jsonl", "sqlite"} or name.endswith(("_trace.jsonl", "_events.jsonl", "_stderr.txt", "_error.txt")):
        return "log"
    return "output"


def _workflow_artifact_priority(relative_path: str, kind: str, role: str) -> int:
    name = Path(relative_path).name.lower()
    role_priority = {
        "primary": 0,
        "accepted": 10,
        "preview": 20,
        "validation": 30,
        "intermediate": 35,
        "output": 40,
        "script": 50,
        "log": 90,
    }.get(role, 80)
    if name in {"semantic.svg", "semantic_svg.svg"}:
        return 5
    if kind == "pptx" and role == "accepted":
        return 8
    if name == "rendered.png":
        return 18
    if name == "validation_report_final.json":
        return 28
    return role_priority


AGENT_LOG_FILE_CANDIDATES = (
    "prompt.md",
    "agent_execution_request.json",
    "agent_execution.json",
    "codex_sdk_trace.jsonl",
    "codex_sdk_final_response.txt",
    "codex_sdk_error.txt",
    "codex_cli_trace.jsonl",
    "codex_cli_events.jsonl",
    "codex_cli_stderr.txt",
    "kimi_cli_trace.jsonl",
    "kimi_events.jsonl",
    "kimi_stderr.txt",
    "kimi_acp_trace.jsonl",
    "kimi_acp_final_response.txt",
    "kimi_acp_error.txt",
    "gemini_acp_trace.jsonl",
    "gemini_acp_final_response.txt",
    "gemini_acp_error.txt",
    "codex_session_log/live_manifest.json",
    "codex_session_log/manifest.json",
    "codex_session_log/turn_result_summary.json",
    "codex_session_log/codex_session_events.jsonl",
    "codex_session_log/codex_runtime_events.jsonl",
    "codex_session_log/logs_2.sqlite",
    "codex_session_log/state_5.sqlite",
)


def _workflow_node_agent_logs(
    case: CaseRecord,
    root: Path,
    run_dir: Path,
    node_run: Mapping[str, Any] | None,
) -> dict[str, Any]:
    relative_paths: list[str] = []
    for relative_path in AGENT_LOG_FILE_CANDIDATES:
        path = run_dir / relative_path
        if path.exists():
            relative_paths.append(_case_relative_path(root, path))
    for path in sorted(run_dir.glob("*_trace.jsonl")):
        relative_paths.append(_case_relative_path(root, path))
    for pattern in ("*_events.jsonl", "*_stderr.txt", "*_error.txt", "*_final_response.txt"):
        for path in sorted(run_dir.glob(pattern)):
            relative_paths.append(_case_relative_path(root, path))
    if node_run:
        for key in (
            "prompt_path",
            "stdout_path",
            "stderr_path",
            "trace_path",
            "session_log_path",
            "execution_manifest_path",
        ):
            value = node_run.get(key)
            if isinstance(value, str) and value:
                relative_paths.append(value)
        for item in _json_list(node_run.get("outputs")):
            for key in (
                "prompt_path",
                "stdout_path",
                "stderr_path",
                "trace_path",
                "session_log_path",
                "execution_manifest_path",
            ):
                value = item.get(key)
                if isinstance(value, str) and value:
                    relative_paths.append(value)

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative_path in relative_paths:
        if relative_path in seen:
            continue
        seen.add(relative_path)
        path = _resolve_case_path(root, relative_path)
        if path.is_dir():
            manifest = path / "manifest.json"
            live_manifest = path / "live_manifest.json"
            if manifest.is_file():
                records.append(_case_file_record(case.case_id, root, "session_manifest", _case_relative_path(root, manifest)))
            if live_manifest.is_file():
                records.append(
                    _case_file_record(case.case_id, root, "session_live_manifest", _case_relative_path(root, live_manifest))
                )
            continue
        records.append(_case_file_record(case.case_id, root, path.name, relative_path))

    trace_events = _agent_trace_events(root, run_dir, node_run)
    session_dir = run_dir / "codex_session_log"
    return {
        "files": records,
        "trace_events": trace_events,
        "session_summary": _read_json_object_if_exists(session_dir / "turn_result_summary.json"),
        "session_events": _agent_session_events(session_dir / "codex_session_events.jsonl"),
        "runtime_log_tail": _codex_runtime_event_tail(session_dir / "codex_runtime_events.jsonl")
        or _codex_runtime_log_tail(session_dir / "logs_2.sqlite"),
    }


def _agent_trace_events(
    root: Path,
    run_dir: Path,
    node_run: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    paths = _agent_trace_event_paths(root, run_dir, node_run)
    for path in paths:
        for item in _read_jsonl_tail(path, limit=80):
            if isinstance(item, dict):
                events.append(
                    {
                        "source": path.name,
                        "type": str(item.get("type") or ""),
                        "summary": _truncate_progress_text(_compact_json_text(item), limit=800),
                        "event": _agent_log_event_detail(item),
                    }
                )
    return events[-80:]


def _agent_trace_event_paths(
    root: Path,
    run_dir: Path,
    node_run: Mapping[str, Any] | None = None,
) -> list[Path]:
    paths: list[Path] = []
    for name in ("codex_sdk_trace.jsonl", "codex_cli_trace.jsonl", "kimi_cli_trace.jsonl"):
        path = run_dir / name
        if path.is_file():
            paths.append(path)
    for path in sorted(run_dir.glob("*_trace.jsonl")):
        if path.is_file():
            paths.append(path)
    if node_run:
        for value in _workflow_node_log_values(node_run, "trace_path"):
            path = _resolve_case_path(root, value)
            if path.is_file():
                paths.append(path)
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


def _workflow_node_log_values(node_run: Mapping[str, Any], key: str) -> list[str]:
    values: list[str] = []
    value = node_run.get(key)
    if isinstance(value, str) and value:
        values.append(value)
    for item in _json_list(node_run.get("outputs")):
        value = item.get(key)
        if isinstance(value, str) and value:
            values.append(value)
    return values


def _agent_session_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in _read_jsonl(path):
        if not isinstance(item, dict):
            continue
        event_item = item.get("item")
        summary = _agent_session_event_summary(event_item)
        if not summary:
            continue
        events.append(
            {
                "index": item.get("index"),
                "kind": _agent_event_kind(event_item),
                "summary": _truncate_progress_text(summary, limit=1200),
                "event": _agent_log_event_detail(event_item),
            }
        )
    return events


def _codex_runtime_log_tail(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[tuple[Any, ...]]
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.2)
        try:
            rows = connection.execute(
                "select ts, level, target, feedback_log_body from logs order by id desc limit 80"
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return []
    events: list[dict[str, Any]] = []
    for row in reversed(rows):
        message = str(row[3] or "")
        event_type = _codex_runtime_event_type_from_message(message)
        if _is_low_value_codex_runtime_event(event_type, message):
            continue
        events.append(
            {
                "ts": row[0],
                "level": str(row[1] or ""),
                "target": str(row[2] or ""),
                "event_type": event_type,
                "message": _truncate_progress_text(message, limit=900),
                "event": {"message": _truncate_progress_text(message, limit=900)},
            }
        )
    return events


def _codex_runtime_event_tail(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in _read_jsonl_tail(path, limit=120):
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "")
        event = item.get("event")
        event_type = str(item.get("event_type") or "")
        event_kind = str(item.get("event_kind") or "")
        if isinstance(event, Mapping):
            event_type = event_type or str(event.get("type") or "")
            text = event.get("text")
            delta = event.get("delta")
            if isinstance(text, str) and text:
                message = text
            elif isinstance(delta, str) and delta:
                message = delta
        if _is_low_value_codex_runtime_event(event_type or event_kind, message):
            continue
        events.append(
            {
                "ts": item.get("ts"),
                "level": str(item.get("level") or ""),
                "target": str(item.get("target") or ""),
                "event_type": event_type or event_kind,
                "message": _truncate_progress_text(message, limit=900),
                "event": _agent_log_event_detail(event if isinstance(event, Mapping) else item),
            }
        )
    return events


LOW_VALUE_CODEX_RUNTIME_EVENT_TYPES = {
    "response.output_text.delta",
    "response.function_call_arguments.delta",
}


def _agent_session_event_summary(value: Any) -> str:
    if not isinstance(value, Mapping):
        return _compact_json_text(value)

    item_type = str(value.get("type") or "")
    if item_type == "agentMessage":
        phase = str(value.get("phase") or "message").strip()
        text = str(value.get("text") or "").strip()
        return f"{phase}: {text}" if text else phase

    if item_type == "commandExecution":
        command = str(value.get("command") or "").strip()
        status = str(value.get("status") or "").strip()
        exit_code = value.get("exitCode")
        output = str(value.get("aggregatedOutput") or "").strip()
        parts = []
        if command:
            parts.append("command: " + _truncate_progress_text(command, limit=520))
        status_parts = []
        if status:
            status_parts.append(status)
        if exit_code is not None:
            status_parts.append(f"exit={exit_code}")
        if status_parts:
            parts.append("status: " + " ".join(status_parts))
        if output:
            parts.append("output: " + _truncate_progress_text(output, limit=360))
        return " | ".join(parts)

    if item_type == "imageView":
        path = str(value.get("path") or "").strip()
        return f"image: {path}" if path else "image viewed"

    if item_type == "fileChange":
        path = str(value.get("path") or "").strip()
        action = str(value.get("action") or value.get("status") or "").strip()
        return " ".join(part for part in ("file", action, path) if part)

    if item_type == "userMessage":
        text = str(value.get("text") or "").strip()
        return f"user: {text}" if text else "user message"

    if item_type == "reasoning":
        summary = value.get("summary")
        if isinstance(summary, list) and summary:
            return _compact_json_text(summary)
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        return ""

    for key in ("summary", "message", "text", "name"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return _compact_json_text(value)


def _codex_runtime_event_type_from_message(message: str) -> str:
    if "websocket event:" not in message:
        return ""
    payload_text = message.partition("websocket event:")[2].strip()
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return ""
    return str(payload.get("type") or "") if isinstance(payload, Mapping) else ""


def _is_low_value_codex_runtime_event(event_type: str, message: str) -> bool:
    if event_type in LOW_VALUE_CODEX_RUNTIME_EVENT_TYPES:
        return True
    return not message.strip()


def _read_jsonl_tail(path: Path, *, limit: int) -> list[Any]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return _jsonl_items_from_lines(lines[-limit:])


def _read_jsonl(path: Path) -> list[Any]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return _jsonl_items_from_lines(lines)


def _jsonl_items_from_lines(lines: Sequence[str]) -> list[Any]:
    items: list[Any] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"raw": line})
    return items


def _agent_event_kind(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("type", "kind", "name", "role"):
            item = value.get(key)
            if isinstance(item, str) and item:
                return item
    return type(value).__name__


def _agent_log_event_detail(value: Any, *, depth: int = 4) -> Any:
    if depth <= 0:
        return _truncate_progress_text(_compact_json_text(value), limit=420)
    if isinstance(value, Mapping):
        return {
            str(key): _agent_log_event_detail(item, depth=depth - 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        limit = 16
        items = [_agent_log_event_detail(item, depth=depth - 1) for item in value[:limit]]
        if len(value) > limit:
            items.append({"omitted": len(value) - limit})
        return items
    if isinstance(value, str):
        return _truncate_progress_text(value, limit=1200)
    return value


def _compact_json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _workflow_node_overlay_source(
    root: Path,
    run_dir: Path,
    node_run: Mapping[str, Any] | None,
) -> tuple[str, str, Mapping[str, Any] | list[Any]] | None:
    candidates: list[tuple[int, str, str]] = []
    if node_run:
        for item in _json_list(node_run.get("outputs")):
            path = item.get("path")
            if not isinstance(path, str) or not path:
                continue
            output_type = str(item.get("type") or "")
            format_id = str(item.get("format_id") or "")
            kind = _workflow_overlay_kind(output_type, format_id, path)
            if kind:
                candidates.append((_workflow_overlay_priority(kind), kind, path))
    for filename in ("page_spec.json", "elements.json", "candidates.json", "element_analysis.json"):
        path = _case_relative_path(root, run_dir / "output" / filename)
        kind = _workflow_overlay_kind("", "", path)
        if kind:
            candidates.append((_workflow_overlay_priority(kind) + 10, kind, path))

    seen: set[str] = set()
    for _, kind, relative_path in sorted(candidates, key=lambda item: item[0]):
        if relative_path in seen:
            continue
        seen.add(relative_path)
        path = _resolve_case_path(root, relative_path)
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        inferred_kind = _workflow_overlay_kind_from_payload(payload, fallback=kind)
        if _workflow_viewer_elements_from_payload(payload, inferred_kind, root=root):
            return inferred_kind, relative_path, payload
    return None


def _workflow_overlay_kind(output_type: str, format_id: str, path: str) -> str:
    probe = f"{output_type} {format_id} {path}".lower()
    if "page_spec" in probe or path.endswith("page_spec.json"):
        return "page_spec"
    if "element_candidates" in probe or path.endswith("candidates.json"):
        return "element_candidates"
    if "element_plans" in probe or path.endswith("elements.json"):
        return "element_plans"
    if "asset_packages" in probe or path.endswith("asset_packages.json"):
        return "asset_packages"
    if "element_analysis" in probe or path.endswith("element_analysis.json"):
        return "element_analysis"
    return ""


def _workflow_overlay_kind_from_payload(payload: object, *, fallback: str) -> str:
    if isinstance(payload, Mapping):
        schema = str(payload.get("schema") or "")
        if schema == "drawai.asset_packages.v1" or (fallback == "asset_packages" and "asset_packages" in payload):
            return "asset_packages"
        if schema == "drawai.page_spec.v1":
            return "page_spec"
        if "element_candidate" in schema or "candidates" in payload:
            return "element_candidates"
        if "element_plan" in schema or "run_package" in schema:
            return "element_plans"
        if "asset_packages" in payload:
            return "asset_packages"
        if "element_analysis" in schema:
            return "element_analysis"
    return fallback


def _workflow_overlay_priority(kind: str) -> int:
    return {
        "page_spec": 10,
        "element_plans": 20,
        "asset_packages": 25,
        "element_candidates": 30,
        "element_analysis": 40,
    }.get(kind, 100)


def _workflow_viewer_elements_from_payload(
    payload: Mapping[str, Any] | list[Any],
    kind: str,
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    if kind == "page_spec":
        items = payload.get("elements", []) if isinstance(payload, Mapping) else payload
        return [
            element
            for index, item in enumerate(_json_list(items))
            if (element := _workflow_viewer_element_from_page_spec(item, index)) is not None
        ]
    if kind == "element_candidates":
        items = payload.get("candidates", []) if isinstance(payload, Mapping) else payload
        return [
            element
            for index, item in enumerate(_json_list(items))
            if (element := _workflow_viewer_element_from_candidate(item, index)) is not None
        ]
    if kind == "element_plans":
        items = payload.get("elements", []) if isinstance(payload, Mapping) else payload
        return [
            element
            for index, item in enumerate(_json_list(items))
            if (element := _workflow_viewer_element_from_plan(item, index)) is not None
        ]
    if kind == "element_analysis":
        items = payload.get("elements", []) if isinstance(payload, Mapping) else payload
        return [
            element
            for index, item in enumerate(_json_list(items))
            if (element := _workflow_viewer_element_from_analysis(item, index)) is not None
        ]
    if kind == "asset_packages":
        items = payload.get("asset_packages", []) if isinstance(payload, Mapping) else payload
        page_elements_by_id = _workflow_page_spec_items_by_id(root) if root is not None else {}
        return [
            element
            for index, item in enumerate(_json_list(items))
            if (element := _workflow_viewer_element_from_asset_package(item, index, page_elements_by_id)) is not None
        ]
    return []


def _workflow_viewer_asset_packages_from_payload(payload: Mapping[str, Any] | list[Any]) -> list[dict[str, Any]]:
    items = payload.get("asset_packages", []) if isinstance(payload, Mapping) else payload
    return [dict(item) for item in _json_list(items) if isinstance(item, Mapping)]


def _workflow_viewer_asset_packages_from_output(root: Path, run_dir: Path) -> list[dict[str, Any]]:
    output_dir = run_dir / "output"
    elements_dir = output_dir / "elements"
    if not elements_dir.is_dir():
        return []
    prefix = _case_relative_path(root, output_dir)
    packages: list[dict[str, Any]] = []
    for package_path in sorted(elements_dir.glob("*/asset_package.json")):
        payload = _read_json_object_if_exists(package_path)
        if not payload:
            continue
        packages.append(_workflow_viewer_package_with_prefixed_paths(payload, prefix))
    return packages


def _workflow_viewer_package_with_prefixed_paths(package: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    payload = dict(package)
    payload["files"] = [_prefix_workflow_viewer_relpath(prefix, item) for item in _string_sequence(payload.get("files"))]
    active_result = payload.get("active_result")
    if isinstance(active_result, Mapping):
        payload["active_result"] = _workflow_viewer_result_with_prefixed_paths(active_result, prefix)
    payload["all_results"] = [
        _workflow_viewer_result_with_prefixed_paths(item, prefix) for item in _json_list(payload.get("all_results")) if isinstance(item, Mapping)
    ]
    return payload


def _workflow_viewer_result_with_prefixed_paths(result: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    payload = dict(result)
    path = payload.get("path")
    if isinstance(path, str):
        payload["path"] = _prefix_workflow_viewer_relpath(prefix, path)
    payload["files"] = [
        _workflow_viewer_file_ref_with_prefixed_path(item, prefix) for item in _json_list(payload.get("files")) if isinstance(item, Mapping)
    ]
    return payload


def _workflow_viewer_file_ref_with_prefixed_path(item: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    payload = dict(item)
    path = payload.get("path")
    if isinstance(path, str):
        payload["path"] = _prefix_workflow_viewer_relpath(prefix, path)
    return payload


def _prefix_workflow_viewer_relpath(prefix: str, path: str) -> str:
    if not path or path.startswith("/") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", path):
        return path
    if path.startswith(prefix + "/"):
        return path
    return f"{prefix}/{path}"


def _workflow_viewer_element_from_page_spec(item: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    bbox = _coerce_bbox_xywh(item.get("box_px"), item.get("geometry"))
    if bbox is None:
        return None
    build = item.get("build")
    build_mapping = build if isinstance(build, Mapping) else {}
    element_id = str(item.get("id") or f"E{index + 1:03d}")
    kind = str(item.get("kind") or "unknown")
    role = str(item.get("role") or kind)
    return _workflow_viewer_element(
        element_id=element_id,
        bbox=bbox,
        element_type=kind,
        source_candidate_ids=_page_spec_source_ids(item) or (element_id,),
        confidence=_confidence_label(item.get("confidence")),
        processing_type=str(build_mapping.get("processing_type") or build_mapping.get("mode") or "page_spec"),
        object_type=role,
        review_status="page_spec",
        created_by_stage=str(_mapping_value(item.get("metadata"), "created_by_stage") or "page_spec"),
        change_reason=str(_mapping_value(item.get("metadata"), "change_reason") or "PageSpec element."),
        z_order=_int_or_default(item.get("z_index"), index),
        geometry=item.get("geometry"),
        parameters=build_mapping.get("parameters") if isinstance(build_mapping.get("parameters"), Mapping) else {},
    )


def _workflow_viewer_element_from_candidate(item: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    bbox = _coerce_bbox_xywh(item.get("bbox"), item.get("geometry"))
    if bbox is None:
        return None
    candidate_id = str(item.get("candidate_id") or f"C{index + 1:03d}")
    element_type = str(item.get("element_type") or item.get("type") or "candidate")
    source_parser = str(item.get("source_parser") or "parser")
    text = str(item.get("text") or "").strip()
    return _workflow_viewer_element(
        element_id=candidate_id,
        bbox=bbox,
        element_type=element_type,
        source_candidate_ids=(candidate_id,),
        confidence=_confidence_label(item.get("confidence")),
        processing_type=source_parser,
        object_type=element_type,
        review_status="parser_candidate",
        created_by_stage=source_parser,
        change_reason=text or source_parser,
        z_order=index,
        geometry=item.get("geometry"),
    )


def _workflow_viewer_element_from_plan(item: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    bbox = _coerce_bbox_xywh(item.get("bbox"), item.get("geometry"))
    if bbox is None:
        return None
    intent = item.get("processing_intent")
    intent_mapping = intent if isinstance(intent, Mapping) else {}
    element_type = str(item.get("element_type") or item.get("type") or intent_mapping.get("object_type") or "element")
    processing_type = str(intent_mapping.get("processing_type") or "planned")
    object_type = str(intent_mapping.get("object_type") or element_type)
    source_ids = _string_sequence(item.get("source_candidate_ids"))
    element_id = str(item.get("element_id") or item.get("box_id") or f"E{index + 1:03d}")
    return _workflow_viewer_element(
        element_id=element_id,
        bbox=bbox,
        element_type=element_type,
        source_candidate_ids=source_ids,
        confidence=_confidence_label(item.get("confidence")),
        processing_type=processing_type,
        object_type=object_type,
        review_status=str(item.get("review_status") or "node_output"),
        created_by_stage=str(item.get("created_by_stage") or "workflow"),
        change_reason=str(item.get("change_reason") or item.get("reason") or "Element plan output."),
        z_order=_int_or_default(item.get("z_order"), index),
        geometry=item.get("geometry"),
        parameters=intent_mapping.get("parameters") if isinstance(intent_mapping.get("parameters"), Mapping) else {},
    )


def _workflow_viewer_element_from_analysis(item: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    bbox = _coerce_bbox_xyxy_to_xywh(item.get("bbox"), item.get("geometry"))
    if bbox is None:
        return None
    element_id = str(item.get("box_id") or item.get("element_id") or f"A{index + 1:03d}")
    element_type = str(item.get("type") or item.get("element_type") or item.get("visual_role") or "analysis")
    processing_type = str(item.get("source_strategy") or item.get("category") or item.get("processing_type") or "analysis")
    source_ids = _string_sequence(item.get("source_candidate_ids")) or (element_id,)
    return _workflow_viewer_element(
        element_id=element_id,
        bbox=bbox,
        element_type=element_type,
        source_candidate_ids=source_ids,
        confidence=_confidence_label(item.get("confidence")),
        processing_type=processing_type,
        object_type=element_type,
        review_status="agent_analysis",
        created_by_stage="agent",
        change_reason=str(item.get("reason") or item.get("change_reason") or "Agent analysis output."),
        z_order=index,
        geometry=item.get("geometry"),
    )


def _workflow_viewer_element_from_asset_package(
    item: Mapping[str, Any],
    index: int,
    page_elements_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    element_id = str(item.get("element_id") or item.get("asset_id") or f"A{index + 1:03d}")
    page_element = page_elements_by_id.get(element_id)
    if isinstance(page_element, Mapping):
        viewer_element = _workflow_viewer_element_from_page_spec(page_element, index)
        if viewer_element is None:
            return None
        processor_type = str(item.get("processor_type") or viewer_element["processing_intent"]["processing_type"])
        viewer_element["processing_intent"]["processing_type"] = processor_type
        viewer_element["review_status"] = str(item.get("status") or "asset_package")
        viewer_element["created_by_stage"] = "asset_prepare"
        viewer_element["change_reason"] = _asset_package_summary(item, processor_type)
        return viewer_element

    bbox = _asset_package_bbox(item)
    if bbox is None:
        return None
    processor_type = str(item.get("processor_type") or "asset_package")
    source_ids = _asset_package_source_ids(item) or (element_id,)
    return _workflow_viewer_element(
        element_id=element_id,
        bbox=bbox,
        element_type="asset",
        source_candidate_ids=source_ids,
        confidence="unknown",
        processing_type=processor_type,
        object_type="asset",
        review_status=str(item.get("status") or "asset_package"),
        created_by_stage="asset_prepare",
        change_reason=_asset_package_summary(item, processor_type),
        z_order=index,
        geometry={"kind": "bbox", "bbox": [bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]]},
    )


def _workflow_viewer_element(
    *,
    element_id: str,
    bbox: tuple[float, float, float, float],
    element_type: str,
    source_candidate_ids: tuple[str, ...],
    confidence: str,
    processing_type: str,
    object_type: str,
    review_status: str,
    created_by_stage: str,
    change_reason: str,
    z_order: int,
    geometry: object,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    geometry_payload = geometry if isinstance(geometry, Mapping) else {"kind": "bbox", "bbox": list(bbox)}
    return {
        "schema": "drawai.viewer_element.v1",
        "element_id": element_id,
        "source_candidate_ids": list(source_candidate_ids),
        "element_type": element_type,
        "bbox": list(bbox),
        "geometry": dict(geometry_payload),
        "z_order": z_order,
        "confidence": confidence,
        "processing_intent": {
            "object_type": object_type,
            "processing_type": processing_type,
            "parameters": dict(parameters or {}),
        },
        "review_status": review_status,
        "created_by_stage": created_by_stage,
        "change_reason": change_reason,
    }


def _page_spec_source_ids(item: Mapping[str, Any]) -> tuple[str, ...]:
    source_refs = item.get("source_refs")
    if isinstance(source_refs, list | tuple):
        ids: list[str] = []
        for ref in source_refs:
            if isinstance(ref, Mapping) and isinstance(ref.get("id"), str) and ref["id"]:
                ids.append(ref["id"])
        if ids:
            return tuple(ids)
    return ()


def _workflow_page_spec_items_by_id(root: Path | None) -> dict[str, Mapping[str, Any]]:
    if root is None:
        return {}
    page_spec_path = root / "page_spec.json"
    if not page_spec_path.is_file():
        return {}
    payload = json.loads(page_spec_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        return {}
    items = payload.get("elements")
    if not isinstance(items, list | tuple):
        return {}
    page_elements: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        element_id = item.get("id")
        if isinstance(element_id, str) and element_id:
            page_elements[element_id] = item
    return page_elements


def _asset_package_bbox(item: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    for metadata in (
        _mapping_value(item.get("metadata"), "last_run_metadata"),
        _mapping_value(_mapping_value(item.get("active_result"), "metadata"), "crop_bbox_xyxy"),
    ):
        if isinstance(metadata, Mapping):
            bbox = _coerce_bbox_xyxy_to_xywh(metadata.get("crop_bbox_xyxy"))
            if bbox is not None:
                return bbox
        else:
            bbox = _coerce_bbox_xyxy_to_xywh(metadata)
            if bbox is not None:
                return bbox
    return None


def _asset_package_source_ids(item: Mapping[str, Any]) -> tuple[str, ...]:
    runs = item.get("processor_runs")
    if not isinstance(runs, list | tuple) or not runs:
        return ()
    first_run = runs[0]
    if not isinstance(first_run, Mapping):
        return ()
    input_refs = first_run.get("input_refs")
    if not isinstance(input_refs, Mapping):
        return ()
    return _string_sequence(input_refs.get("source_candidate_ids"))


def _asset_package_summary(item: Mapping[str, Any], processor_type: str) -> str:
    status = str(item.get("status") or "unknown")
    asset_id = str(item.get("asset_id") or "")
    if asset_id:
        return f"Asset {asset_id} prepared with {processor_type}; status={status}."
    return f"Asset prepared with {processor_type}; status={status}."


def _mapping_value(value: object, key: str) -> object:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _coerce_bbox_xywh(value: object, geometry: object = None) -> tuple[float, float, float, float] | None:
    numbers = _number_tuple4(value)
    if numbers is not None and numbers[2] >= 0 and numbers[3] >= 0:
        return numbers
    if isinstance(geometry, Mapping) and geometry.get("kind") == "bbox":
        bbox = _number_tuple4(geometry.get("bbox"))
        if bbox is None:
            return None
        x1, y1, x2, y2 = bbox
        return (x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))
    return None


def _coerce_bbox_xyxy_to_xywh(value: object, geometry: object = None) -> tuple[float, float, float, float] | None:
    bbox = _number_tuple4(value)
    if bbox is None and isinstance(geometry, Mapping) and geometry.get("kind") == "bbox":
        bbox = _number_tuple4(geometry.get("bbox"))
    if bbox is None:
        return None
    x1, y1, x2, y2 = bbox
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    return (left, top, max(0.0, right - left), max(0.0, bottom - top))


def _number_tuple4(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    except (TypeError, ValueError):
        return None


def _confidence_label(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int | float):
        return f"{float(value):.3f}"
    return "unknown"


def _int_or_default(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _json_list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _read_json_object_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def _case_relative_path(root: Path, path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return resolved.relative_to(root.expanduser().resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"case file path is outside case root: {path}") from exc


def _case_file_record(case_id: str, root: Path, label: str, relative_path: str) -> dict[str, Any]:
    path = _resolve_case_path(root, relative_path)
    exists = path.exists() and path.is_file()
    stat = path.stat() if exists else None
    return {
        "label": label,
        "relative_path": relative_path,
        "exists": exists,
        "media_type": _media_type(path),
        "size_bytes": stat.st_size if stat is not None else 0,
        "updated_at": int(stat.st_mtime) if stat is not None else None,
        "url": _case_file_url(case_id, relative_path) if exists else "",
    }


def _case_file_url(case_id: str, relative_path: str) -> str:
    return f"/api/cases/{case_id}/files/{urllib.parse.quote(relative_path, safe='/')}"


def _case_figure_path(case: CaseRecord) -> Path:
    run_root = Path(case.run_root)
    figure = run_root / "inputs" / "figure.png"
    if figure.is_file():
        return figure
    return Path(case.source_image_path)


def _resolve_case_path(root: Path, relative_path: str | Path) -> Path:
    root_resolved = root.expanduser().resolve()
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise HTTPException(status_code=400, detail="case file path must be relative")
    resolved = (root_resolved / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="case file path is outside case root") from exc
    return resolved


def _media_type(path: Path) -> str:
    if path.suffix.lower() == ".svg":
        return "image/svg+xml"
    if path.suffix.lower() == ".json":
        return "application/json"
    if path.suffix.lower() == ".md":
        return "text/markdown"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _include_agents_param(request: Request) -> bool:
    raw = request.query_params.get("include_agents")
    return True if raw is None else _as_bool(raw)


def _refresh_agents_param(request: Request) -> bool:
    return _as_bool(request.query_params.get("refresh_agents"))


def _workbench_agent_discovery_snapshot(app: FastAPI, *, refresh: bool = False) -> list[dict[str, Any]]:
    if refresh:
        app.state.workbench_agent_discovery_snapshot = discover_workbench_agents()
    return [dict(agent) for agent in app.state.workbench_agent_discovery_snapshot]


def _batch_execution_mode(value: Any) -> BatchExecutionMode:
    mode = str(value or "default").strip().lower()
    if mode not in {"default", "agent", "llm"}:
        raise HTTPException(status_code=400, detail="execution_mode must be default, agent, or llm")
    return mode  # type: ignore[return-value]


def _batch_agent_settings(value: Any, workspace: str | Path):
    if value in (None, ""):
        return read_workbench_agent_settings(workspace)
    payload = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="agent_settings must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise HTTPException(status_code=400, detail="agent_settings must be a JSON object")
    try:
        return normalize_workbench_agent_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _optional_positive_float_env(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
