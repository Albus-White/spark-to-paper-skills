from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from .artifacts import DrawAiArtifactPaths, prepare_artifact_paths, write_json
from .domain.box_ir import build_raw_box_ir, build_svg_template_ir, merge_box_ir
from .config import DrawAiPipelineConfig
from .image_normalization import normalize_input_image
from .ocr_provider import clamp_ocr_boxes_to_canvas
from .overlays import render_semantic_overlay
from .pipeline import (
    PipelineInvoker,
    STAGE_ORDER,
    _artifact_summary,
    _box_merge_diagnostics,
    _check_svg_to_ppt,
    _default_rmbg_client,
    _extract_ocr_boxes,
    _load_config,
    _load_normalized_size,
    _load_prompt_runs,
    _raw_regions_payload_items,
    _read_json_file,
    _release_runtime_if_supported,
    _reset_run_owned_outputs,
    _sam_boxes_by_prompt,
    _validate_or_raise,
    run_drawai_pipeline_from_stage,
)
from .sam3_client import JsonTransport, run_sam3_prompt_plan
from .svg_to_ppt_check import CompilerCallable

PUBLIC_STAGE_ORDER = (
    "prepare",
    "detect_structure",
    "detect_text",
    "assemble_boxir",
    "asset_plan",
    "asset_analyze",
    "asset_materialize",
    "svg",
    "export",
)

BoxIrAssemblySources = Literal["both", "structure", "text", "auto"]


def run_public_stage(
    config_path_or_config: str | Path | DrawAiPipelineConfig,
    stage: str,
    *,
    sources: BoxIrAssemblySources = "both",
    sam3_transport: JsonTransport | None = None,
    ocr_provider: Any | None = None,
    rmbg_client: Any | None = None,
    svg_invoker: PipelineInvoker | None = None,
    svg_to_ppt_compiler: CompilerCallable | None = None,
    parallel: bool = True,
) -> dict[str, Any]:
    cfg = _load_config(config_path_or_config, validate_input_exists=False)
    paths = prepare_artifact_paths(cfg.input.output_dir)
    if stage == "all":
        return run_public_pipeline(
            cfg,
            sources=sources,
            sam3_transport=sam3_transport,
            ocr_provider=ocr_provider,
            rmbg_client=rmbg_client,
            svg_invoker=svg_invoker,
            svg_to_ppt_compiler=svg_to_ppt_compiler,
            parallel=parallel,
        )
    if stage not in PUBLIC_STAGE_ORDER:
        raise ValueError(f"stage must be one of {', '.join((*PUBLIC_STAGE_ORDER, 'all'))}; got {stage!r}")
    if stage == "prepare":
        _run_prepare(cfg, paths)
    elif stage == "detect_structure":
        _run_detect_structure(cfg, paths, sam3_transport=sam3_transport)
    elif stage == "detect_text":
        _run_detect_text(cfg, paths, ocr_provider=ocr_provider)
    elif stage == "assemble_boxir":
        _run_assemble_boxir(cfg, paths, sources=sources)
    elif stage == "asset_plan":
        return _run_low_level_public_stage(
            cfg,
            "asset_decisions_completed",
            "asset_plan",
            sources=sources,
        )
    elif stage == "asset_materialize":
        return _run_low_level_public_stage(
            cfg,
            "assets_materialized",
            "asset_materialize",
            sources=sources,
            rmbg_client=rmbg_client,
        )
    elif stage == "asset_analyze":
        return _run_low_level_public_stage(
            cfg,
            "codex_run0_asset_analysis_completed",
            "asset_analyze",
            sources=sources,
        )
    elif stage == "svg":
        return _run_low_level_public_stage(
            cfg,
            "assets_materialized",
            "svg",
            to_stage="svg_generated",
            sources=sources,
            rmbg_client=rmbg_client,
            svg_invoker=svg_invoker,
        )
    elif stage == "export":
        return _run_low_level_public_stage(
            cfg,
            "svg_to_ppt_exported",
            "export",
            sources=sources,
            svg_to_ppt_compiler=svg_to_ppt_compiler,
        )
    summary = _public_summary("ok", cfg, paths, stage, sources=sources)
    write_json(paths.pipeline_summary_json, summary)
    return summary


