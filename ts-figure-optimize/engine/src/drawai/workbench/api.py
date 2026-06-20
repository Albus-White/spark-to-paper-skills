from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import posixpath
import re
import shutil
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from lxml import etree

from .assets import process_asset_plan_elements, read_asset_draft, validate_asset_plan, write_asset_draft
from ..codex_python_sdk_imagegen import (
    CodexPythonSdkImageGenError,
    CodexImageGenResult,
    invoke_codex_python_sdk_image_edit,
    invoke_codex_python_sdk_imagegen,
)
from ..config import load_drawai_config
from ..http_utils import urlopen_direct_for_loopback
from ..rmbg_client import RemoteRmbgClient
from .models import CaseRecord, WorkbenchSettings
from .runner import WorkbenchRunner, create_case_config
from .store import WorkbenchStore

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
}

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ],
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

    @app.post("/api/imagegen/generations")
    async def generate_images(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="image generation payload must be an object")
        normalized = _normalize_image_generation_payload(payload)
        if _image_generation_provider(payload) == "codex":
            return _call_codex_image_generation(normalized, store=resolved_store)
        api_url = _image_generation_api_url(payload.get("api_base_url") or payload.get("base_url"))
        api_key = str(payload.get("api_key") or "").strip() or None
        return _call_image_generation_upstream(normalized, api_url=api_url, api_key=api_key)

    @app.post("/api/imagegen/edits")
    async def edit_image(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="image edit payload must be an object")
        if _image_generation_provider(payload) != "codex":
            raise HTTPException(status_code=400, detail="image edits currently require provider=codex")
        normalized = _normalize_image_edit_payload(payload)
        return _call_codex_image_edit(normalized, store=resolved_store)

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
        batch = resolved_store.create_batch(
            name=str(payload.get("name") or "DrawAI batch"),
            input_mode=input_mode,  # type: ignore[arg-type]
            max_concurrent_cases=max_cases,
            auto_run_svg_after_analysis=_as_bool(payload.get("auto_run_svg_after_analysis")),
            config_path=base_config,
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
            config_path = create_case_config(
                base_config_path=base_config,
                source_image=source,
                output_dir=case.run_root,
                target_path=Path(case.run_root) / "drawai.config.yaml",
                sam3_base_url=resolved_settings.sam3_base_url,
                ocr_base_url=resolved_settings.ocr_base_url,
                ocr_timeout_seconds=resolved_settings.ocr_timeout_seconds,
                rmbg_base_url=resolved_settings.rmbg_base_url,
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
            "case": case.to_api(),
            "stage_runs": [stage.to_api() for stage in resolved_store.list_stage_runs(case_id)],
            "artifacts": [artifact.to_api() for artifact in resolved_store.list_artifacts(case_id)],
        }

    @app.get("/api/cases/{case_id}/progress")
    def get_case_progress(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        root = Path(case.run_root)
        stage_runs = [stage.to_api() for stage in resolved_store.list_stage_runs(case_id)]
        return {
            "case": case.to_api(),
            "stage_runs": stage_runs,
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
        _get_case_or_404(resolved_store, case_id)
        payload = await _optional_json(request)
        run_svg = _as_bool(payload.get("run_svg")) if payload else False
        try:
            plan = resolved_runner.approve_case(case_id, run_svg=run_svg)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"asset_plan": plan, "case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/run-stage")
    async def run_stage(case_id: str, request: Request) -> dict[str, Any]:
        _get_case_or_404(resolved_store, case_id)
        payload = await request.json()
        stage = str(payload.get("stage") or "")
        if stage not in {"analysis", "asset_analyze", "materialize", "svg", "export"}:
            raise HTTPException(status_code=400, detail="stage must be analysis, asset_analyze, materialize, svg, or export")
        try:
            resolved_runner.submit_rerun(case_id, stage)  # type: ignore[arg-type]
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/cancel")
    def cancel_case(case_id: str) -> dict[str, Any]:
        case = _get_case_or_404(resolved_store, case_id)
        resolved_store.update_case_status(case_id, status="canceled", phase=case.phase, stage=case.stage)
        return {"case": resolved_store.get_case(case_id).to_api()}

    @app.post("/api/cases/{case_id}/retry")
    def retry_case(case_id: str) -> dict[str, Any]:
        _get_case_or_404(resolved_store, case_id)
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
    return normalized


def _normalize_image_edit_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    source_image_path = str(payload.get("source_image_path") or payload.get("image_path") or "").strip()
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


def _image_generation_provider(payload: Mapping[str, Any]) -> str:
    provider = str(payload.get("provider") or payload.get("image_provider") or "api").strip().lower()
    if provider in {"openai", "images", "image-api"}:
        return "api"
    if provider == "codex":
        return "codex"
    if provider and provider != "api":
        raise HTTPException(status_code=400, detail="provider must be api or codex")
    return "api"


def _call_codex_image_generation(payload: Mapping[str, Any], *, store: WorkbenchStore) -> dict[str, Any]:
    n = int(payload.get("n") or 1)
    output_root = _codex_imagegen_output_dir(store.workspace, "generations")
    runtime_config = _codex_imagegen_runtime_config(payload)
    results: list[CodexImageGenResult] = []
    try:
        for index in range(1, n + 1):
            prompt = _codex_generation_prompt(payload, variant_index=index, variant_count=n)
            output_dir = output_root / f"variant-{index:03d}"
            output_dir.mkdir(parents=True, exist_ok=True)
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
    )


def _call_codex_image_edit(payload: Mapping[str, Any], *, store: WorkbenchStore) -> dict[str, Any]:
    output_dir = _codex_imagegen_output_dir(store.workspace, "edits")
    runtime_config = _codex_imagegen_runtime_config(payload)
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


def _codex_imagegen_runtime_config(payload: Mapping[str, Any]) -> dict[str, Any]:
    timeout = (
        _optional_positive_float_env("DRAWAI_CODEX_IMAGEGEN_TIMEOUT_SECONDS")
        or _optional_positive_float_env("DRAWAI_IMAGEGEN_TIMEOUT_SECONDS")
        or 300.0
    )
    runtime_config: dict[str, Any] = {"timeout_seconds": timeout}
    reasoning_effort = str(os.environ.get("DRAWAI_CODEX_IMAGEGEN_REASONING_EFFORT") or "").strip()
    if reasoning_effort:
        runtime_config["reasoning_effort"] = reasoning_effort
    model_name = _codex_imagegen_model_name(payload)
    if model_name:
        runtime_config["model_name"] = model_name
    return runtime_config


def _codex_imagegen_model_name(payload: Mapping[str, Any]) -> str:
    model_name = str(payload.get("codex_model") or payload.get("model") or "").strip()
    if model_name.startswith("gpt-image-"):
        return ""
    return model_name


def _codex_generation_prompt(payload: Mapping[str, Any], *, variant_index: int, variant_count: int) -> str:
    lines = [
        "DrawAI image generation request.",
        f"Primary request: {str(payload.get('prompt') or '').strip()}",
        "",
        "Generation settings selected in the DrawAI UI:",
        f"- Requested size/aspect: {payload.get('size')}",
        f"- Quality preference: {payload.get('quality')}",
        f"- Background preference: {payload.get('background')}",
        f"- Output format preference: {payload.get('output_format')}",
        f"- Requested image count: {variant_count}",
    ]
    if variant_count > 1:
        lines.append(f"- This tool call should produce image {variant_index} of {variant_count}; create a distinct useful variant without making a collage.")
    if str(payload.get("background") or "").lower() == "transparent":
        lines.append(
            "- Transparent background was requested. If true alpha is unavailable, keep the subject isolated on a clean removable background; do not draw a checkerboard pattern."
        )
    lines.extend([
        "",
        "Use the built-in Codex image generation tool for exactly one output image.",
        "Do not render these settings as visible text unless the primary request explicitly asks for text.",
    ])
    return "\n".join(lines)


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