def run_public_pipeline(
    config_path_or_config: str | Path | DrawAiPipelineConfig,
    *,
    sources: BoxIrAssemblySources = "both",
    sam3_transport: JsonTransport | None = None,
    ocr_provider: Any | None = None,
    rmbg_client: Any | None = None,
    svg_invoker: PipelineInvoker | None = None,
    svg_to_ppt_compiler: CompilerCallable | None = None,
    parallel: bool = True,
) -> dict[str, Any]:
    cfg = _load_config(config_path_or_config, validate_input_exists=False)
    paths = prepare_artifact_paths(cfg.input.output_dir)
    _run_prepare(cfg, paths)
    resolved_sources = _resolve_sources(paths, sources)
    if resolved_sources in {"both", "structure"} and resolved_sources in {"both", "text"} and parallel:
        with ThreadPoolExecutor(max_workers=2) as executor:
            structure_future = executor.submit(_run_detect_structure, cfg, paths, sam3_transport=sam3_transport)
            text_future = executor.submit(_run_detect_text, cfg, paths, ocr_provider=ocr_provider)
            structure_future.result()
            text_future.result()
    else:
        if resolved_sources in {"both", "structure"}:
            _run_detect_structure(cfg, paths, sam3_transport=sam3_transport)
        if resolved_sources in {"both", "text"}:
            _run_detect_text(cfg, paths, ocr_provider=ocr_provider)
    _run_assemble_boxir(cfg, paths, sources=resolved_sources)
    summary = _run_low_level_public_stage(cfg, "asset_decisions_completed", "asset_plan", sources=resolved_sources)
    if summary.get("status") != "ok":
        return _failed_public_pipeline_summary(summary, paths)
    summary = _run_low_level_public_stage(
        cfg,
        "codex_run0_asset_analysis_completed",
        "asset_analyze",
        sources=resolved_sources,
    )
    if summary.get("status") != "ok":
        return _failed_public_pipeline_summary(summary, paths)
    summary = _run_low_level_public_stage(
        cfg,
        "assets_materialized",
        "asset_materialize",
        sources=resolved_sources,
        rmbg_client=rmbg_client,
    )
    if summary.get("status") != "ok":
        return _failed_public_pipeline_summary(summary, paths)
    summary = _run_low_level_public_stage(
        cfg,
        "svg_generated",
        "svg",
        sources=resolved_sources,
        svg_invoker=svg_invoker,
    )
    if summary.get("status") != "ok":
        return _failed_public_pipeline_summary(summary, paths)
    summary = _run_low_level_public_stage(
        cfg,
        "svg_to_ppt_exported",
        "export",
        sources=resolved_sources,
        svg_to_ppt_compiler=svg_to_ppt_compiler,
    )
    if summary.get("status") != "ok":
        return _failed_public_pipeline_summary(summary, paths)
    summary = _public_summary("ok", cfg, paths, "all", sources=resolved_sources)
    summary["public_stages"] = list(PUBLIC_STAGE_ORDER)
    write_json(paths.pipeline_summary_json, summary)
    return summary


def _run_prepare(cfg: DrawAiPipelineConfig, paths: DrawAiArtifactPaths) -> None:
    _reset_run_owned_outputs(paths)
    if not cfg.input.image.exists():
        raise FileNotFoundError(f"input.image does not exist: {cfg.input.image}")
    normalize_input_image(cfg.input, paths)


def _run_detect_structure(
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    *,
    sam3_transport: JsonTransport | None,
) -> None:
    if not paths.figure_image.exists():
        raise FileNotFoundError(f"prepare must run before detect_structure: {paths.figure_image}")
    sam3_result = run_sam3_prompt_plan(
        cfg.sam3,
        paths.figure_image,
        paths,
        transport=sam3_transport,
    )
    write_json(paths.sam_boxes_by_prompt_json, _sam_boxes_by_prompt(sam3_result))
    _release_runtime_if_supported(sam3_transport)


def _run_detect_text(
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    *,
    ocr_provider: Any | None,
) -> None:
    if not paths.figure_image.exists():
        raise FileNotFoundError(f"prepare must run before detect_text: {paths.figure_image}")
    normalized_size = _load_normalized_size(paths)
    ocr_payload = _extract_ocr_boxes(cfg, paths.figure_image, ocr_provider)
    ocr_payload = clamp_ocr_boxes_to_canvas(
        ocr_payload,
        canvas_width=normalized_size[0],
        canvas_height=normalized_size[1],
    )
    write_json(paths.ocr_boxes_json, ocr_payload)
    _release_runtime_if_supported(ocr_provider)


def _run_assemble_boxir(
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    *,
    sources: BoxIrAssemblySources,
) -> None:
    resolved_sources = _resolve_sources(paths, sources)
    normalized_size = _load_normalized_size(paths)
    has_structure = resolved_sources in {"both", "structure"}
    has_text = resolved_sources in {"both", "text"}
    if has_structure:
        raw_regions_payload = _read_json_file(paths.raw_regions_json, "SAM3 raw regions")
        prompt_runs = _load_prompt_runs(paths, raw_regions_payload)
        raw_regions = _raw_regions_payload_items(raw_regions_payload)
        if not raw_regions:
            raw_regions = _regions_from_prompt_runs(prompt_runs)
    else:
        prompt_runs = []
        raw_regions = []
    raw_box_ir = build_raw_box_ir(
        canvas=normalized_size,
        source_image=paths.figure_image,
        normalized_long_edge=max(normalized_size),
        prompt_runs=prompt_runs,
        raw_regions=raw_regions,
    )
    write_json(paths.box_ir_raw_json, raw_box_ir)
    merged_box_ir, merge_trace = merge_box_ir(raw_box_ir)
    write_json(paths.merge_trace_json, merge_trace)
    _validate_or_raise(merged_box_ir, "merged layout IR")
    write_json(paths.box_ir_merged_json, merged_box_ir)
    write_json(paths.box_merge_diagnostics_json, _box_merge_diagnostics(raw_box_ir, merged_box_ir, merge_trace))
    render_semantic_overlay(paths.figure_image, merged_box_ir, paths.semantic_overlay_png)
    render_semantic_overlay(paths.figure_image, merged_box_ir, paths.semantic_overlay_legend_png, draw_legend=True)

    final_box_ir = dict(merged_box_ir)
    if has_text:
        ocr_payload = _read_json_file(paths.ocr_boxes_json, "OCR boxes")
        final_box_ir["ocr_text_boxes"] = ocr_payload.get("ocr_text_boxes", [])
    else:
        final_box_ir["ocr_text_boxes"] = []
    _validate_or_raise(final_box_ir, "final layout IR")
    write_json(paths.box_ir_json, final_box_ir)
    write_json(paths.svg_template_ir_json, build_svg_template_ir(final_box_ir))
    render_semantic_overlay(paths.figure_image, final_box_ir, paths.final_semantic_overlay_png)
    render_semantic_overlay(
        paths.figure_image,
        final_box_ir,
        paths.final_semantic_overlay_legend_png,
        draw_legend=True,
    )


def _run_low_level_public_stage(
    cfg: DrawAiPipelineConfig,
    low_level_stage: str,
    public_stage: str,
    *,
    to_stage: str | None = None,
    sources: BoxIrAssemblySources,
    rmbg_client: Any | None = None,
    svg_invoker: PipelineInvoker | None = None,
    svg_to_ppt_compiler: CompilerCallable | None = None,
) -> dict[str, Any]:
    summary = run_drawai_pipeline_from_stage(
        cfg,
        low_level_stage,
        to_stage=to_stage or low_level_stage,
        rmbg_client=rmbg_client,
        svg_invoker=svg_invoker,
        svg_to_ppt_compiler=svg_to_ppt_compiler,
    )
    summary["public_stage"] = public_stage
    summary["sources"] = sources
    write_json(prepare_artifact_paths(cfg.input.output_dir).pipeline_summary_json, summary)
    return summary


def _failed_public_pipeline_summary(summary: dict[str, Any], paths: DrawAiArtifactPaths) -> dict[str, Any]:
    summary["public_stages"] = list(PUBLIC_STAGE_ORDER)
    write_json(paths.pipeline_summary_json, summary)
    return summary


def _resolve_sources(paths: DrawAiArtifactPaths, sources: BoxIrAssemblySources) -> Literal["both", "structure", "text"]:
    if sources == "auto":
        has_structure = paths.raw_regions_json.exists()
        has_text = paths.ocr_boxes_json.exists()
        if has_structure and has_text:
            return "both"
        if has_structure:
            return "structure"
        if has_text:
            return "text"
        raise FileNotFoundError("No structure or text detection artifacts exist for assemble_boxir --sources auto")
    if sources not in {"both", "structure", "text"}:
        raise ValueError("sources must be one of both, structure, text, auto")
    return sources


def _regions_from_prompt_runs(prompt_runs: list[Any]) -> list[dict[str, Any]]:
    raw_regions: list[dict[str, Any]] = []
    for run in prompt_runs:
        if not isinstance(run, dict):
            continue
        prompt_id = str(run.get("prompt_id") or "unknown")
        regions = run.get("regions") if isinstance(run.get("regions"), list) else []
        for region in regions:
            payload = dict(region) if isinstance(region, dict) else {"value": region}
            payload.setdefault("source_prompt", prompt_id)
            raw_regions.append(payload)
    return raw_regions


def _public_summary(
    status: str,
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    stage: str,
    *,
    sources: BoxIrAssemblySources,
) -> dict[str, Any]:
    summary = {
        "schema": "drawai.public_stage_summary.v1",
        "status": status,
        "public_stage": stage,
        "sources": sources,
        "config_path": str(cfg.config_path) if cfg.config_path is not None else None,
        "output_dir": str(paths.root),
        "artifacts": _artifact_summary(paths),
    }
    if stage == "all":
        summary["stages"] = list(STAGE_ORDER)
    return summary
