from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import traceback
from collections import Counter
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from PIL import Image

from .artifacts import DrawAiArtifactPaths, prepare_artifact_paths, write_json, write_stage_status
from .acp_agent_presets import acp_agent_label
from .asset_materialization import materialize_run0_refined_assets
from .asset_manifest_utils import (
    extend_asset_manifest_for_svg_export,
    iter_manifest_image_items,
    native_backfill_validation_assets_for_export,
)
from .asset_policy import (
    analyze_asset_crop,
    decide_asset_policy,
    detect_asset_components,
    refine_asset_policy_with_components,
)
from .asset_selection_loop import (
    AssetSelectionError,
    SVG_RECOVERABLE_ASSETS_SCHEMA,
    apply_svg_recoverability_to_asset_decisions,
    build_initial_asset_decisions,
)
from .domain.box_ir import build_raw_box_ir, build_svg_template_ir, merge_box_ir, normalize_box_type, validate_box_ir
from .config import DrawAiPipelineConfig, load_drawai_config
from .core import DagRunner
from .image_normalization import normalize_input_image
from . import model_runtime
from .ocr_provider import build_ocr_provider, clamp_ocr_boxes_to_canvas
from .overlays import render_semantic_overlay, render_visual_template_reference
from .rmbg_client import RemoteRmbgClient
from .sam3_client import JsonTransport, run_sam3_prompt_plan
from .stages import FileBackedStageOptions, build_file_backed_run_context, build_file_backed_stage_specs
from .svg_generation_loop import SvgGenerationError, run_svg_generation_loop
from .svg_to_ppt_check import CompilerCallable
from .v2.stages import V2_STAGE_ORDER, V2StageOptions, build_v2_run_context, build_v2_stage_specs

PipelineInvoker = Callable[..., Any]

HIGH_OVERLAP_DIFFERENT_TYPE_IOU_THRESHOLD = 0.85
HIGH_OVERLAP_DIFFERENT_TYPE_SMALLER_OVERLAP_THRESHOLD = 0.98
HIGH_OVERLAP_DIFFERENT_TYPE_AREA_SIMILARITY_THRESHOLD = 0.75
MERGE_DIAGNOSTIC_SAMPLE_LIMIT = 12

STAGE_ORDER = [
    "config_loaded",
    "input_normalized",
    "sam3_completed",
    "box_ir_merged",
    "semantic_overlay_rendered",
    "ocr_completed",
    "asset_decisions_completed",
    "codex_run0_asset_analysis_completed",
    "assets_materialized",
    "svg_generated",
    "svg_to_ppt_exported",
    "completed",
]

RERUNNABLE_STAGE_ORDER = [
    stage
    for stage in STAGE_ORDER
    if stage not in {"config_loaded", "completed"}
]

V2_RERUNNABLE_STAGE_ORDER = list(V2_STAGE_ORDER)

V2_STAGE_ALIASES = {
    "input_normalized": "prepare",
    "detect_structure": "parse_elements",
    "detect_text": "parse_elements",
    "sam3_completed": "parse_elements",
    "ocr_completed": "parse_elements",
    "assemble_boxir": "fuse_elements",
    "box_ir_merged": "fuse_elements",
    "semantic_overlay_rendered": "fuse_elements",
    "asset_plan": "plan_assets",
    "asset_decisions_completed": "plan_assets",
    "asset_analyze": "refine_elements",
    "codex_run0_asset_analysis_completed": "refine_elements",
    "asset_materialize": "process_assets",
    "assets_materialized": "process_assets",
    "svg": "compose_svg",
    "svg_generated": "compose_svg",
    "svg_to_ppt_exported": "export",
    "completed": "package_run",
}

STAGE_IO_SCHEMA = "drawai.stage_io_manifest.v1"

STAGE_INFERENCE_SLOTS: dict[str, list[str]] = {
    "sam3_completed": ["sam3_transport"],
    "ocr_completed": ["ocr_provider"],
    "assets_materialized": ["rmbg_client"],
    "codex_run0_asset_analysis_completed": ["model_runtime"],
    "svg_generated": ["svg_invoker", "model_runtime"],
    "svg_to_ppt_exported": ["svg_to_ppt_compiler"],
}

STAGE_CONFIG_SECTIONS: dict[str, list[str]] = {
    "input_normalized": ["input"],
    "sam3_completed": ["sam3"],
    "ocr_completed": ["ocr"],
    "asset_decisions_completed": ["asset_selection", "asset_policy"],
    "assets_materialized": ["asset_materialization"],
    "codex_run0_asset_analysis_completed": ["model_runtime"],
    "svg_generated": ["svg", "model_runtime"],
    "svg_to_ppt_exported": ["svg_to_ppt"],
}


def run_drawai_pipeline(
    config_path_or_config: str | Path | DrawAiPipelineConfig,
    *,
    sam3_transport: JsonTransport | None = None,
    ocr_provider: Any | None = None,
    rmbg_client: Any | None = None,
    svg_invoker: PipelineInvoker | None = None,
    svg_to_ppt_compiler: CompilerCallable | None = None,
) -> dict[str, Any]:
    try:
        cfg = _load_config(config_path_or_config, validate_input_exists=False)
    except Exception as exc:  # noqa: BLE001 - no output_dir may be recoverable here.
        return _config_load_failure_summary(config_path_or_config, exc)

    paths = prepare_artifact_paths(cfg.input.output_dir)
    if cfg.v2.enabled:
        return _run_v2_pipeline(
            cfg,
            paths,
            options=V2StageOptions(
                sam3_transport=sam3_transport,
                ocr_provider=ocr_provider,
                rmbg_client=rmbg_client,
                svg_invoker=svg_invoker,
                svg_to_ppt_compiler=svg_to_ppt_compiler,
            ),
        )

    _reset_run_owned_outputs(paths)
    completed: list[str] = []
    current_stage = "config_loaded"

    try:
        _mark_stage(paths, current_stage, "running", "Config loaded; preparing artifacts.")
        _mark_stage(paths, current_stage, "ok", "Config loaded.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={"config": cfg.config_path},
            outputs={
                "stage_status": paths.stage_status_json,
                "stage_io_manifest": paths.stage_io_manifest_json,
            },
            execution_mode="full_pipeline",
        )

        current_stage = "input_normalized"
        _mark_stage(paths, current_stage, "running", "Normalizing input image.")
        if not cfg.input.image.exists():
            raise FileNotFoundError(f"input.image does not exist: {cfg.input.image}")
        normalization = normalize_input_image(cfg.input, paths)
        _mark_stage(paths, current_stage, "ok", "Input image normalized.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={"source_image": cfg.input.image, "config": cfg.config_path},
            outputs={
                "original_image": paths.original_image,
                "figure_image": paths.figure_image,
                "source_metadata": paths.source_metadata,
            },
            execution_mode="full_pipeline",
        )

        current_stage = "sam3_completed"
        _mark_stage(paths, current_stage, "running", "Running SAM3 prompt plan.")
        sam3_result = run_sam3_prompt_plan(
            cfg.sam3,
            normalization.figure_image,
            paths,
            transport=sam3_transport,
        )
        write_json(paths.sam_boxes_by_prompt_json, _sam_boxes_by_prompt(sam3_result))
        _mark_stage(paths, current_stage, "ok", "SAM3 prompt plan completed.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={"figure_image": paths.figure_image},
            outputs={
                "raw_regions": paths.raw_regions_json,
                "prompt_runs": paths.prompt_runs_dir,
                "prompt_overlays": paths.sam_prompt_overlays_dir,
                "sam_boxes_by_prompt": paths.sam_boxes_by_prompt_json,
            },
            execution_mode="full_pipeline",
        )
        _release_runtime_if_supported(sam3_transport)

        current_stage = "box_ir_merged"
        _mark_stage(paths, current_stage, "running", "Building and merging raw layout IR.")
        raw_regions = _raw_regions_for_box_ir(sam3_result)
        raw_box_ir = build_raw_box_ir(
            canvas=normalization.normalized_size,
            source_image=normalization.figure_image,
            normalized_long_edge=max(normalization.normalized_size),
            prompt_runs=[_json_safe(run) for run in sam3_result.prompt_runs],
            raw_regions=raw_regions,
        )
        write_json(paths.box_ir_raw_json, raw_box_ir)
        merged_box_ir, merge_trace = merge_box_ir(raw_box_ir)
        write_json(paths.merge_trace_json, merge_trace)
        _validate_or_raise(merged_box_ir, "merged layout IR")
        write_json(paths.box_ir_merged_json, merged_box_ir)
        write_json(paths.box_ir_json, merged_box_ir)
        write_json(paths.box_merge_diagnostics_json, _box_merge_diagnostics(raw_box_ir, merged_box_ir, merge_trace))
        _mark_stage(paths, current_stage, "ok", "raw layout IR merged.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={
                "source_metadata": paths.source_metadata,
                "raw_regions": paths.raw_regions_json,
                "prompt_runs": paths.prompt_runs_dir,
            },
            outputs={
                "raw_box_ir": paths.box_ir_raw_json,
                "merged_box_ir": paths.box_ir_merged_json,
                "box_ir_compat": paths.box_ir_json,
                "merge_trace": paths.merge_trace_json,
                "box_merge_diagnostics": paths.box_merge_diagnostics_json,
            },
            execution_mode="full_pipeline",
        )

        current_stage = "semantic_overlay_rendered"
        _mark_stage(paths, current_stage, "running", "Rendering semantic overlay.")
        overlay_legend = render_semantic_overlay(
            normalization.figure_image,
            merged_box_ir,
            paths.semantic_overlay_png,
        )
        render_semantic_overlay(
            normalization.figure_image,
            merged_box_ir,
            paths.semantic_overlay_legend_png,
            draw_legend=True,
        )
        write_json(paths.box_ir_dir / "semantic_overlay_legend.json", overlay_legend)
        _mark_stage(paths, current_stage, "ok", "Semantic overlay rendered.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={"figure_image": paths.figure_image, "merged_box_ir": paths.box_ir_merged_json},
            outputs={
                "semantic_overlay": paths.semantic_overlay_png,
                "semantic_overlay_legend_image": paths.semantic_overlay_legend_png,
                "semantic_overlay_legend": paths.box_ir_dir / "semantic_overlay_legend.json",
            },
            execution_mode="full_pipeline",
        )

        current_stage = "ocr_completed"
        _mark_stage(paths, current_stage, "running", "Extracting OCR text boxes.")
        ocr_payload = _extract_ocr_boxes(cfg, normalization.figure_image, ocr_provider)
        ocr_payload = clamp_ocr_boxes_to_canvas(
            ocr_payload,
            canvas_width=normalization.normalized_size[0],
            canvas_height=normalization.normalized_size[1],
        )
        write_json(paths.ocr_boxes_json, ocr_payload)
        final_box_ir = dict(merged_box_ir)
        final_box_ir["ocr_text_boxes"] = ocr_payload.get("ocr_text_boxes", [])
        _validate_or_raise(final_box_ir, "final layout IR")
        write_json(paths.box_ir_json, final_box_ir)
        svg_template_ir = build_svg_template_ir(final_box_ir)
        write_json(paths.svg_template_ir_json, svg_template_ir)
        render_semantic_overlay(
            normalization.figure_image,
            final_box_ir,
            paths.final_semantic_overlay_png,
        )
        render_semantic_overlay(
            normalization.figure_image,
            final_box_ir,
            paths.final_semantic_overlay_legend_png,
            draw_legend=True,
        )
        _mark_stage(paths, current_stage, "ok", "OCR text boxes injected into layout IR.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={"figure_image": paths.figure_image, "merged_box_ir": paths.box_ir_merged_json},
            outputs={
                "ocr_boxes": paths.ocr_boxes_json,
                "final_box_ir": paths.box_ir_json,
                "svg_template_ir": paths.svg_template_ir_json,
                "final_semantic_overlay": paths.final_semantic_overlay_png,
                "final_semantic_overlay_legend_image": paths.final_semantic_overlay_legend_png,
            },
            execution_mode="full_pipeline",
        )
        _release_runtime_if_supported(ocr_provider)

        current_stage = "asset_decisions_completed"
        _mark_stage(paths, current_stage, "running", "Selecting SVG-recoverable gray-box assets.")
        initial_asset_decisions = build_initial_asset_decisions(final_box_ir)
        write_json(paths.initial_asset_decisions_json, initial_asset_decisions)
        asset_recovery_reference_legend = render_visual_template_reference(
            normalization.figure_image,
            final_box_ir,
            initial_asset_decisions,
            paths.asset_recovery_reference_png,
            asset_selection_config=cfg.asset_selection,
        )
        render_visual_template_reference(
            normalization.figure_image,
            final_box_ir,
            initial_asset_decisions,
            paths.asset_recovery_reference_legend_png,
            asset_selection_config=cfg.asset_selection,
            draw_legend=True,
        )
        write_json(paths.svg_dir / "asset_recovery_reference_legend.json", asset_recovery_reference_legend)
        asset_policy_report: dict[str, Any] | None = None
        if cfg.asset_policy.enabled:
            asset_policy_report = _build_asset_policy_report(
                normalization.figure_image,
                final_box_ir,
                initial_asset_decisions,
            )
            write_json(_asset_policy_report_path(paths), asset_policy_report)

        svg_recoverable_assets = _svg_recoverability_from_asset_policy(
            initial_asset_decisions,
            asset_policy_report,
            source="asset_policy" if cfg.asset_policy.enabled else "asset_policy_disabled",
        )
        write_json(paths.svg_recoverable_assets_json, svg_recoverable_assets)
        asset_decisions = apply_svg_recoverability_to_asset_decisions(
            initial_asset_decisions,
            svg_recoverable_assets,
        )
        write_json(paths.asset_decisions_json, asset_decisions)
        svg_generation_reference_legend = render_visual_template_reference(
            normalization.figure_image,
            final_box_ir,
            asset_decisions,
            paths.svg_generation_reference_png,
            asset_selection_config=cfg.asset_selection,
            asset_policy_report=asset_policy_report,
            draw_labels=False,
        )
        render_visual_template_reference(
            normalization.figure_image,
            final_box_ir,
            asset_decisions,
            paths.svg_generation_reference_legend_png,
            asset_selection_config=cfg.asset_selection,
            asset_policy_report=asset_policy_report,
            draw_legend=True,
        )
        write_json(paths.svg_dir / "svg_generation_reference_legend.json", svg_generation_reference_legend)
        template_reference_legend = render_visual_template_reference(
            normalization.figure_image,
            final_box_ir,
            asset_decisions,
            paths.template_reference_png,
            asset_selection_config=cfg.asset_selection,
            asset_policy_report=asset_policy_report,
            semantic_types=("content_box",),
        )
        render_visual_template_reference(
            normalization.figure_image,
            final_box_ir,
            asset_decisions,
            paths.template_reference_legend_png,
            asset_selection_config=cfg.asset_selection,
            asset_policy_report=asset_policy_report,
            draw_legend=True,
            semantic_types=("content_box",),
        )
        write_json(paths.svg_dir / "template_reference_legend.json", template_reference_legend)
        _mark_stage(paths, current_stage, "ok", "Asset decisions completed.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={"figure_image": paths.figure_image, "box_ir": paths.box_ir_json},
            outputs=_asset_decision_stage_outputs(paths, include_asset_policy=cfg.asset_policy.enabled),
            execution_mode="full_pipeline",
        )

        current_stage = "codex_run0_asset_analysis_completed"
        _mark_stage(paths, current_stage, "running", "Running Codex run0 asset analysis.")
        _run_codex_run0_asset_analysis(cfg, paths)
        _mark_stage(paths, current_stage, "ok", "Codex run0 asset analysis completed.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={
                "figure_image": paths.figure_image,
                "box_ir": paths.box_ir_json,
                "asset_decisions": paths.asset_decisions_json,
            },
            outputs=_codex_run0_asset_analysis_stage_outputs(paths),
            execution_mode="full_pipeline",
        )

        current_stage = "assets_materialized"
        _mark_stage(paths, current_stage, "running", "Materializing confirmed run0-refined assets.")
        asset_manifest = materialize_run0_refined_assets(
            paths.figure_image,
            _read_json_file(paths.element_analysis_json, "Codex run0 element analysis"),
            paths.assets_dir,
            rmbg_config=cfg.asset_materialization.rmbg,
            rmbg_client=rmbg_client or _default_rmbg_client(cfg),
        )
        _mark_stage(paths, current_stage, "ok", "Run0-refined assets materialized.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs=_assets_materialized_stage_inputs(paths),
            outputs={
                "assets_dir": paths.assets_dir,
                "crops_dir": paths.crops_dir,
                "asset_manifest": paths.asset_manifest_json,
            },
            execution_mode="full_pipeline",
        )
        _release_runtime_if_supported(rmbg_client)

        current_stage = "svg_generated"
        _mark_stage(paths, current_stage, "running", "Generating and validating semantic SVG.")
        svg_invoker_context = (
            nullcontext(svg_invoker)
            if svg_invoker is not None
            else _default_svg_invoker(cfg, paths)
        )
        with svg_invoker_context as active_svg_invoker:
            svg_result = run_svg_generation_loop(
                box_ir=final_box_ir,
                figure_path=paths.figure_image,
                reference_image_path=paths.template_reference_png,
                asset_manifest=asset_manifest,
                output_dir=paths.svg_dir,
                max_attempts=cfg.svg.max_attempts,
                invoker=active_svg_invoker,
                runtime_config=_svg_runtime_config(cfg) if svg_invoker is None else None,
                staged_generation=cfg.svg.staged_generation,
                visual_review_rounds=cfg.svg.visual_review_rounds,
                template_ir=svg_template_ir,
                text_rendering=cfg.svg.text_rendering,
            )
        _copy_if_exists(Path(svg_result["artifacts"]["validation_report"]), paths.svg_validation_report_json)
        _mark_stage(paths, current_stage, "ok", "Semantic SVG generated.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={
                "box_ir": paths.box_ir_json,
                "figure_image": paths.figure_image,
                "visual_template_reference": paths.template_reference_png,
                "asset_manifest": paths.asset_manifest_json,
                "svg_template_ir": paths.svg_template_ir_json,
            },
            outputs=_svg_stage_outputs(paths),
            execution_mode="full_pipeline",
        )

        current_stage = "svg_to_ppt_exported"
        _mark_stage(paths, current_stage, "running", "Checking SVG-to-PPT compatibility.")
        ppt_report = _check_svg_to_ppt(cfg, paths, asset_manifest, svg_to_ppt_compiler)
        write_json(paths.svg_to_ppt_export_report_json, ppt_report)
        if ppt_report.get("status") != "ok":
            raise RuntimeError("SVG-to-PPTX export failed.")
        _mark_stage(paths, current_stage, "ok", "SVG-to-PPT compatibility checked.")
        completed.append(current_stage)
        _record_stage_io(
            paths,
            cfg,
            current_stage,
            inputs={"semantic_svg": paths.semantic_svg, "asset_manifest": paths.asset_manifest_json},
            outputs={"svg_to_ppt_export_report": paths.svg_to_ppt_export_report_json},
            execution_mode="full_pipeline",
        )

        current_stage = "completed"
        _mark_stage(paths, current_stage, "running", "Writing final pipeline summary.")
        summary = _summary("ok", cfg, paths, completed + [current_stage])
        write_json(paths.pipeline_summary_json, summary)
        _mark_stage(paths, current_stage, "ok", "Pipeline completed.")
        return summary
    except Exception as exc:  # noqa: BLE001 - top-level pipeline report boundary.
        _mark_stage(paths, current_stage, "failed", _sanitize_summary_string(f"{type(exc).__name__}: {exc}"))
        summary = _summary(
            "failed",
            cfg,
            paths,
            completed,
            failed_stage=current_stage,
            exception=exc,
        )
        write_json(paths.pipeline_summary_json, summary)
        return summary


def _run_v2_pipeline(
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    *,
    options: V2StageOptions,
) -> dict[str, Any]:
    _reset_run_owned_outputs(
        paths,
        preserve_external_refinement_analysis=cfg.v2.refine.enabled,
    )
    completed: list[str] = []
    current_stage = "prepare"

    try:
        runner = DagRunner(build_v2_stage_specs(V2_RERUNNABLE_STAGE_ORDER, options=options))
        context = build_v2_run_context(cfg, paths, options=options)

        def before_stage(stage) -> None:
            nonlocal current_stage
            current_stage = stage.stage_id
            _mark_stage(paths, current_stage, "running", f"Running v2 stage {current_stage}.")

        def after_stage(stage, _result) -> None:
            _mark_stage(paths, stage.stage_id, "ok", f"v2 stage {stage.stage_id} completed.")
            completed.append(stage.stage_id)

        runner.run(context, before_stage=before_stage, after_stage=after_stage)

        summary = _summary("ok", cfg, paths, completed)
        summary["execution_mode"] = "v2_file_stage_runner"
        summary["v2_enabled"] = True
        write_json(paths.pipeline_summary_json, summary)
        return summary
    except Exception as exc:  # noqa: BLE001 - top-level pipeline report boundary.
        _mark_stage(paths, current_stage, "failed", _sanitize_summary_string(f"{type(exc).__name__}: {exc}"))
        summary = _summary(
            "failed",
            cfg,
            paths,
            completed,
            failed_stage=current_stage,
            exception=exc,
        )
        summary["execution_mode"] = "v2_file_stage_runner"
        summary["v2_enabled"] = True
        write_json(paths.pipeline_summary_json, summary)
        return summary


def run_drawai_pipeline_from_stage(
    config_path_or_config: str | Path | DrawAiPipelineConfig,
    from_stage: str,
    *,
    to_stage: str | None = None,
    sam3_transport: JsonTransport | None = None,
    ocr_provider: Any | None = None,
    rmbg_client: Any | None = None,
    svg_invoker: PipelineInvoker | None = None,
    svg_to_ppt_compiler: CompilerCallable | None = None,
) -> dict[str, Any]:
    try:
        cfg = _load_config(config_path_or_config, validate_input_exists=False)
    except Exception as exc:  # noqa: BLE001 - no output_dir may be recoverable here.
        return _config_load_failure_summary(config_path_or_config, exc)

    paths = prepare_artifact_paths(cfg.input.output_dir)
    if cfg.v2.enabled:
        return _run_v2_pipeline_from_stage(
            cfg,
            paths,
            from_stage,
            to_stage=to_stage,
            options=V2StageOptions(
                sam3_transport=sam3_transport,
                ocr_provider=ocr_provider,
                rmbg_client=rmbg_client,
                svg_invoker=svg_invoker,
                svg_to_ppt_compiler=svg_to_ppt_compiler,
            ),
        )

    completed: list[str] = []
    current_stage = from_stage

    try:
        stage_range = _stage_range(from_stage, to_stage)
        _reset_outputs_from_stage(paths, from_stage)
        options = FileBackedStageOptions(
            sam3_transport=sam3_transport,
            ocr_provider=ocr_provider,
            rmbg_client=rmbg_client,
            svg_invoker=svg_invoker,
            svg_to_ppt_compiler=svg_to_ppt_compiler,
        )
        runner = DagRunner(build_file_backed_stage_specs(stage_range, options=options))
        context = build_file_backed_run_context(cfg, paths, options=options)

        def before_stage(stage) -> None:
            nonlocal current_stage
            current_stage = stage.stage_id
            _mark_stage(paths, current_stage, "running", f"Running file-backed stage {current_stage}.")

        def after_stage(stage, _result) -> None:
            _mark_stage(paths, stage.stage_id, "ok", f"File-backed stage {stage.stage_id} completed.")
            completed.append(stage.stage_id)

        runner.run(context, before_stage=before_stage, after_stage=after_stage)

        summary = _summary("ok", cfg, paths, completed)
        summary["execution_mode"] = "file_stage_runner"
        summary["from_stage"] = from_stage
        summary["to_stage"] = stage_range[-1]
        write_json(paths.pipeline_summary_json, summary)
        return summary
    except Exception as exc:  # noqa: BLE001 - top-level stage runner report boundary.
        _mark_stage(paths, current_stage, "failed", _sanitize_summary_string(f"{type(exc).__name__}: {exc}"))
        summary = _summary(
            "failed",
            cfg,
            paths,
            completed,
            failed_stage=current_stage,
            exception=exc,
        )
        summary["execution_mode"] = "file_stage_runner"
        summary["from_stage"] = from_stage
        summary["to_stage"] = to_stage
        write_json(paths.pipeline_summary_json, summary)
        return summary


def _run_v2_pipeline_from_stage(
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    from_stage: str,
    *,
    to_stage: str | None,
    options: V2StageOptions,
) -> dict[str, Any]:
    completed: list[str] = []
    current_stage = _canonical_v2_stage(from_stage)

    try:
        stage_range = _v2_stage_range(from_stage, to_stage)
        _reset_v2_outputs_from_stage(
            paths,
            stage_range[0],
            preserve_external_refinement_analysis=(
                cfg.v2.refine.enabled and "refine_elements" in stage_range
            ),
        )
        runner = DagRunner(build_v2_stage_specs(stage_range, options=options))
        context = build_v2_run_context(cfg, paths, options=options)

        def before_stage(stage) -> None:
            nonlocal current_stage
            current_stage = stage.stage_id
            _mark_stage(paths, current_stage, "running", f"Running v2 file-backed stage {current_stage}.")

        def after_stage(stage, _result) -> None:
            _mark_stage(paths, stage.stage_id, "ok", f"v2 file-backed stage {stage.stage_id} completed.")
            completed.append(stage.stage_id)

        runner.run(context, before_stage=before_stage, after_stage=after_stage)

        summary = _summary("ok", cfg, paths, completed)
        summary["execution_mode"] = "v2_file_stage_runner"
        summary["from_stage"] = stage_range[0]
        summary["to_stage"] = stage_range[-1]
        summary["v2_enabled"] = True
        if from_stage != stage_range[0]:
            summary["from_stage_alias"] = from_stage
        if to_stage is not None and to_stage != stage_range[-1]:
            summary["to_stage_alias"] = to_stage
        write_json(paths.pipeline_summary_json, summary)
        return summary
    except Exception as exc:  # noqa: BLE001 - top-level stage runner report boundary.
        _mark_stage(paths, current_stage, "failed", _sanitize_summary_string(f"{type(exc).__name__}: {exc}"))
        summary = _summary(
            "failed",
            cfg,
            paths,
            completed,
            failed_stage=current_stage,
            exception=exc,
        )
        summary["execution_mode"] = "v2_file_stage_runner"
        summary["from_stage"] = from_stage
        summary["to_stage"] = to_stage
        summary["v2_enabled"] = True
        write_json(paths.pipeline_summary_json, summary)
        return summary


def _stage_range(from_stage: str, to_stage: str | None) -> list[str]:
    if from_stage not in RERUNNABLE_STAGE_ORDER:
        raise ValueError(
            f"from_stage must be one of {', '.join(RERUNNABLE_STAGE_ORDER)}; got {from_stage!r}"
        )
    resolved_to_stage = to_stage or RERUNNABLE_STAGE_ORDER[-1]
    if resolved_to_stage not in RERUNNABLE_STAGE_ORDER:
        raise ValueError(
            f"to_stage must be one of {', '.join(RERUNNABLE_STAGE_ORDER)}; got {resolved_to_stage!r}"
        )
    start_index = RERUNNABLE_STAGE_ORDER.index(from_stage)
    end_index = RERUNNABLE_STAGE_ORDER.index(resolved_to_stage)
    if end_index < start_index:
        raise ValueError(f"to_stage {resolved_to_stage!r} is before from_stage {from_stage!r}")
    return RERUNNABLE_STAGE_ORDER[start_index : end_index + 1]


def _v2_stage_range(from_stage: str, to_stage: str | None) -> list[str]:
    resolved_from_stage = _canonical_v2_stage(from_stage)
    resolved_to_stage = _canonical_v2_stage(to_stage) if to_stage is not None else V2_RERUNNABLE_STAGE_ORDER[-1]
    start_index = V2_RERUNNABLE_STAGE_ORDER.index(resolved_from_stage)
    end_index = V2_RERUNNABLE_STAGE_ORDER.index(resolved_to_stage)
    if end_index < start_index:
        raise ValueError(f"to_stage {resolved_to_stage!r} is before from_stage {resolved_from_stage!r}")
    return V2_RERUNNABLE_STAGE_ORDER[start_index : end_index + 1]


def _canonical_v2_stage(stage: str | None) -> str:
    if stage is None:
        return V2_RERUNNABLE_STAGE_ORDER[-1]
    resolved_stage = V2_STAGE_ALIASES.get(stage, stage)
    if resolved_stage not in V2_RERUNNABLE_STAGE_ORDER:
        accepted = ", ".join((*V2_RERUNNABLE_STAGE_ORDER, *V2_STAGE_ALIASES))
        raise ValueError(f"stage must be one of {accepted}; got {stage!r}")
    return resolved_stage


def _run_file_backed_stage(
    stage: str,
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    *,
    sam3_transport: JsonTransport | None,
    ocr_provider: Any | None,
    rmbg_client: Any | None,
    svg_invoker: PipelineInvoker | None,
    svg_to_ppt_compiler: CompilerCallable | None,
) -> None:
    if stage == "input_normalized":
        if not cfg.input.image.exists():
            raise FileNotFoundError(f"input.image does not exist: {cfg.input.image}")
        normalize_input_image(cfg.input, paths)
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={"source_image": cfg.input.image, "config": cfg.config_path},
            outputs={
                "original_image": paths.original_image,
                "figure_image": paths.figure_image,
                "source_metadata": paths.source_metadata,
            },
            execution_mode="file_stage_runner",
        )
        return

    if stage == "sam3_completed":
        _require_path(paths.figure_image, "normalized figure image")
        sam3_result = run_sam3_prompt_plan(
            cfg.sam3,
            paths.figure_image,
            paths,
            transport=sam3_transport,
        )
        write_json(paths.sam_boxes_by_prompt_json, _sam_boxes_by_prompt(sam3_result))
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={"figure_image": paths.figure_image},
            outputs={
                "raw_regions": paths.raw_regions_json,
                "prompt_runs": paths.prompt_runs_dir,
                "prompt_overlays": paths.sam_prompt_overlays_dir,
                "sam_boxes_by_prompt": paths.sam_boxes_by_prompt_json,
            },
            execution_mode="file_stage_runner",
        )
        _release_runtime_if_supported(sam3_transport)
        return

    if stage == "box_ir_merged":
        normalized_size = _load_normalized_size(paths)
        raw_regions_payload = _read_json_file(paths.raw_regions_json, "SAM3 raw regions")
        prompt_runs = _load_prompt_runs(paths, raw_regions_payload)
        raw_box_ir = build_raw_box_ir(
            canvas=normalized_size,
            source_image=paths.figure_image,
            normalized_long_edge=max(normalized_size),
            prompt_runs=prompt_runs,
            raw_regions=_raw_regions_payload_items(raw_regions_payload),
        )
        write_json(paths.box_ir_raw_json, raw_box_ir)
        merged_box_ir, merge_trace = merge_box_ir(raw_box_ir)
        write_json(paths.merge_trace_json, merge_trace)
        _validate_or_raise(merged_box_ir, "merged layout IR")
        write_json(paths.box_ir_merged_json, merged_box_ir)
        write_json(paths.box_ir_json, merged_box_ir)
        write_json(paths.box_merge_diagnostics_json, _box_merge_diagnostics(raw_box_ir, merged_box_ir, merge_trace))
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={
                "source_metadata": paths.source_metadata,
                "raw_regions": paths.raw_regions_json,
                "prompt_runs": paths.prompt_runs_dir,
            },
            outputs={
                "raw_box_ir": paths.box_ir_raw_json,
                "merged_box_ir": paths.box_ir_merged_json,
                "box_ir_compat": paths.box_ir_json,
                "merge_trace": paths.merge_trace_json,
                "box_merge_diagnostics": paths.box_merge_diagnostics_json,
            },
            execution_mode="file_stage_runner",
        )
        return

    if stage == "semantic_overlay_rendered":
        _require_path(paths.figure_image, "normalized figure image")
        merged_box_ir = _read_json_file(paths.box_ir_merged_json, "merged layout IR")
        overlay_legend = render_semantic_overlay(
            paths.figure_image,
            merged_box_ir,
            paths.semantic_overlay_png,
        )
        render_semantic_overlay(
            paths.figure_image,
            merged_box_ir,
            paths.semantic_overlay_legend_png,
            draw_legend=True,
        )
        write_json(paths.box_ir_dir / "semantic_overlay_legend.json", overlay_legend)
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={"figure_image": paths.figure_image, "merged_box_ir": paths.box_ir_merged_json},
            outputs={
                "semantic_overlay": paths.semantic_overlay_png,
                "semantic_overlay_legend_image": paths.semantic_overlay_legend_png,
                "semantic_overlay_legend": paths.box_ir_dir / "semantic_overlay_legend.json",
            },
            execution_mode="file_stage_runner",
        )
        return

    if stage == "ocr_completed":
        _require_path(paths.figure_image, "normalized figure image")
        normalized_size = _load_normalized_size(paths)
        merged_box_ir = _read_json_file(paths.box_ir_merged_json, "merged layout IR")
        ocr_payload = _extract_ocr_boxes(cfg, paths.figure_image, ocr_provider)
        ocr_payload = clamp_ocr_boxes_to_canvas(
            ocr_payload,
            canvas_width=normalized_size[0],
            canvas_height=normalized_size[1],
        )
        write_json(paths.ocr_boxes_json, ocr_payload)
        final_box_ir = dict(merged_box_ir)
        final_box_ir["ocr_text_boxes"] = ocr_payload.get("ocr_text_boxes", [])
        _validate_or_raise(final_box_ir, "final layout IR")
        write_json(paths.box_ir_json, final_box_ir)
        svg_template_ir = build_svg_template_ir(final_box_ir)
        write_json(paths.svg_template_ir_json, svg_template_ir)
        render_semantic_overlay(paths.figure_image, final_box_ir, paths.final_semantic_overlay_png)
        render_semantic_overlay(
            paths.figure_image,
            final_box_ir,
            paths.final_semantic_overlay_legend_png,
            draw_legend=True,
        )
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={"figure_image": paths.figure_image, "merged_box_ir": paths.box_ir_merged_json},
            outputs={
                "ocr_boxes": paths.ocr_boxes_json,
                "final_box_ir": paths.box_ir_json,
                "svg_template_ir": paths.svg_template_ir_json,
                "final_semantic_overlay": paths.final_semantic_overlay_png,
                "final_semantic_overlay_legend_image": paths.final_semantic_overlay_legend_png,
            },
            execution_mode="file_stage_runner",
        )
        _release_runtime_if_supported(ocr_provider)
        return

    if stage == "asset_decisions_completed":
        _require_path(paths.figure_image, "normalized figure image")
        final_box_ir = _read_json_file(paths.box_ir_json, "final layout IR")
        initial_asset_decisions = build_initial_asset_decisions(final_box_ir)
        write_json(paths.initial_asset_decisions_json, initial_asset_decisions)
        asset_recovery_reference_legend = render_visual_template_reference(
            paths.figure_image,
            final_box_ir,
            initial_asset_decisions,
            paths.asset_recovery_reference_png,
            asset_selection_config=cfg.asset_selection,
        )
        render_visual_template_reference(
            paths.figure_image,
            final_box_ir,
            initial_asset_decisions,
            paths.asset_recovery_reference_legend_png,
            asset_selection_config=cfg.asset_selection,
            draw_legend=True,
        )
        write_json(paths.svg_dir / "asset_recovery_reference_legend.json", asset_recovery_reference_legend)
        asset_policy_report: dict[str, Any] | None = None
        if cfg.asset_policy.enabled:
            asset_policy_report = _build_asset_policy_report(
                paths.figure_image,
                final_box_ir,
                initial_asset_decisions,
            )
            write_json(_asset_policy_report_path(paths), asset_policy_report)
        svg_recoverable_assets = _svg_recoverability_from_asset_policy(
            initial_asset_decisions,
            asset_policy_report,
            source="asset_policy" if cfg.asset_policy.enabled else "asset_policy_disabled",
        )
        write_json(paths.svg_recoverable_assets_json, svg_recoverable_assets)
        asset_decisions = apply_svg_recoverability_to_asset_decisions(
            initial_asset_decisions,
            svg_recoverable_assets,
        )
        write_json(paths.asset_decisions_json, asset_decisions)
        svg_generation_reference_legend = render_visual_template_reference(
            paths.figure_image,
            final_box_ir,
            asset_decisions,
            paths.svg_generation_reference_png,
            asset_selection_config=cfg.asset_selection,
            asset_policy_report=asset_policy_report,
            draw_labels=False,
        )
        render_visual_template_reference(
            paths.figure_image,
            final_box_ir,
            asset_decisions,
            paths.svg_generation_reference_legend_png,
            asset_selection_config=cfg.asset_selection,
            asset_policy_report=asset_policy_report,
            draw_legend=True,
        )
        write_json(paths.svg_dir / "svg_generation_reference_legend.json", svg_generation_reference_legend)
        template_reference_legend = render_visual_template_reference(
            paths.figure_image,
            final_box_ir,
            asset_decisions,
            paths.template_reference_png,
            asset_selection_config=cfg.asset_selection,
            asset_policy_report=asset_policy_report,
            semantic_types=("content_box",),
        )
        render_visual_template_reference(
            paths.figure_image,
            final_box_ir,
            asset_decisions,
            paths.template_reference_legend_png,
            asset_selection_config=cfg.asset_selection,
            asset_policy_report=asset_policy_report,
            draw_legend=True,
            semantic_types=("content_box",),
        )
        write_json(paths.svg_dir / "template_reference_legend.json", template_reference_legend)
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={"figure_image": paths.figure_image, "box_ir": paths.box_ir_json},
            outputs=_asset_decision_stage_outputs(paths, include_asset_policy=cfg.asset_policy.enabled),
            execution_mode="file_stage_runner",
        )
        return

    if stage == "assets_materialized":
        _require_path(paths.figure_image, "normalized figure image")
        _require_path(paths.element_analysis_json, "Codex run0 element analysis")
        asset_manifest = materialize_run0_refined_assets(
            paths.figure_image,
            _read_json_file(paths.element_analysis_json, "Codex run0 element analysis"),
            paths.assets_dir,
            rmbg_config=cfg.asset_materialization.rmbg,
            rmbg_client=rmbg_client or _default_rmbg_client(cfg),
        )
        write_json(paths.asset_manifest_json, asset_manifest)
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs=_assets_materialized_stage_inputs(paths),
            outputs={
                "assets_dir": paths.assets_dir,
                "crops_dir": paths.crops_dir,
                "asset_manifest": paths.asset_manifest_json,
            },
            execution_mode="file_stage_runner",
        )
        _release_runtime_if_supported(rmbg_client)
        return

    if stage == "codex_run0_asset_analysis_completed":
        _require_path(paths.figure_image, "normalized figure image")
        _require_path(paths.box_ir_json, "final layout IR")
        _require_path(paths.asset_decisions_json, "asset decisions")
        _run_codex_run0_asset_analysis(cfg, paths)
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={
                "figure_image": paths.figure_image,
                "box_ir": paths.box_ir_json,
                "asset_decisions": paths.asset_decisions_json,
            },
            outputs=_codex_run0_asset_analysis_stage_outputs(paths),
            execution_mode="file_stage_runner",
        )
        return

    if stage == "svg_generated":
        final_box_ir = _read_json_file(paths.box_ir_json, "final layout IR")
        asset_manifest = _read_json_file(paths.asset_manifest_json, "asset manifest")
        svg_template_ir = _read_json_file(paths.svg_template_ir_json, "SVG template IR")
        _require_path(paths.figure_image, "normalized figure image")
        _require_path(paths.template_reference_png, "visual template reference image")
        svg_invoker_context = (
            nullcontext(svg_invoker)
            if svg_invoker is not None
            else _default_svg_invoker(cfg, paths)
        )
        with svg_invoker_context as active_svg_invoker:
            svg_result = run_svg_generation_loop(
                box_ir=final_box_ir,
                figure_path=paths.figure_image,
                reference_image_path=paths.template_reference_png,
                asset_manifest=asset_manifest,
                output_dir=paths.svg_dir,
                max_attempts=cfg.svg.max_attempts,
                invoker=active_svg_invoker,
                runtime_config=_svg_runtime_config(cfg) if svg_invoker is None else None,
                staged_generation=cfg.svg.staged_generation,
                visual_review_rounds=cfg.svg.visual_review_rounds,
                template_ir=svg_template_ir,
                text_rendering=cfg.svg.text_rendering,
            )
        _copy_if_exists(Path(svg_result["artifacts"]["validation_report"]), paths.svg_validation_report_json)
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={
                "box_ir": paths.box_ir_json,
                "figure_image": paths.figure_image,
                "visual_template_reference": paths.template_reference_png,
                "asset_manifest": paths.asset_manifest_json,
                "svg_template_ir": paths.svg_template_ir_json,
            },
            outputs=_svg_stage_outputs(paths),
            execution_mode="file_stage_runner",
        )
        return

    if stage == "svg_to_ppt_exported":
        asset_manifest = _read_asset_manifest_for_svg_to_ppt_export(paths)
        _require_path(paths.semantic_svg, "semantic SVG")
        ppt_report = _check_svg_to_ppt(cfg, paths, asset_manifest, svg_to_ppt_compiler)
        write_json(paths.svg_to_ppt_export_report_json, ppt_report)
        if ppt_report.get("status") != "ok":
            raise RuntimeError("SVG-to-PPTX export failed.")
        _record_stage_io(
            paths,
            cfg,
            stage,
            inputs={"semantic_svg": paths.semantic_svg, "asset_manifest": paths.asset_manifest_json},
            outputs={"svg_to_ppt_export_report": paths.svg_to_ppt_export_report_json},
            execution_mode="file_stage_runner",
        )
        return

    raise ValueError(f"Unsupported file-backed stage: {stage}")


def _load_config(
    config_path_or_config: str | Path | DrawAiPipelineConfig,
    *,
    validate_input_exists: bool,
) -> DrawAiPipelineConfig:
    if isinstance(config_path_or_config, DrawAiPipelineConfig):
        return config_path_or_config
    return load_drawai_config(config_path_or_config, validate_input_exists=validate_input_exists)


def _release_runtime_if_supported(runtime: Any | None) -> None:
    if runtime is None:
        return
    release = getattr(runtime, "release_runtime", None)
    if callable(release):
        release()


def _mark_stage(paths: DrawAiArtifactPaths, stage: str, status: str, message: str) -> None:
    write_stage_status(paths, stage, status, message)


def _record_stage_io(
    paths: DrawAiArtifactPaths,
    cfg: DrawAiPipelineConfig,
    stage: str,
    *,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    execution_mode: str,
) -> None:
    manifest = _load_stage_io_manifest(paths, cfg, execution_mode)
    stages = manifest.get("stages")
    if not isinstance(stages, dict):
        stages = {}
    stages[stage] = {
        "stage": stage,
        "execution_mode": execution_mode,
        "inputs": _json_safe(inputs),
        "outputs": _json_safe(outputs),
        "inference_slots": list(STAGE_INFERENCE_SLOTS.get(stage, [])),
        "config_sections": list(STAGE_CONFIG_SECTIONS.get(stage, [])),
    }
    manifest["stages"] = stages
    manifest["latest_stage"] = stage
    manifest["latest_execution_mode"] = execution_mode
    write_json(paths.stage_io_manifest_json, manifest)


def _load_stage_io_manifest(
    paths: DrawAiArtifactPaths,
    cfg: DrawAiPipelineConfig,
    execution_mode: str,
) -> dict[str, Any]:
    if paths.stage_io_manifest_json.exists():
        loaded = _read_json_file(paths.stage_io_manifest_json, "stage I/O manifest")
        if isinstance(loaded, Mapping):
            manifest = dict(loaded)
        else:
            manifest = {}
    else:
        manifest = {}

    prior_mode = manifest.get("execution_mode")
    if isinstance(prior_mode, str) and prior_mode and prior_mode != execution_mode:
        root_execution_mode = "mixed"
    else:
        root_execution_mode = execution_mode

    manifest.update(
        {
            "schema": STAGE_IO_SCHEMA,
            "execution_mode": root_execution_mode,
            "config_path": str(cfg.config_path) if cfg.config_path is not None else None,
            "output_dir": str(paths.root),
            "stage_order": list(STAGE_ORDER),
        }
    )
    if not isinstance(manifest.get("stages"), dict):
        manifest["stages"] = {}
    return manifest


def _asset_decision_stage_outputs(paths: DrawAiArtifactPaths, *, include_asset_policy: bool) -> dict[str, Any]:
    outputs: dict[str, Any] = {
        "initial_asset_decisions": paths.initial_asset_decisions_json,
        "asset_recovery_reference": paths.asset_recovery_reference_png,
        "asset_recovery_reference_legend_image": paths.asset_recovery_reference_legend_png,
        "asset_recovery_reference_legend": paths.svg_dir / "asset_recovery_reference_legend.json",
        "svg_recoverable_assets": paths.svg_recoverable_assets_json,
        "asset_decisions": paths.asset_decisions_json,
        "svg_generation_reference": paths.svg_generation_reference_png,
        "svg_generation_reference_legend_image": paths.svg_generation_reference_legend_png,
        "svg_generation_reference_legend": paths.svg_dir / "svg_generation_reference_legend.json",
        "visual_template_reference": paths.template_reference_png,
        "visual_template_reference_legend_image": paths.template_reference_legend_png,
        "visual_template_reference_legend": paths.svg_dir / "template_reference_legend.json",
    }
    if include_asset_policy:
        outputs["asset_policy_report"] = _asset_policy_report_path(paths)
    return outputs


def _assets_materialized_stage_inputs(paths: DrawAiArtifactPaths) -> dict[str, Any]:
    return {
        "figure_image": paths.figure_image,
        "element_analysis": paths.element_analysis_json,
    }


def _codex_run0_asset_analysis_stage_outputs(paths: DrawAiArtifactPaths) -> dict[str, Any]:
    return {
        "element_analysis_dir": paths.element_analysis_dir,
        "element_analysis": paths.element_analysis_json,
        "element_analysis_request": paths.element_analysis_request_json,
        "element_analysis_validation": paths.element_analysis_validation_json,
        "element_analysis_status": paths.element_analysis_status_json,
        "element_analysis_prompt": paths.element_analysis_prompt_txt,
        "element_analysis_trace": paths.element_analysis_trace_jsonl,
        "asset_plan_overlay": paths.reports_dir / "assemble_debug" / "assets" / "08_asset_plan.png",
    }


def _svg_stage_outputs(paths: DrawAiArtifactPaths) -> dict[str, Any]:
    outputs: dict[str, Any] = {
        "semantic_svg": paths.semantic_svg,
        "rendered_png": paths.rendered_png,
        "attempts": paths.attempts_dir,
        "template_iterations": paths.template_iterations_dir,
        "svg_validation_report": paths.svg_validation_report_json,
    }
    for key, path in (
        ("template_svg", paths.template_svg),
        ("template_rendered_png", paths.template_rendered_png),
    ):
        if path.exists():
            outputs[key] = path
    return outputs


def _read_json_file(path: str | Path, label: str) -> Any:
    json_path = _require_path(path, label)
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_asset_manifest_for_svg_to_ppt_export(paths: DrawAiArtifactPaths) -> Any:
    if paths.asset_manifest_json.exists():
        return _read_json_file(paths.asset_manifest_json, "asset manifest")

    legacy_manifest = paths.root / "svg_to_ooxml" / "assets" / "asset_manifest.json"
    if legacy_manifest.exists():
        manifest = _read_json_file(legacy_manifest, "legacy asset manifest")
        write_json(paths.asset_manifest_json, manifest)
        return manifest

    return _read_json_file(paths.asset_manifest_json, "asset manifest")


def _read_optional_json_file(path: str | Path) -> Any | None:
    json_path = Path(path)
    if not json_path.exists():
        return None
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _require_path(path: str | Path, label: str) -> Path:
    required = Path(path)
    if not required.exists():
        raise FileNotFoundError(f"Required {label} file is missing: {required}")
    return required


def _load_normalized_size(paths: DrawAiArtifactPaths) -> tuple[int, int]:
    metadata = _read_json_file(paths.source_metadata, "source metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("source metadata must be a mapping")
    raw_size = metadata.get("normalized_size")
    if not isinstance(raw_size, (list, tuple)) or len(raw_size) != 2:
        raise ValueError("source metadata must contain normalized_size [width, height]")
    try:
        width = int(raw_size[0])
        height = int(raw_size[1])
    except (TypeError, ValueError) as exc:
        raise ValueError("source metadata normalized_size must contain integers") from exc
    if width <= 0 or height <= 0:
        raise ValueError("source metadata normalized_size must be positive")
    return (width, height)


def _load_prompt_runs(paths: DrawAiArtifactPaths, raw_regions_payload: Any) -> list[Any]:
    prompt_run_paths: list[Path] = []
    if isinstance(raw_regions_payload, Mapping):
        for item in raw_regions_payload.get("prompt_runs", []) or []:
            if not isinstance(item, Mapping):
                continue
            artifact_path = item.get("artifact_path")
            if isinstance(artifact_path, str) and artifact_path:
                prompt_run_paths.append(Path(artifact_path))
    if not prompt_run_paths:
        prompt_run_paths = sorted(paths.prompt_runs_dir.glob("*.json"))
    if not prompt_run_paths:
        raise FileNotFoundError(f"No SAM3 prompt run JSON files found in {paths.prompt_runs_dir}")
    return [_read_json_file(path, "SAM3 prompt run") for path in prompt_run_paths]


def _raw_regions_payload_items(raw_regions_payload: Any) -> list[Any]:
    if isinstance(raw_regions_payload, Mapping):
        raw_regions = raw_regions_payload.get("raw_regions")
        if isinstance(raw_regions, list):
            return raw_regions
    raise ValueError("SAM3 raw regions payload must contain a raw_regions list")


def _raw_regions_for_box_ir(sam3_result: Any) -> list[Any]:
    if getattr(sam3_result, "raw_regions", None):
        return list(sam3_result.raw_regions)
    raw_regions: list[Any] = []
    for run in getattr(sam3_result, "prompt_runs", ()):
        prompt_id = getattr(run, "prompt_id", "unknown")
        for region in getattr(run, "regions", []) or []:
            if isinstance(region, Mapping):
                payload = dict(region)
            else:
                payload = {"value": region}
            payload.setdefault("source_prompt", prompt_id)
            raw_regions.append(payload)
    return raw_regions


def _sam_boxes_by_prompt(sam3_result: Any) -> dict[str, Any]:
    prompts: list[dict[str, Any]] = []
    total_box_count = 0
    for run in getattr(sam3_result, "prompt_runs", ()) or ():
        regions = list(getattr(run, "regions", []) or [])
        raw_regions = list(getattr(run, "raw_regions", []) or [])
        prompts.append(
            {
                "prompt_id": getattr(run, "prompt_id", "unknown"),
                "box_count": len(regions),
                "raw_region_count": len(raw_regions),
                "regions": _json_safe(regions),
                "raw_regions": _json_safe(raw_regions),
                "artifact_path": str(getattr(run, "artifact_path", "")),
                "elapsed_ms": getattr(run, "elapsed_ms", None),
            }
        )
        total_box_count += len(regions)
    return {
        "schema": "drawai.sam3_boxes_by_prompt.v1",
        "total_box_count": total_box_count,
        "prompt_count": len(prompts),
        "prompts": prompts,
    }


def _box_merge_diagnostics(
    raw_box_ir: Mapping[str, Any],
    merged_box_ir: Mapping[str, Any],
    merge_trace: Mapping[str, Any],
) -> dict[str, Any]:
    raw_boxes = [box for box in raw_box_ir.get("boxes", []) if isinstance(box, Mapping)]
    merged_boxes = [box for box in merged_box_ir.get("boxes", []) if isinstance(box, Mapping)]
    decisions = [decision for decision in merge_trace.get("decisions", []) if isinstance(decision, Mapping)]
    warnings = _box_merge_warnings(raw_boxes, merged_boxes, decisions)
    return {
        "schema": "drawai.box_ir.merge_diagnostics.v1",
        "status": "ok" if not warnings else "review",
        "raw_box_count": len(raw_boxes),
        "merged_box_count": len(merged_boxes),
        "removed_or_merged_box_count": max(0, len(raw_boxes) - len(merged_boxes)),
        "raw_count_by_type": dict(sorted(Counter(str(box.get("type", "unknown")) for box in raw_boxes).items())),
        "merged_count_by_type": dict(sorted(Counter(str(box.get("type", "unknown")) for box in merged_boxes).items())),
        "merge_action_counts": dict(sorted(Counter(str(decision.get("action", "unknown")) for decision in decisions).items())),
        "containment_relation_count": sum(1 for decision in decisions if decision.get("action") == "relate"),
        "warnings": warnings,
    }


def _box_merge_warnings(
    raw_boxes: list[Mapping[str, Any]],
    merged_boxes: list[Mapping[str, Any]],
    decisions: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if raw_boxes and not merged_boxes:
        warnings.append({"code": "empty_merge_result", "message": "Raw boxes exist but merge produced no boxes."})
    if len(merged_boxes) > len(raw_boxes):
        warnings.append({"code": "merged_count_exceeds_raw", "message": "Merge produced more boxes than the raw input."})
    missing_source_ids = [
        box.get("id")
        for box in merged_boxes
        if not isinstance(box.get("source_box_ids"), list) or not box.get("source_box_ids")
    ]
    if missing_source_ids:
        warnings.append(
            {
                "code": "missing_source_box_ids",
                "message": "Merged boxes should preserve source_box_ids for traceability.",
                "box_ids": missing_source_ids,
            }
        )
    high_overlap_pairs = _high_overlap_different_type_pairs(merged_boxes)
    if high_overlap_pairs:
        warnings.append(
            {
                "code": "high_overlap_different_type_pairs",
                "message": "Different semantic types have near-duplicate boxes; review merge priority rules.",
                "count": len(high_overlap_pairs),
                "iou_threshold": HIGH_OVERLAP_DIFFERENT_TYPE_IOU_THRESHOLD,
                "smaller_overlap_threshold": HIGH_OVERLAP_DIFFERENT_TYPE_SMALLER_OVERLAP_THRESHOLD,
                "area_similarity_threshold": HIGH_OVERLAP_DIFFERENT_TYPE_AREA_SIMILARITY_THRESHOLD,
                "samples": high_overlap_pairs[:MERGE_DIAGNOSTIC_SAMPLE_LIMIT],
            }
        )
    large_duplicate_clusters = [
        result_id
        for result_id, count in Counter(
            str(decision.get("result_box_id"))
            for decision in decisions
            if decision.get("action") == "merge" and decision.get("result_box_id")
        ).items()
        if count > 20
    ]
    if large_duplicate_clusters:
        warnings.append(
            {
                "code": "large_duplicate_cluster",
                "message": "A merged result accumulated an unusually large number of merge decisions.",
                "result_box_ids": large_duplicate_clusters,
            }
        )
    return warnings


def _high_overlap_different_type_pairs(boxes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(boxes):
        for right in boxes[left_index + 1 :]:
            if left.get("type") == right.get("type"):
                continue
            metrics = _box_overlap_metrics(left.get("bbox"), right.get("bbox"))
            if metrics is None:
                continue
            if (
                metrics["iou"] >= HIGH_OVERLAP_DIFFERENT_TYPE_IOU_THRESHOLD
                or (
                    metrics["smaller_overlap"] >= HIGH_OVERLAP_DIFFERENT_TYPE_SMALLER_OVERLAP_THRESHOLD
                    and metrics["area_similarity"] >= HIGH_OVERLAP_DIFFERENT_TYPE_AREA_SIMILARITY_THRESHOLD
                )
            ):
                pairs.append(
                    {
                        "left_id": left.get("id"),
                        "left_type": left.get("type"),
                        "right_id": right.get("id"),
                        "right_type": right.get("type"),
                        "iou": round(metrics["iou"], 4),
                        "smaller_overlap": round(metrics["smaller_overlap"], 4),
                        "area_similarity": round(metrics["area_similarity"], 4),
                    }
                )
    return pairs


def _box_overlap_metrics(left_bbox: Any, right_bbox: Any) -> dict[str, float] | None:
    left = _numeric_bbox(left_bbox)
    right = _numeric_bbox(right_bbox)
    if left is None or right is None:
        return None
    left_area = _bbox_area(left)
    right_area = _bbox_area(right)
    if left_area <= 0 or right_area <= 0:
        return None
    intersection = _bbox_intersection_area(left, right)
    if intersection <= 0:
        return None
    union = left_area + right_area - intersection
    return {
        "iou": intersection / union if union > 0 else 0.0,
        "smaller_overlap": intersection / min(left_area, right_area),
        "area_similarity": min(left_area, right_area) / max(left_area, right_area),
    }


def _numeric_bbox(raw_bbox: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(value) for value in raw_bbox)
    except (TypeError, ValueError):
        return None
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _bbox_intersection_area(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    return max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0,
        min(left[3], right[3]) - max(left[1], right[1]),
    )


def _extract_ocr_boxes(
    cfg: DrawAiPipelineConfig,
    image_path: Path,
    injected_provider: Any | None,
) -> dict[str, Any]:
    provider = injected_provider or build_ocr_provider(cfg.ocr)
    if hasattr(provider, "extract_boxes"):
        payload = provider.extract_boxes(image_path)
    elif callable(provider):
        payload = provider(image_path=image_path)
    else:
        raise TypeError("ocr_provider must expose extract_boxes(image_path) or be callable")
    if not isinstance(payload, Mapping):
        raise ValueError("OCR provider must return a mapping")
    if not isinstance(payload.get("ocr_text_boxes"), list):
        raise ValueError("OCR provider payload must contain an ocr_text_boxes list")
    return dict(payload)


def _asset_policy_report_path(paths: DrawAiArtifactPaths) -> Path:
    return paths.assets_dir / "asset_policy_report.json"


def _build_asset_policy_report(
    figure_image_path: str | Path,
    box_ir: Mapping[str, Any],
    initial_asset_decisions: Mapping[str, Any],
) -> dict[str, Any]:
    boxes_by_id = _policy_boxes_by_id(box_ir.get("boxes"))
    canvas_size = _canvas_size_for_prompt(box_ir)
    ocr_boxes = box_ir.get("ocr_text_boxes") if isinstance(box_ir.get("ocr_text_boxes"), list) else []
    assets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    with Image.open(figure_image_path) as source_image:
        source = source_image.convert("RGB")
        for decision in initial_asset_decisions.get("decisions", []):
            if not isinstance(decision, Mapping) or decision.get("decision") != "crop_asset":
                continue
            asset_id = decision.get("asset_id")
            box_id = decision.get("box_id")
            if not isinstance(asset_id, str) or not isinstance(box_id, str):
                continue
            box = boxes_by_id.get(box_id)
            if box is None:
                skipped.append({"asset_id": asset_id, "box_id": box_id, "reason": "missing_box"})
                continue
            crop_bbox = _policy_crop_bbox(box.get("bbox"), source.size)
            if crop_bbox is None:
                skipped.append({"asset_id": asset_id, "box_id": box_id, "reason": "invalid_bbox"})
                continue

            crop = source.crop(crop_bbox)
            metrics = analyze_asset_crop(image=crop, box=box, slide_size=canvas_size)
            base_decision = decide_asset_policy(
                asset_id=asset_id,
                role=str(box.get("type") or decision.get("initial_crop_role") or "unknown"),
                metrics=metrics,
            )
            components = detect_asset_components(
                image=crop,
                decision=base_decision,
                asset_box=box,
                ocr_boxes=ocr_boxes,
            )
            policy_decision = refine_asset_policy_with_components(base_decision, components)
            policy_payload = policy_decision.to_dict()
            policy_payload["box_id"] = box_id
            policy_payload["bbox"] = list(crop_bbox)
            policy_payload["current_label"] = _asset_policy_current_label(policy_payload)
            assets.append(policy_payload)

    return {
        "schema": "drawai.asset_policy_report.v1",
        "status": "ok",
        "asset_count": len(assets),
        "skipped_count": len(skipped),
        "render_policy_counts": dict(
            sorted(Counter(str(asset.get("render_policy", "unknown")) for asset in assets).items())
        ),
        "background_policy_counts": dict(
            sorted(Counter(str(asset.get("background_policy", "unknown")) for asset in assets).items())
        ),
        "split_policy_counts": dict(
            sorted(Counter(str(asset.get("split_policy", "unknown")) for asset in assets).items())
        ),
        "active_label_counts": dict(
            sorted(Counter(str(asset.get("current_label", "unknown")) for asset in assets).items())
        ),
        "should_run_rmbg_count": sum(1 for asset in assets if asset.get("should_run_rmbg") is True),
        "assets": assets,
        "skipped": skipped,
    }


def _asset_policy_current_label(asset_policy: Mapping[str, Any]) -> str:
    render_policy = str(asset_policy.get("render_policy") or "")
    background_policy = str(asset_policy.get("background_policy") or "")
    if render_policy == "native_svg":
        return "SVG"
    if render_policy == "hybrid":
        return "COMBO"
    if render_policy == "raster_png":
        return "PNG-T" if background_policy in {"transparent_subject", "split_backplate"} else "PNG-O"
    return "UNKNOWN"


def _svg_recoverability_from_asset_policy(
    initial_asset_decisions: Mapping[str, Any],
    asset_policy_report: Mapping[str, Any] | None,
    *,
    source: str,
) -> dict[str, Any]:
    crop_asset_ids = [
        str(decision.get("asset_id"))
        for decision in initial_asset_decisions.get("decisions", [])
        if isinstance(decision, Mapping)
        and decision.get("decision") == "crop_asset"
        and isinstance(decision.get("asset_id"), str)
    ]
    policy_by_id = _asset_policy_by_asset_id(asset_policy_report)
    recoverable_ids: list[str] = []
    for asset_id in crop_asset_ids:
        policy = policy_by_id.get(asset_id)
        if policy is None:
            continue
        if policy.get("render_policy") == "native_svg":
            recoverable_ids.append(asset_id)
    return {
        "schema": SVG_RECOVERABLE_ASSETS_SCHEMA,
        "recoverable_asset_ids": recoverable_ids,
        "source": source,
    }


def _asset_policy_by_asset_id(asset_policy_report: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(asset_policy_report, Mapping):
        return {}
    assets = asset_policy_report.get("assets")
    if not isinstance(assets, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        asset_id = asset.get("asset_id")
        if isinstance(asset_id, str) and asset_id:
            result[asset_id] = asset
    return result


def _policy_boxes_by_id(raw_boxes: Any) -> dict[str, Mapping[str, Any]]:
    boxes: dict[str, Mapping[str, Any]] = {}
    iterable = raw_boxes if isinstance(raw_boxes, list) else []
    for box in iterable:
        if not isinstance(box, Mapping):
            continue
        box_id = box.get("id")
        if isinstance(box_id, str) and box_id:
            boxes[box_id] = box
    return boxes


def _policy_crop_bbox(raw_bbox: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    bbox = _numeric_bbox(raw_bbox)
    if bbox is None:
        return None
    width, height = image_size
    left = max(0, min(width, round(bbox[0])))
    top = max(0, min(height, round(bbox[1])))
    right = max(0, min(width, round(bbox[2])))
    bottom = max(0, min(height, round(bbox[3])))
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _default_rmbg_client(cfg: DrawAiPipelineConfig) -> RemoteRmbgClient | None:
    rmbg = cfg.asset_materialization.rmbg
    if not rmbg.enabled:
        return None
    base_url = rmbg.base_url.strip() or cfg.sam3.base_url
    return RemoteRmbgClient(base_url)


def _default_svg_invoker(
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
) -> PipelineInvoker:
    return _DefaultSvgInvoker(cfg, paths)


def _svg_runtime_config(cfg: DrawAiPipelineConfig) -> dict[str, Any]:
    runtime_config = cfg.model_runtime.to_runtime_dict()
    runtime_config["timeout_seconds"] = cfg.svg.timeout_seconds
    if cfg.svg.generation_backend == "sdk_tool_loop":
        runtime_config["model_name"] = ""
    return runtime_config


class _DefaultSvgInvoker:
    def __init__(
        self,
        cfg: DrawAiPipelineConfig,
        paths: DrawAiArtifactPaths,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.runtime_config = _svg_runtime_config(cfg)
        self.trace_path = paths.trace_dir / "svg_generation_model.jsonl"
        self._codex_session: Any | None = None

    def __enter__(self) -> "_DefaultSvgInvoker":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self._codex_session is not None:
            self._codex_session.close()
            self._codex_session = None

    def __call__(self, **kwargs: Any) -> str:
        phase = str(kwargs.get("phase") or "single")
        prompt_kwargs = dict(kwargs)
        if self.cfg.svg.generation_backend in {"codex_python_sdk_controlled", "agent_cli", "acp_agent", "tool_agent"}:
            prompt_kwargs["file_context_mode"] = True
            prompt_kwargs["workspace_dir"] = self.paths.root
            if self.cfg.svg.generation_backend == "agent_cli":
                prompt_kwargs["agent_label"] = _agent_cli_label(self.cfg.model_runtime.cli.agent)
            elif self.cfg.svg.generation_backend == "acp_agent":
                prompt_kwargs["agent_label"] = _acp_agent_label(self.cfg.model_runtime.acp.agent)
            elif self.cfg.svg.generation_backend == "tool_agent":
                prompt_kwargs["agent_label"] = "DrawAI Tool Agent"
            else:
                prompt_kwargs["codex_thread_turn_mode"] = True
        prompt = _svg_generation_prompt(prompt_kwargs)
        prompt_path = kwargs.get("prompt_path")
        if prompt_path is not None:
            prompt_output = Path(prompt_path)
            prompt_output.parent.mkdir(parents=True, exist_ok=True)
            prompt_output.write_text(prompt, encoding="utf-8")
        if self.cfg.svg.generation_backend == "codex_python_sdk_controlled":
            return self._invoke_codex_thread(phase=phase, prompt=prompt, kwargs=kwargs)
        if self.cfg.svg.generation_backend == "agent_cli":
            return self._invoke_agent_cli(phase=phase, prompt=prompt, kwargs=kwargs)
        if self.cfg.svg.generation_backend == "acp_agent":
            return self._invoke_acp_agent(phase=phase, prompt=prompt, kwargs=kwargs)
        if self.cfg.svg.generation_backend == "tool_agent":
            return self._invoke_tool_agent(phase=phase, prompt=prompt, kwargs=kwargs)
        if self.cfg.svg.generation_backend == "sdk_tool_loop":
            from .codex_svg_tool_loop import invoke_codex_svg_text

            return invoke_codex_svg_text(
                image_paths=[Path(kwargs["figure_path"]), Path(kwargs["reference_image_path"])],
                prompt=prompt,
                task_name=f"box_ir_semantic_svg.{phase}.v1",
                runtime_config=self.runtime_config,
                trace_path=self.trace_path,
                max_output_tokens=50000,
            )
        return model_runtime.invoke_vision_text(
            image_paths=[Path(kwargs["figure_path"]), Path(kwargs["reference_image_path"])],
            prompt=prompt,
            task_name=f"box_ir_semantic_svg.{phase}.v1",
            runtime_config=self.runtime_config,
            trace_path=self.trace_path,
            max_output_tokens=50000,
        )

    def _invoke_codex_thread(
        self,
        *,
        phase: str,
        prompt: str,
        kwargs: Mapping[str, Any],
    ) -> str:
        session = self._ensure_codex_session(kwargs)
        try:
            return session.invoke(
                image_paths=[Path(kwargs["figure_path"]), Path(kwargs["reference_image_path"])],
                prompt=prompt,
                task_name=f"box_ir_semantic_svg.{phase}.v1",
                output_svg_path=Path(kwargs["output_svg_path"]),
                output_response_path=Path(kwargs["output_response_path"]),
            )
        except Exception as exc:
            recovered_svg = _recover_latest_valid_codex_partial_svg(
                output_svg_path=Path(kwargs["output_svg_path"]),
                output_response_path=Path(kwargs["output_response_path"]),
                trace_path=self.trace_path,
                error=exc,
            )
            self.close()
            if recovered_svg is not None:
                return recovered_svg
            raise

    def _ensure_codex_session(self, kwargs: Mapping[str, Any]) -> Any:
        if self._codex_session is not None:
            return self._codex_session
        from .codex_python_sdk_svg import CodexPythonSdkSvgSession

        shared_prompt_kwargs = dict(kwargs)
        shared_prompt_kwargs["file_context_mode"] = True
        shared_prompt_kwargs["workspace_dir"] = self.paths.root
        shared_prompt = _svg_generation_thread_shared_prompt(shared_prompt_kwargs)
        shared_prompt_path = self.paths.svg_dir / "codex_thread_shared_prompt.txt"
        shared_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        shared_prompt_path.write_text(shared_prompt, encoding="utf-8")
        model_runtime._append_trace(
            self.trace_path,
            {
                "type": "codex_python_sdk_shared_prompt",
                "runner": "codex_python_sdk_controlled",
                "path": str(shared_prompt_path),
                "chars": len(shared_prompt),
            },
        )
        session = CodexPythonSdkSvgSession(
            runtime_config=self.runtime_config,
            trace_path=self.trace_path,
            isolated_cwd=self.paths.root,
            shared_prompt=shared_prompt,
        )
        session.__enter__()
        self._codex_session = session
        return session

    def _invoke_agent_cli(
        self,
        *,
        phase: str,
        prompt: str,
        kwargs: Mapping[str, Any],
    ) -> str:
        from .agent_cli_svg import AgentCliSvgSession

        session = AgentCliSvgSession(
            runtime_config=self.runtime_config,
            trace_path=self.trace_path,
            isolated_cwd=self.paths.root,
        )
        return session.invoke(
            image_paths=[Path(kwargs["figure_path"]), Path(kwargs["reference_image_path"])],
            prompt=prompt,
            task_name=f"box_ir_semantic_svg.{phase}.v1",
            output_svg_path=Path(kwargs["output_svg_path"]),
            output_response_path=Path(kwargs["output_response_path"]),
        )

    def _invoke_acp_agent(
        self,
        *,
        phase: str,
        prompt: str,
        kwargs: Mapping[str, Any],
    ) -> str:
        from .acp_agent import AcpAgentSession

        session = AcpAgentSession(
            runtime_config=self.runtime_config,
            trace_path=self.trace_path,
            isolated_cwd=self.paths.root,
            additional_roots=(Path(__file__).resolve().parents[2],),
        )
        return session.invoke(
            image_paths=[Path(kwargs["figure_path"]), Path(kwargs["reference_image_path"])],
            prompt=prompt,
            task_name=f"box_ir_semantic_svg.{phase}.v1",
            output_svg_path=Path(kwargs["output_svg_path"]),
            output_response_path=Path(kwargs["output_response_path"]),
        )

    def _invoke_tool_agent(
        self,
        *,
        phase: str,
        prompt: str,
        kwargs: Mapping[str, Any],
    ) -> str:
        from .tool_agent_runtime import (
            DEFAULT_TOOL_AGENT_MAX_ITERATIONS,
            DRAWAI_TOOL_AGENT_PROVIDER,
            invoke_drawai_tool_agent,
        )

        runtime_config = dict(self.runtime_config)
        runtime_config["provider"] = DRAWAI_TOOL_AGENT_PROVIDER
        runtime_config["connection_id"] = DRAWAI_TOOL_AGENT_PROVIDER
        runtime_config["wire_api"] = str(runtime_config.get("wire_api") or "chat_completions")
        result = invoke_drawai_tool_agent(
            image_paths=[Path(kwargs["figure_path"]), Path(kwargs["reference_image_path"])],
            prompt=prompt,
            task_name=f"box_ir_semantic_svg.{phase}.v1",
            runtime_config=runtime_config,
            workspace_dir=self.paths.root,
            repo_root=Path(__file__).resolve().parents[2],
            trace_path=self.trace_path,
            max_output_tokens=int(runtime_config.get("max_output_tokens") or 32768),
            max_iterations=int(runtime_config.get("max_iterations") or DEFAULT_TOOL_AGENT_MAX_ITERATIONS),
        )
        output_svg_path = Path(kwargs["output_svg_path"])
        if not output_svg_path.is_file():
            raise RuntimeError(f"DrawAI Tool Agent did not write SVG output: {output_svg_path}")
        output_response_path = Path(kwargs["output_response_path"])
        if not output_response_path.exists():
            output_response_path.parent.mkdir(parents=True, exist_ok=True)
            output_response_path.write_text(result.final_text, encoding="utf-8")
        return output_svg_path.read_text(encoding="utf-8")


def _recover_latest_valid_codex_partial_svg(
    *,
    output_svg_path: Path,
    output_response_path: Path,
    trace_path: Path,
    error: Exception,
) -> str | None:
    attempt_dir = output_svg_path.parent
    candidates: list[tuple[int, Path, Path]] = []
    for candidate in attempt_dir.glob("semantic_*.svg"):
        match = re.fullmatch(r"semantic_(\d+)\.svg", candidate.name)
        if match is None:
            continue
        report_path = attempt_dir / f"validation_report_{match.group(1)}.json"
        candidates.append((int(match.group(1)), candidate, report_path))
    for index, candidate, report_path in sorted(candidates, reverse=True):
        if not report_path.exists():
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if report.get("status") != "ok":
            continue
        svg_text = candidate.read_text(encoding="utf-8", errors="replace")
        if not svg_text.lstrip().startswith("<svg"):
            continue
        output_svg_path.parent.mkdir(parents=True, exist_ok=True)
        output_svg_path.write_text(svg_text, encoding="utf-8")
        rendered_candidate = attempt_dir / f"rendered_{index}.png"
        rendered_output = attempt_dir / "rendered.png"
        if rendered_candidate.exists():
            shutil.copy2(rendered_candidate, rendered_output)
        output_response_path.parent.mkdir(parents=True, exist_ok=True)
        output_response_path.write_text(svg_text, encoding="utf-8")
        _write_partial_svg_recovery_iteration_logs(
            attempt_dir=attempt_dir,
            recovered_svg=candidate,
            recovered_render=rendered_candidate if rendered_candidate.exists() else None,
            validation_report=report_path,
            error=error,
        )
        model_runtime._append_trace(
            trace_path,
            {
                "type": "codex_python_sdk_partial_svg_recovered",
                "runner": "codex_python_sdk_controlled",
                "candidate": str(candidate),
                "validation_report": str(report_path),
                "output_svg_path": str(output_svg_path),
                "error": repr(error),
            },
        )
        return svg_text
    return None


def _write_partial_svg_recovery_iteration_logs(
    *,
    attempt_dir: Path,
    recovered_svg: Path,
    recovered_render: Path | None,
    validation_report: Path,
    error: Exception,
) -> None:
    iteration_log = attempt_dir / "iteration_log.md"
    iteration_log_jsonl = attempt_dir / "iteration_log.jsonl"
    if not iteration_log.exists() or iteration_log.stat().st_size <= 0:
        iteration_log.write_text(
            "\n".join(
                [
                    "# Codex SVG self-iteration log",
                    "",
                    "- Recovered a valid partial SVG after the Codex SDK turn ended without a complete response.",
                    f"- Recovered SVG: {recovered_svg.name}",
                    f"- Validation report: {validation_report.name}",
                    f"- Error: {type(error).__name__}: {error}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    if not iteration_log_jsonl.exists() or iteration_log_jsonl.stat().st_size <= 0:
        payload = {
            "iteration": 0,
            "stage": "timeout_partial_recovery",
            "status": "ok",
            "svg": recovered_svg.name,
            "rendered": recovered_render.name if recovered_render is not None else "",
            "validation_report": validation_report.name,
            "error_type": type(error).__name__,
            "error": str(error),
        }
        iteration_log_jsonl.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _svg_generation_prompt(kwargs: Mapping[str, Any]) -> str:
    phase = str(kwargs.get("phase") or "single")
    text_rendering = _normalize_svg_text_rendering(kwargs.get("text_rendering"))
    file_context_mode = bool(kwargs.get("file_context_mode"))
    agent_label = str(kwargs.get("agent_label") or "Codex").strip() or "Codex"
    box_ir = kwargs.get("box_ir") if isinstance(kwargs.get("box_ir"), Mapping) else {}
    asset_manifest = kwargs.get("asset_manifest") if isinstance(kwargs.get("asset_manifest"), Mapping) else {}
    template_ir = kwargs.get("template_ir")
    if not isinstance(template_ir, Mapping):
        template_ir = build_svg_template_ir(box_ir)
    safe_box_ir = deepcopy(dict(box_ir))
    feedback = kwargs.get("feedback") or {}

    response_format = "" if file_context_mode else f"{_response_format_instruction(phase)} "
    common_rules = (
        response_format
        + "The SVG root must match the layout IR canvas exactly with viewBox='0 0 width height'. "
        "Never emit absolute paths, file:// paths, or external URLs. "
        "If attempt feedback is present, fix those validation issues. "
        f"{_drawai_svg_profile_prompt()} "
    )
    width, height = _canvas_size_for_prompt(template_ir)
    dimension_rules = (
        f"- The original image has dimensions: {width} x {height} pixels.\n"
        f"- Set viewBox=\"0 0 {width} {height}\" and width=\"{width}\" height=\"{height}\".\n"
        "- Do not scale or resize the SVG.\n"
    )
    grid_prompt_addendum = _grid_prompt_addendum(
        box_ir, phase, file_context_mode=file_context_mode
    )
    raster_exclusion_addendum = _raster_asset_exclusion_addendum(
        asset_manifest, file_context_mode=file_context_mode
    )
    asset_constraints_addendum = _asset_restoration_constraints_addendum(
        asset_manifest, file_context_mode=file_context_mode
    )
    native_backfill_addendum = _native_backfill_mode_prompt(kwargs, phase)
    template_ir_section = _template_ir_source_section(
        template_ir, file_context_mode=file_context_mode
    )
    attempt_feedback_section = _attempt_feedback_section(
        feedback,
        file_context_mode=file_context_mode,
        request_context_path=kwargs.get("request_context_path"),
    )
    workspace_context_addendum = _codex_workspace_context_addendum(kwargs) if file_context_mode else ""
    if file_context_mode and bool(kwargs.get("codex_thread_turn_mode")):
        return _svg_generation_thread_turn_prompt(
            kwargs,
            phase=phase,
            text_rendering=text_rendering,
        )
    if phase == "template":
        if file_context_mode:
            return (
                "ROLE\n"
                f"You are {agent_label} operating inside the DrawAI run workspace. Your job is to edit files, not to return SVG in chat.\n\n"
                "STAGE GOAL\n"
                "Run 1 / template: Build the first editable vector template for the whole figure. "
                "Produce a complete first-pass SVG that keeps run0 svg_self_draw structure editable and inserts allowed manifest-backed crop/crop_nobg image assets at their refined bboxes.\n\n"
                "IMAGE MEANINGS\n"
                "- Image 1 is the original/current reference image.\n"
                "- Image 2 is a secondary semantic/template reference image.\n"
                "- The run0-refined asset manifest identifies crop/crop_nobg regions that may be inserted as local images.\n\n"
                "SOURCE PRIORITY\n"
                "1. Visible evidence in Image 1 wins.\n"
                "2. Codex run0 asset analysis is the primary structured plan for refined asset boundaries and source choices.\n"
                "3. Asset manifest entries are authoritative for allowed local raster image hrefs.\n"
                "4. Compact Template IR and attempt feedback are fallback hints.\n\n"
                "STAGE-SPECIFIC TASKS\n"
                "- Build a PPT-stable editable SVG template at pixel-level layout fidelity.\n"
                "- Use manifest svg_href or insertable_components[].svg_href exactly for run0 crop/crop_nobg elements.\n"
                "- Keep arrow styles, borders, colors, composition, and layout consistent with the original image.\n"
                f"- {_template_text_rendering_instruction(text_rendering)}\n"
                "- Use OCR text evidence only as a hint; correct it when the image disagrees.\n"
                "ALLOWED ACTIONS\n"
                "- Draw run0 svg_self_draw structure using rect, line, polyline, path, polygon, circle/ellipse, text/tspan, g, explicit polygon arrowheads, and supported gradients.\n"
                "- Insert allowed local raster images listed in the asset manifest for run0 crop/crop_nobg elements.\n"
                "- Use simple neutral underlays around gray boxes when surrounding editable structure needs continuity.\n\n"
                "FORBIDDEN ACTIONS\n"
                "RETIRED PLACEHOLDER CONTRACT:\n"
                "- Do not output AF01/AF02 identifiers, data-placeholder-kind, data-asset-id, data-asset-placeholder, or placeholder groups.\n"
                "- Do not write any AFxx token as visible text, ids, comments, descriptions, metadata, or annotations.\n"
                "- Do not use <marker>, marker-start, marker-mid, or marker-end; draw arrowheads as explicit editable polygons.\n"
                "- Do not output CSS <style> blocks, filters, masks, clipPath, foreignObject, textPath, pattern fills, base64 images, external URLs, absolute paths, <symbol>, or <use>.\n"
                "- Do not add arrows, panels, or placeholder-like objects solely because the IR contains a noisy proposal.\n\n"
                "VALIDATION CHECKLIST\n"
                "- Canvas dimensions and viewBox match exactly.\n"
                "- Panels/modules/content boxes align with visible image evidence.\n"
                "- Arrows/connectors match visible direction, bend, endpoint, arrowhead, stroke weight, and z-order.\n"
                "- Text/formulas are editable SVG text/tspan with required data-pb attributes.\n"
                "- Tables/grids, if present, use editable line/rect primitives and do not invent rows or columns.\n"
                "- Gray-box boundaries remain clean and do not contain invented hidden details.\n\n"
                f"{dimension_rules}\n"
                f"{raster_exclusion_addendum}"
                f"{native_backfill_addendum}"
                f"{grid_prompt_addendum}"
                f"{_model_text_contract(use_ocr_hints=True)}"
                f"{common_rules}\n\n"
                f"{template_ir_section}"
                f"{_ocr_text_hint_section(box_ir, file_context_mode=file_context_mode)}"
                f"{attempt_feedback_section}"
                f"{workspace_context_addendum}"
            )
        return (
            "This template stage builds the first PPT-stable editable SVG reconstruction. "
                "Write SVG code that already looks like a full result at pixel level, using editable SVG primitives for run0 svg_self_draw elements and allowed manifest images for run0 crop/crop_nobg elements. "
            "Keep arrow styles, borders, colors, composition, and layout consistent with the original image; "
            f"{_template_text_rendering_instruction(text_rendering)} "
            "\n\nCRITICAL DIMENSION REQUIREMENT:\n"
            f"{dimension_rules}\n"
            "Image reference notes:\n"
            "- Image 1 is the original/current reference image.\n"
            "- Image 2 is a secondary semantic/template reference image.\n"
            "- The asset manifest lists allowed local raster image hrefs for run0 crop/crop_nobg elements.\n\n"
            "VISUAL SOURCE PRIORITY:\n"
            "Treat Image 1 as the primary visual truth and run0 element analysis as the primary structured asset plan. "
            "Compact Template IR JSON is only a soft geometry hint for broad content boxes and arrows. "
            "If the IR conflicts with the visible figure, follow the images. "
            "Do not add arrows, panels, or placeholder-like objects solely because the IR contains a noisy proposal.\n\n"
            f"{raster_exclusion_addendum}"
            f"{native_backfill_addendum}"
            f"{grid_prompt_addendum}"
            "PPT PROFILE HARD LIMITS:\n"
            "Do not output CSS <style> blocks, SVG filters, feDropShadow, mask, clipPath, foreignObject, textPath, pattern fills, "
            "base64 images, external image URLs, absolute paths, or full-slide images. "
            "Do not output <symbol> or <use>; duplicate simple geometry explicitly. "
            "Use direct SVG presentation attributes on elements so the local svg_to_ppt tool can map objects to editable PowerPoint shapes.\n\n"
            "RETIRED PLACEHOLDER CONTRACT:\n"
            "Do not output AF01/AF02 identifiers, data-placeholder-kind, data-asset-id, data-asset-placeholder, or placeholder groups. "
            "Use direct <image> elements only for allowed manifest entries. If a crop/crop_nobg region lacks an allowed href, leave only "
            "an ordinary neutral underlay shape without placeholder metadata and record the missing source.\n\n"
            f"{_model_text_contract(use_ocr_hints=True)}"
            "The compact template IR below contains only content_box and arrow geometry. It intentionally excludes icons, "
            "pictures, and detailed OCR text boxes. Use it only as a low-priority geometry hint to improve broad layout and connector accuracy. "
            f"{common_rules}\n\n"
            f"{template_ir_section}"
            f"{_ocr_text_hint_section(box_ir, file_context_mode=file_context_mode)}"
            f"{attempt_feedback_section}"
            f"{workspace_context_addendum}"
        )
    if phase.startswith("visual_review_"):
        visual_round = _positive_int_or_default(kwargs.get("visual_review_round"), 1)
        visual_total_rounds = _positive_int_or_default(
            kwargs.get("visual_review_total_rounds"),
            visual_round,
        )
        visual_focus = str(kwargs.get("visual_review_focus") or "layout")
        focus_instruction = _visual_review_focus_instruction(visual_focus)
        if file_context_mode:
            return (
                "ROLE\n"
                f"You are {agent_label} operating inside the DrawAI run workspace. Your job is to inspect the current template files and edit the SVG output file.\n\n"
                "STAGE GOAL\n"
                f"Run 2 / {phase}: Visual-review round {visual_round} of {visual_total_rounds}. "
                f"This is visual review loop round {visual_round} of {visual_total_rounds}. "
                "Only edit the current template SVG to improve the whole-figure visual match. "
                "Return a corrected editable SVG template, not the final asset-restored SVG.\n\n"
                "IMAGE MEANINGS\n"
                "- Image 1 is the original/current reference image.\n"
                "- Image 2 is the current rendered template SVG from the previous stage.\n"
                "- Compare the whole figure, including panels, text, connectors, grids/tables, z-order, colors, and manifest-backed image placement.\n\n"
                "SOURCE PRIORITY\n"
                "1. Visible evidence in Image 1 wins.\n"
                "2. The current template SVG is the editable starting point, not a truth source when it visually disagrees.\n"
                "3. Compact Template IR is only a weak geometry hint; it cannot justify arrows or boxes absent from Image 1.\n"
                "4. Attempt feedback is a repair hint; re-check the current images and files before editing.\n\n"
                f"REVIEW FOCUS\n{focus_instruction}\n\n"
                "STAGE-SPECIFIC TASKS\n"
                "- Review the whole figure together, not only arrows or one local region.\n"
                "- Fix readable editable text, formulas, font style/weight/color/size, baselines, superscript/subscript, legend labels, and vertical text.\n"
                "- Fix only supported layout issues: panel boundaries, connector endpoints/arrowheads, grid/table alignment, spacing, overlap, and z-order.\n"
                "- Remove unsupported duplicate/invented arrows, but keep and repair visible original connectors.\n"
                "- Modify or delete existing unsupported geometry instead of adding parallel duplicate lines.\n"
                "- Keep manifest-backed crop/crop_nobg images aligned with their refined bboxes.\n\n"
                "ALLOWED ACTIONS\n"
                "- Make small targeted edits to the current template SVG.\n"
                "- Repair visible connectors, text/formulas, grid/table lines, panel geometry, colors, and layering.\n"
                "- Use allowed local raster images listed in the asset manifest for run0 crop/crop_nobg elements.\n"
                "- Write concise whole-figure modification notes to the optional notes path if useful.\n\n"
                "FORBIDDEN ACTIONS\n"
                "- Do not invent raster assets, hrefs, or bboxes outside the asset manifest/native_backfill_request.\n"
                "- Do not redraw complex crop/crop_nobg content when an allowed href exists.\n"
                "- Do not use AF01/AF02 identifiers, data-placeholder-kind, data-asset-id, data-asset-placeholder, or placeholder groups.\n"
                "- Do not write any AFxx token as visible text, ids, comments, descriptions, metadata, or annotations.\n"
                "- Do not use <marker>, marker-start, marker-mid, or marker-end; draw arrowheads as explicit editable polygons.\n"
                "- Do not optimize one category by breaking another.\n\n"
                "VALIDATION CHECKLIST\n"
                "- Every remaining arrow or connector corresponds to visible original structure in Image 1.\n"
                "- Text/formulas are readable, editable, correctly oriented, and not overlapping key structure.\n"
                "- Panels/content boxes, tables/grids, color hierarchy, z-order, and image placements match the target as a whole.\n"
                "- No unsupported duplicate/invented arrows or invented crop-region details remain.\n\n"
                f"{dimension_rules}\n"
                f"{_model_text_contract(use_ocr_hints=False)}"
                f"{raster_exclusion_addendum}"
                f"{native_backfill_addendum}"
                f"{grid_prompt_addendum}"
                f"{common_rules}\n\n"
                f"{_base_svg_source_section(kwargs, file_context_mode, heading='Current template SVG to refine')}"
                f"{template_ir_section}"
                f"{attempt_feedback_section}"
                f"{workspace_context_addendum}"
            )
        return (
            "Act as the visual critic and editor for the sparse template SVG. "
            f"This is visual review loop round {visual_round} of {visual_total_rounds}. "
            "Refine the visual template SVG by comparing the original/current reference image against the current rendered template. "
            "Return a corrected SVG template, not a final filled SVG. "
            "\n\nCRITICAL DIMENSION REQUIREMENT:\n"
            f"{dimension_rules}\n"
            "Image reference notes:\n"
            "- Image 1 is the original/current reference image.\n"
            "- Image 2 is the current rendered template SVG from the previous stage.\n\n"
            "Use the run0-refined asset manifest for crop/crop_nobg regions; review and refine the visible editable structure around them.\n\n"
            f"REVIEW FOCUS:\n{focus_instruction}\n\n"
            "REFINEMENT SCOPE:\n"
            "Review the whole figure together, not only arrows or one local region. "
            "Check and correct panels/modules/content boxes, rounded corners, stroke widths, fills, z-order, arrows/connectors, "
            "text/formulas, tables/grids, borders, spacing, color hierarchy, and simplified regions around gray boxes. "
            "Every remaining arrow or connector must correspond to visible original structure in Image 1, with matching direction, bend, endpoint, arrowhead, and visual weight. "
            "Remove unsupported duplicate/invented arrows, but keep and repair visible original connectors instead of deleting them aggressively. "
            "Do not optimize one category by breaking another; prefer small targeted edits that improve the full-image match. "
            f"{_visual_review_text_rendering_instruction(text_rendering)} "
            "Use direct <image> elements only for allowed manifest entries. "
            "Do not use AF01/AF02 identifiers, data-placeholder-kind, data-asset-id, data-asset-placeholder, or placeholder groups. "
            "For crop/crop_nobg regions without an allowed href, keep only ordinary neutral underlay shapes without placeholder metadata. "
            f"{_model_text_contract(use_ocr_hints=False)}"
            "The compact template IR contains only content_box and arrow geometry; layout IR arrow geometry is a soft hint, not permission to keep arrows that Image 1 does not support. "
            "Before returning SVG, perform a visual acceptance check across layout, connectors, text/formulas, grids/tables, colors, z-order, and gray-box boundaries. "
            "In the whole-figure Modification Notes block, list the full-image change categories you made or considered: panels/content boxes, arrows/connectors, text/formula placement, grids/tables, color/style/z-order, and unresolved visual risks. "
            f"{raster_exclusion_addendum}"
            f"{native_backfill_addendum}"
            f"{grid_prompt_addendum}"
            f"{common_rules}\n\n"
            f"{_base_svg_source_section(kwargs, file_context_mode, heading='Current template SVG to refine')}"
            f"{template_ir_section}"
            f"{attempt_feedback_section}"
            f"{workspace_context_addendum}"
        )
    if phase == "ir_refine":
        if file_context_mode:
            return (
                "ROLE\n"
                f"You are {agent_label} operating inside the DrawAI run workspace. Your job is to produce the final editable semantic SVG file.\n\n"
                "STAGE GOAL\n"
                "Run 3 / ir_refine: Start from the validated visual template, use the compact IR only for final content-box and arrow geometry corrections, "
                "and produce the final SVG that local post-processing can convert to editable PowerPoint.\n\n"
                "IMAGE MEANINGS\n"
                "- Image 1 is the original/current reference image used for final visual comparison.\n"
                "- Image 2 is the rendered template from the visual-review stage.\n"
                "- Gray boxes still indicate raster asset zones; detailed raster content must come only from the manifest.\n\n"
                "SOURCE PRIORITY\n"
                "1. Visible image evidence and the validated template structure win for editable vector content.\n"
                "2. Use the asset manifest for allowed raster asset insertion; it does not define ordinary vector structure.\n"
                "3. Compact Template IR is a low-priority geometry correction source for content boxes and arrows.\n"
                "4. Attempt feedback is a repair hint; do not blindly apply it against visible evidence.\n\n"
                "STAGE-SPECIFIC TASKS\n"
                "- Preserve useful editable visual structure from the template.\n"
                "- Apply IR-driven coordinate and connector corrections only where they improve the whole figure.\n"
                "- Keep panels, arrows, text, formulas, tables, and layout structure editable.\n"
                "- Keep using manifest-listed raster <image> elements for run0 crop/crop_nobg areas.\n"
                "- This is also the only separated stage that may backfill a native-SVG candidate when the rendered candidate is worse than the original exact region, or when visual evidence shows the region should be restored from a crop instead of redrawn as native SVG.\n"
                f"- {_ir_refine_text_rendering_instruction(text_rendering)}\n\n"
                "ALLOWED ACTIONS\n"
                "- Use asset.svg_href or insertable_components[].svg_href exactly for allowed local raster assets.\n"
                "- Place insertable component PNGs at their component bboxes when a parent asset has insertable=false.\n"
                "- Leave clean neutral underlays only where they support vector continuity around raster asset regions.\n"
                "- Write concise whole-figure modification notes to the optional notes path if useful.\n\n"
                "FORBIDDEN ACTIONS\n"
                "- Do not use parent crop/source_svg_href when insertable_components are provided.\n"
                "- Do not invent hrefs, absolute paths, or raster assets outside the manifest.\n"
                "- Do not redraw detailed content inside raster asset bboxes.\n"
                "- Do not output AF01/AF02 identifiers, data-placeholder-kind, data-asset-id, data-asset-placeholder, or placeholder groups.\n"
                "- Do not write any AFxx token as visible text, ids, comments, descriptions, metadata, or annotations.\n"
                "- Do not use <marker>, marker-start, marker-mid, or marker-end; draw arrowheads as explicit editable polygons.\n\n"
                "VALIDATION CHECKLIST\n"
                "- Final SVG dimensions and viewBox match exactly.\n"
                "- Manifest raster assets, if used, reference only allowed hrefs and preserve their bboxes.\n"
                "- Editable panels/connectors/text/formulas/tables remain as SVG primitives outside raster asset bboxes.\n"
                "- Arrows/connectors remain visually supported and PPT-stable.\n"
                "- No hidden raster details are invented and no placeholder metadata remains.\n\n"
                f"{dimension_rules}\n"
                f"{_model_text_contract(use_ocr_hints=False)}"
                f"{raster_exclusion_addendum}"
                f"{native_backfill_addendum}"
                f"{grid_prompt_addendum}"
                f"{common_rules}\n\n"
                f"{_base_svg_source_section(kwargs, file_context_mode, heading='Validated visual template SVG from stage 1')}"
                f"{asset_constraints_addendum}"
                f"{template_ir_section}"
                f"{attempt_feedback_section}"
                f"{workspace_context_addendum}"
            )
        return (
            "Generate the IR-refined editable semantic SVG. "
            "Start from the validated visual template SVG below. Use the compact template IR only to adjust content-box "
            "and arrow geometry. "
            "Preserve useful visual structure from the template. "
            f"{_ir_refine_text_rendering_instruction(text_rendering)} "
            "In the whole-figure Modification Notes block, list the IR-driven changes you made across the full image, especially coordinate changes, connector changes, text/formula decisions, simplified complex regions, and unresolved risks. "
            "Do not output AF01/AF02 identifiers, data-placeholder-kind, data-asset-id, data-asset-placeholder, or placeholder groups. "
            "Local raster <image> elements are allowed only for insertable assets listed in the Asset manifest JSON below. "
            "Use asset.svg_href or insertable_components[].svg_href exactly, never absolute paths or invented hrefs. "
            "If native_backfill_request.json lists a candidate whose rendered SVG is worse than the original exact region, or whose content is unsuitable for faithful native-SVG reconstruction, you may create and reference exactly one of its allowed backfill hrefs. "
            "If a manifest parent asset has insertable=false and insertable_components, never use the parent crop/source_svg_href; place only the listed component PNGs at their component bboxes. "
            "Keep panels, arrows, text, formulas, tables, and layout structure as editable SVG primitives. "
            "Do not redraw detailed content inside raster asset bboxes; keep only clean neutral underlays if needed. "
            "A deterministic finalizer will also overlay any missing insertable manifest raster assets at their manifest/component bbox, so preserve clean vector structure around those regions. "
            f"{_model_text_contract(use_ocr_hints=False)}"
            f"{raster_exclusion_addendum}"
            f"{native_backfill_addendum}"
            f"{grid_prompt_addendum}"
            f"{common_rules}\n\n"
            f"{_base_svg_source_section(kwargs, file_context_mode, heading='Validated visual template SVG from stage 1')}"
            f"{asset_constraints_addendum}"
            f"{template_ir_section}"
            f"{attempt_feedback_section}"
            f"{workspace_context_addendum}"
        )
    if file_context_mode:
        return (
            "Generate the final editable semantic SVG for this scientific figure. "
            "Use canonical SVG elements where possible and reference bitmap assets only from the asset manifest. "
            "For every bitmap asset, read svg_href or insertable_components[].svg_href from the asset manifest; never emit absolute paths. "
            f"{common_rules}\n\n"
            f"{native_backfill_addendum}"
            "layout IR and asset sources:\n"
            f"- layout IR JSON: {_path_for_prompt('box_ir/box_ir.json')}\n"
            f"- Asset manifest JSON: {_path_for_prompt('svg_to_ppt/assets/asset_manifest.json')}\n"
            f"- Attempt context and feedback: {_path_for_prompt(kwargs.get('request_context_path'))}\n\n"
            f"{workspace_context_addendum}"
        )
    return (
        "Generate the final editable semantic SVG for this scientific figure. "
        "Use canonical SVG elements where possible and reference bitmap assets only from the asset manifest. "
        "For every bitmap asset, use the manifest asset.svg_href or insertable_components[].svg_href value exactly in the SVG href; never emit absolute paths. "
        f"{common_rules}\n\n"
        "layout IR JSON with OCR text redacted:\n"
        f"{json.dumps(_json_safe(safe_box_ir), ensure_ascii=False, indent=2)}\n\n"
        "Asset manifest JSON:\n"
        f"{json.dumps(_json_safe(asset_manifest), ensure_ascii=False, indent=2)}\n\n"
        "Attempt feedback JSON:\n"
        f"{json.dumps(_json_safe(feedback), ensure_ascii=False, indent=2)}"
    )


def _format_prompt_number(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _svg_generation_thread_shared_prompt(kwargs: Mapping[str, Any]) -> str:
    box_ir = kwargs.get("box_ir") if isinstance(kwargs.get("box_ir"), Mapping) else {}
    asset_manifest = kwargs.get("asset_manifest") if isinstance(kwargs.get("asset_manifest"), Mapping) else {}
    template_ir = kwargs.get("template_ir")
    if not isinstance(template_ir, Mapping):
        template_ir = build_svg_template_ir(box_ir)
    agent_label = str(kwargs.get("agent_label") or "Codex").strip() or "Codex"
    width, height = _canvas_size_for_prompt(template_ir)
    dimension_rules = (
        f"- The original image has dimensions: {width} x {height} pixels.\n"
        f"- Every stage must set viewBox=\"0 0 {width} {height}\" and width=\"{width}\" height=\"{height}\".\n"
        "- Do not scale or resize the SVG canvas.\n"
    )
    return (
        f"DRAWAI {agent_label.upper()} THREAD SHARED CONTEXT\n"
        "ROLE\n"
        f"You are {agent_label} operating inside one reusable DrawAI SVG-generation thread. "
        "Python starts the thread and supplies each new turn, but you are responsible for reading files, editing SVG files, and writing the requested output files yourself.\n\n"
        "THREAD STRUCTURE\n"
        "- Run 1 / template creates the first editable visual template.\n"
            "- Run 2 / visual_review_* compares the rendered template with the original/current reference and edits the template.\n"
            "- Run 3 / ir_refine creates the final editable semantic SVG while preserving manifest-listed raster assets.\n"
        "- Later turns only provide stage-specific instructions, current images, feedback, and output paths; keep this shared context in mind without requiring it to be repeated.\n\n"
        "MUST READ FILES:\n"
        f"- Sandbox cwd / run root: {_path_for_prompt(kwargs.get('workspace_dir'))}\n"
        f"- Target figure image: {_path_for_prompt(kwargs.get('figure_path'))}\n"
        f"- Current reference image: {_path_for_prompt(kwargs.get('reference_image_path'))}\n"
        f"- layout IR JSON: {_path_for_prompt('box_ir/box_ir.json')}\n"
        f"- SVG template IR JSON: {_path_for_prompt('svg/svg_template_ir.json')}\n"
        f"- Asset manifest JSON: {_path_for_prompt('svg_to_ppt/assets/asset_manifest.json')}\n"
        f"- Codex run0 refined asset/source analysis JSON: {_path_for_prompt('reports/element_analysis_codex/element_analysis.json')}\n"
        f"- OCR boxes JSON: {_path_for_prompt('ocr/ocr_boxes.json')}\n\n"
        "WORKSPACE RULES:\n"
        "- You may use shell commands inside this workspace to inspect files, compare SVGs, render/check intermediate outputs, and write outputs.\n"
        "- You may freely read files under the sandbox cwd / run root listed above.\n"
        "- Do not use MCP tools, apps, web search, memories, multi-agent delegation, hooks, skills, or files outside this workspace.\n"
        "- Do not write outputs outside the required SVG path, optional notes path, validator/render intermediates, iteration logs, and any native_backfill assets explicitly named in the current turn.\n\n"
        "COMMON SVG/PPT PROFILE\n"
        f"{dimension_rules}"
        "Never emit absolute paths, file:// paths, or external URLs. "
        "Treat the input as an editable scientific structure diagram, not as a bitmap tracing task. "
        f"{_drawai_svg_profile_prompt()} "
        "Use direct SVG presentation attributes on elements so the local svg_to_ppt tool can map objects to editable PowerPoint shapes. "
        "Do not output CSS <style> blocks, filters, masks, clipPath, foreignObject, textPath, pattern fills, base64 images, <symbol>, or <use>.\n\n"
        f"{_model_text_contract(use_ocr_hints=True)}"
        f"{_raster_asset_exclusion_addendum(asset_manifest, file_context_mode=True)}"
        f"{_native_backfill_shared_prompt(kwargs)}"
        f"{_grid_prompt_addendum(box_ir, 'thread_shared', file_context_mode=True)}"
        "SOURCE PRIORITY\n"
        "1. Visible evidence in the attached images wins.\n"
        "2. Existing SVG files are editable starting points, not truth sources when they visually disagree.\n"
        "3. Compact Template IR is only a low-priority geometry hint for broad content boxes and arrows.\n"
        "4. Asset manifest entries are authoritative for allowed crop/crop_nobg image hrefs in every SVG generation stage.\n"
        "5. Codex run0 asset analysis is the primary structured plan for refined asset boundaries and svg_self_draw/crop/crop_nobg source choices.\n"
        "6. Attempt feedback is a repair hint; re-check current images and files before editing.\n"
    )


def _svg_generation_thread_turn_prompt(
    kwargs: Mapping[str, Any],
    *,
    phase: str,
    text_rendering: str,
) -> str:
    feedback = kwargs.get("feedback") or {}
    attempt_feedback_section = _attempt_feedback_section(
        feedback if isinstance(feedback, Mapping) else {},
        file_context_mode=True,
        request_context_path=kwargs.get("request_context_path"),
    )
    native_backfill_addendum = _native_backfill_mode_prompt(kwargs, phase)
    if phase == "codex_merged_stages":
        return _svg_generation_merged_thread_turn_prompt(
            kwargs,
            text_rendering=text_rendering,
            attempt_feedback_section=attempt_feedback_section,
        )
    if phase == "template":
        stage_goal = (
            "Run 1 / template: Build the first editable vector template for the whole figure. "
            "Produce a complete first-pass SVG using editable SVG primitives for run0 svg_self_draw elements and manifest images for run0 crop/crop_nobg elements."
        )
        image_meanings = (
            "- Image 1 is the original/current reference image.\n"
            "- Image 2 is the semantic reference image with layout IR diagnostic overlays and the same raster asset exclusion zones.\n"
            "- Treat the run0-refined asset manifest as the source of allowed crop/crop_nobg image hrefs."
        )
        tasks = (
            "- Build a PPT-stable editable SVG template at pixel-level layout fidelity.\n"
            "- Keep arrow styles, borders, colors, composition, and layout consistent with the original image.\n"
            f"- {_template_text_rendering_instruction(text_rendering)}\n"
            "- Use OCR text evidence only as a hint; correct it when the image disagrees.\n"
            "- Use manifest svg_href or insertable_components[].svg_href exactly for run0 crop/crop_nobg elements.\n"
            "- Do not use placeholder metadata or invented crop-region details."
        )
    elif phase.startswith("visual_review_"):
        visual_round = _positive_int_or_default(kwargs.get("visual_review_round"), 1)
        visual_total_rounds = _positive_int_or_default(
            kwargs.get("visual_review_total_rounds"),
            visual_round,
        )
        visual_focus = str(kwargs.get("visual_review_focus") or "layout")
        stage_goal = (
            f"Run 2 / {phase}: Visual-review round {visual_round} of {visual_total_rounds}. "
            "Edit the current template SVG to improve the whole-figure visual match while preserving manifest-backed image assets."
        )
        image_meanings = (
            "- Image 1 is the original/current reference image.\n"
            "- Image 2 is the current rendered template SVG from the previous stage.\n"
            "- Compare panels, text, connectors, grids/tables, z-order, colors, and manifest-backed image placement across the whole figure."
        )
        tasks = (
            f"Review focus:\n{_visual_review_focus_instruction(visual_focus)}\n"
            "- Fix readable editable text, formulas, orientation, style, placement, panel boundaries, connector endpoints/arrowheads, grid/table alignment, spacing, overlap, and z-order.\n"
            "- Remove unsupported duplicate/invented arrows, but keep and repair visible original connectors.\n"
            "- Keep manifest-backed crop/crop_nobg images aligned with their refined bboxes.\n"
            "- Do not invent raster assets, hrefs, bboxes, or crop-region details."
        )
    elif phase == "ir_refine":
        stage_goal = (
            "Run 3 / ir_refine: Start from the validated visual template, apply only visually supported IR/manifest corrections, "
            "and produce the final SVG that local post-processing can convert to editable PowerPoint."
        )
        image_meanings = (
            "- Image 1 is the original/current reference image used for final visual comparison.\n"
            "- Image 2 is the rendered template from the visual-review stage.\n"
            "- Detailed raster content must come only from the manifest or native_backfill_request."
        )
        tasks = (
            "- Preserve useful editable visual structure from the template.\n"
            "- Apply IR-driven coordinate and connector corrections only where they improve the whole figure.\n"
            "- Keep panels, arrows, text, formulas, tables, and layout structure editable.\n"
            "- Use only manifest svg_href or insertable_components[].svg_href values for manifest-listed raster <image> elements.\n"
            "- This is also the only separated stage that may backfill a native-SVG candidate when the rendered candidate is worse than the original exact region, or when visual evidence shows the region should be restored from a crop instead of redrawn as native SVG.\n"
            f"- {_ir_refine_text_rendering_instruction(text_rendering)}"
        )
    else:
        stage_goal = "Generate the final editable semantic SVG for this scientific figure."
        image_meanings = (
            "- Image 1 is the target figure.\n"
            "- Image 2 is the current semantic or visual reference image."
        )
        tasks = (
            "- Use canonical editable SVG elements where possible.\n"
            "- Reference bitmap assets only from the asset manifest."
        )
    return (
        "STAGE GOAL\n"
        f"{stage_goal}\n\n"
        "IMAGE MEANINGS\n"
        f"{image_meanings}\n\n"
        "CURRENT TURN FILES\n"
        f"- Image 1 path: {_path_for_prompt(kwargs.get('figure_path'))}\n"
        f"- Image 2 path: {_path_for_prompt(kwargs.get('reference_image_path'))}\n"
        f"- Attempt request context: {_path_for_prompt(kwargs.get('request_context_path'))}\n"
        f"- Attempt prompt copy: {_path_for_prompt(kwargs.get('prompt_path'))}\n"
        f"- Required SVG output path: {_path_for_prompt(kwargs.get('output_svg_path'))}\n"
        f"- Optional notes/response path: {_path_for_prompt(kwargs.get('output_response_path'))}\n"
        f"{_thread_turn_base_svg_line(kwargs)}\n"
        "STAGE-SPECIFIC TASKS\n"
        f"{tasks}\n\n"
        f"{native_backfill_addendum}"
        f"{attempt_feedback_section}"
        "FINAL CHECK BEFORE ENDING THIS TURN\n"
        "- Write exactly one complete SVG document at the required SVG output path named above.\n"
        "- The SVG file must start with <svg and end with </svg>.\n"
        "- Keep the final chat response short; the SVG file is the source of truth.\n"
    )


def _svg_generation_merged_thread_turn_prompt(
    kwargs: Mapping[str, Any],
    *,
    text_rendering: str,
    attempt_feedback_section: str,
) -> str:
    native_backfill_addendum = _native_backfill_mode_prompt(kwargs, "codex_merged_stages")
    return (
        "IMAGE VECTORIZATION TASK\n"
        "Goal: convert one bitmap figure into an editable, PPT-stable SVG.\n\n"
        "OVERALL DRAWAI PIPELINE\n"
        "The full DrawAI task is split into three conceptual stages:\n"
        "1. Asset parsing: split the bitmap figure into independent visual assets, such as text, icons, tables, frames, arrows, chart marks, screenshots, pictures, diagram components, formulas, axes, panels, and other meaningful regions.\n"
        "2. Asset post-processing: refine the pre-parsed assets, adjust bboxes, split/merge elements, add missing elements, and decide the source strategy for each asset: svg_self_draw, crop, or crop_nobg.\n"
        "3. Image editabilization: reconstruct the whole figure as an editable SVG/PPT representation by combining editable SVG primitives/text with allowed raster crop assets.\n\n"
        "The current Codex turn executes stage 3 only. Do not redo stage 1 or stage 2. Use their outputs as evidence, especially run0 refined asset analysis and the run0 asset manifest. "
        "Your job is to create one complete first-pass SVG, validate it, make the bounded refinement rounds described below, and always finish with the required final SVG and logs before the turn timeout.\n\n"
        "EXECUTION MODEL\n"
        "- Python has already prepared the run workspace and prior analysis files. You must read those files yourself.\n"
        "- You may use ordinary shell utilities or short local scripts to inspect connected files and write run-local outputs. For DrawAI-specific behavior, do not inspect repository source code, import internal DrawAI modules, or call internal Python APIs; use only the declared scripts/tools and their documented contracts.\n"
        "- Python will not run the first-pass generation and refinement as separate Codex turns. This is one Codex turn that must complete them internally.\n"
        "- You must create intermediate SVGs/renders, inspect them, revise them, and finish with the required final SVG and logs.\n"
        "- Run1 and every refine round may use allowed local raster image hrefs from the run0-refined asset manifest when the asset source is crop or crop_nobg.\n\n"
        "WORKFLOW\n"
        "1. Run1: create a complete first-pass SVG as semantic_0.svg.\n"
        "2. Refine loop: default to one refinement round. Run a second round only for validator failures or clearly blocking structure issues. Do not run a third round in this workflow.\n"
        "3. Finalize: write semantic.svg/rendered.png, copy them to the required output paths, and write logs.\n\n"
        "Finalization has higher priority than another refinement round. If the latest SVG validates and is broadly faithful, finalize it immediately.\n\n"
        "AVAILABLE FILES AND READING LOGIC\n"
        "Primary files for this stage:\n"
        f"- Original/current reference image: {_path_for_prompt(kwargs.get('figure_path'))}. Use it as the visual truth for layout, color, text placement, arrows, icons, images, tables, axes, and spacing.\n"
        f"- Codex run0 refined asset/source analysis JSON: {_path_for_prompt('reports/element_analysis_codex/element_analysis.json')}. Use this as the main structured plan for refined asset boundaries and source decisions: svg_self_draw, crop, or crop_nobg.\n"
        f"- Run0-refined asset manifest JSON: {_path_for_prompt('svg_to_ppt/assets/asset_manifest.json')}. Use it as the authoritative list of local raster image hrefs that may appear in your SVG.\n"
        f"- Native backfill request JSON: {_path_for_prompt(kwargs.get('native_backfill_request_path'))}. Use it only for listed candidates when the existing manifest does not provide a faithful crop/no-background source. It is not permission to crop arbitrary regions.\n"
        f"- SVG validator script: {_path_for_prompt(kwargs.get('validator_script_path'))}. Use it after every written SVG.\n\n"
        "Auxiliary files to read only when needed:\n"
        f"- OCR boxes JSON: {_path_for_prompt('ocr/ocr_boxes.json')}. Read it when visible text content, text grouping, or text bbox needs confirmation.\n"
        f"- Template/reference image: {_path_for_prompt(kwargs.get('reference_image_path'))}. Use it only as a secondary comparison for early layout, never as higher-priority visual truth than the original image.\n"
        f"- SVG template IR JSON: {_path_for_prompt('svg/svg_template_ir.json')}. Use it only as a low-priority editable-geometry hint when run0 or the original image leaves an ambiguity.\n"
        f"- layout IR JSON: {_path_for_prompt('box_ir/box_ir.json')}. Treat it as a legacy detection artifact. Do not rebuild the task around old layout IR boxes; use it only as a fallback debug hint if a run0 element is missing or unclear.\n"
        f"- Attempt request context: {_path_for_prompt(kwargs.get('request_context_path'))}. Read it only for operational paths or optional response instructions.\n"
        f"- Attempt prompt copy: {_path_for_prompt(kwargs.get('prompt_path'))}. This is a saved copy of the current instructions, not a separate evidence source.\n\n"
        "Reading sequence:\n"
        "1. Start from the original image and run0 element analysis. These two sources define what the stage is trying to reproduce.\n"
        "2. Before inserting any raster image href, verify it against the asset manifest or native_backfill_request.\n"
        "3. Read OCR only when text details need help.\n"
        "4. Read SVG template IR or layout IR only as fallback hints. They must not override visible evidence or the run0 refined asset plan.\n"
        "5. Keep the request JSON compact in your reasoning. Do not print full JSON files to the terminal or logs.\n\n"
        f"{native_backfill_addendum}"
        "SOURCE POLICY\n"
        "- svg_self_draw: use editable SVG primitives/text for text, formulas, arrows, frames, tables, axes, borders, simple charts, simple icons, and simple diagram components.\n"
        "- crop: use an exact local crop image for screenshots, photos, dense raster texture, heatmaps, complex small icons, or details that are not worth or not possible to faithfully redraw as SVG.\n"
        "- crop_nobg: use a no-background crop image when the foreground object is separable and should sit on top of reconstructed editable SVG background.\n"
        "- Use run0 source labels as the default. Override run0 only when the original image and current render clearly show that another source strategy is more faithful. Record the reason in the iteration log.\n"
        "- Insert only hrefs listed in asset_manifest or native_backfill_request. Do not invent image paths, external URLs, file:// URLs, absolute paths, or base64 images.\n"
        "- Do not use raster images to cover text, arrows, panels, tables, formulas, axes, or other structure that should remain editable.\n\n"
        "RUN1 / COMPLETE FIRST PASS\n"
        "- Write semantic_0.svg.\n"
        "- It must be a complete whole-figure SVG, not a placeholder map, skeleton, gray-box map, or list of asset boxes.\n"
        "- Cover the whole canvas.\n"
        "- Use SVG/text for svg_self_draw elements.\n"
        "- Use manifest image hrefs for crop/crop_nobg elements when available.\n"
        "- Preserve run0 refined bboxes unless visible evidence shows they need adjustment.\n"
        "- Keep major objects separated and editable where appropriate.\n"
        "- Avoid overfitting tiny details before the whole figure layout is coherent.\n"
        "- Render/validate semantic_0.svg to rendered_0.png and validation_report_0.json using the validator command.\n"
        "- Record Run1 in iteration_log.md and iteration_log.jsonl, including what was created, obvious issues, and any crop/crop_nobg regions that still need source decisions.\n\n"
        "REFINE LOOP / DEFAULT 1 ROUND, MAX 2 ROUNDS\n"
        "At the start of each round:\n"
        "1. Use the latest SVG as input.\n"
        "2. Render it.\n"
        "3. Compare the render against the original image.\n"
        "4. First inspect the whole figure, then inspect local regions.\n"
        "5. Decide the highest-impact fixes yourself.\n\n"
        "Refinement budget:\n"
        "- Default: run exactly one refinement round after Run1, then finalize.\n"
        "- Skip the refinement round only when Run1 already validates and the whole-figure match is clearly acceptable.\n"
        "- Run a second refinement round only if the latest validator failed, the render is blank/broken, required raster hrefs are invalid, or one clearly fixable high-impact structure issue would block a useful PPT.\n"
        "- Do not run a third refinement round in this workflow. Preserve time for finalization.\n\n"
        "In each round, consider these issue types:\n"
        "- Whole-figure layout mismatch: canvas scale, panel positions, major blocks, relative spacing, z-order.\n"
        "- Text mismatch: missing text, wrong content, wrong grouping, wrong size, wrong baseline, wrong color.\n"
        "- Connector/arrow mismatch: missing arrows, wrong direction, wrong endpoint, wrong arrowhead, wrong layering.\n"
        "- Shape/table/axis mismatch: wrong borders, grids, ticks, legends, blocks, fills, strokes.\n"
        "- Asset source mismatch: crop/crop_nobg region redrawn badly, missing image href, wrong crop/no-background choice, image placed at the wrong bbox.\n"
        "- Editability regression: text/arrow/table/panel became raster when it should be editable.\n"
        "- PPT stability issue: unsupported SVG feature, unsafe href, invalid image reference, bad structure for SVG-to-PPT conversion.\n"
        "- Validator issue: parse error, blank render, asset_href_not_in_manifest, blocked feature, viewBox mismatch, or failed report.\n\n"
        "You may fix any number of issues in one round. You may make large changes if the current SVG is globally wrong. You may make only small changes if the current SVG is already close.\n\n"
        "Allowed refine actions:\n"
        "- Edit SVG shapes, text, groups, arrow geometry, fills, strokes, transforms, z-order, and object IDs.\n"
        "- Add or remove SVG elements when the original image supports it.\n"
        "- Insert allowed manifest/backfill image hrefs for crop/crop_nobg regions.\n"
        "- Replace an unfaithful SVG approximation with an allowed crop/crop_nobg image.\n"
        "- Replace a crop with editable SVG only when the region is visually simple and the SVG version is faithful.\n"
        "- Adjust manifest image placement/size to match run0 bboxes or visible evidence.\n"
        "- Use OCR to correct text.\n"
        "- Use Template IR or layout IR only as fallback geometry hints.\n\n"
        "Round outputs:\n"
        "- Round 1 writes semantic_1.svg, rendered_1.png, validation_report_1.json.\n"
        "- Optional Round 2 writes semantic_2.svg, rendered_2.png, validation_report_2.json.\n\n"
        "After each round, write to iteration_log.md and iteration_log.jsonl: round number, input SVG, output SVG/render/report, issues found, changes made, asset source changes if any, validation status, and stop or continue decision.\n\n"
        "Stop after Run1 or Round 1 when all of these are true:\n"
        "- The latest validator report is status=\"ok\".\n"
        "- The whole-figure render is coherent and broadly close to the original under the current constraints.\n"
        "- Text, arrows, panels, tables, axes, images, and icons are not obviously missing or broken.\n"
        "- crop/crop_nobg regions use the right allowed image source, or any exception is explicitly logged.\n"
        "- Editable structures remain editable.\n"
        "- Another round would likely improve only small details.\n\n"
        "Continue to optional Round 2 only if any of these are true:\n"
        "- The validator fails.\n"
        "- The render is blank or globally broken.\n"
        "- A visible major element is missing, malformed, or visibly misplaced.\n"
        "- A crop/crop_nobg region uses an invalid source, is redrawn badly despite an allowed image source, or is placed at the wrong bbox.\n"
        "- Editable structure has been lost where it should remain editable.\n"
        "- The SVG uses unsupported features, invalid hrefs, unsafe image references, or a PPT-unstable structure.\n\n"
        "FINALIZATION\n"
        "- Choose the latest acceptable SVG as the final result.\n"
        "- Write the accepted final SVG as semantic.svg in the attempt directory.\n"
        "- Render/validate semantic.svg to rendered.png and validation_report_final.json using the validator command.\n"
        "- Copy semantic_0.svg/rendered_0.png to the stable template SVG/render paths.\n"
        "- Copy the accepted final SVG/render to the required final SVG/rendered output paths.\n"
        "- Finish only after validation_report_final.json reports status=\"ok\".\n\n"
        "- If validation is already ok and time is being spent on minor visual tweaks, stop tweaking and finalize. A complete valid final SVG is better than an unfinished extra refinement.\n\n"
        "REQUIRED OUTPUT PATHS\n"
        f"- Required final SVG output path: {_path_for_prompt(kwargs.get('output_svg_path'))}\n"
        f"- Required final rendered PNG path: {_path_for_prompt(kwargs.get('output_rendered_path'))}\n"
        f"- Stable template SVG copy path: {_path_for_prompt(kwargs.get('template_svg_path'))}\n"
        f"- Stable template rendered PNG copy path: {_path_for_prompt(kwargs.get('template_rendered_path'))}\n"
        f"- Required human-readable iteration log: {_path_for_prompt(kwargs.get('iteration_log_path'))}\n"
        f"- Required machine-readable iteration log: {_path_for_prompt(kwargs.get('iteration_log_jsonl_path'))}\n"
        f"- SVG validator script: {_path_for_prompt(kwargs.get('validator_script_path'))}\n"
        f"- SVG validator command template: {_path_for_prompt(kwargs.get('validator_command'))}\n"
        "- If useful, write brief notes to the optional response path named in the request context.\n\n"
        "OVERALL RENDERING RULES\n"
        "- Use shell commands inside this full-access Codex SDK workspace to render intermediate SVGs before revising them.\n"
        "- Prefer Google Chrome/Chromium headless when available, for example with --headless=new, --allow-file-access-from-files, --screenshot=<rendered_N.png>, and the SVG file URI.\n"
        "- If Chrome is unavailable or fails, use another local renderer available in the environment, such as Python with CairoSVG, rsvg-convert, resvg, ImageMagick, or a small Pillow fallback only for diagnostics.\n"
        "- Do not stop after rendering; inspect the rendered PNG output and revise unless the strict stop condition is already met.\n\n"
        "OVERALL VALIDATION RULES\n"
        "- You must run this validator after each semantic_N.svg you create: "
        f"{_path_for_prompt(kwargs.get('validator_command'))}\n"
        "- Replace <SVG_PATH>, <PNG_PATH>, and <REPORT_PATH> with the current files, for example semantic_0.svg, rendered_0.png, and validation_report_0.json.\n"
        "- If validation_report_N.json has status=\"failed\", read every issue and revise before continuing. In particular, fix asset_href_not_in_manifest, unsafe references, parse failures, viewBox mismatches, and blank renders yourself inside this turn.\n"
        "- Before ending, run the same validator on the final semantic.svg/rendered.png with validation_report_final.json and only finish if it reports status=\"ok\".\n\n"
        "OVERALL SOURCE PRIORITY\n"
        "1. Visible evidence in the original/current reference image wins.\n"
        "2. Codex run0 asset analysis is the primary structured plan for refined asset boundaries and svg_self_draw/crop/crop_nobg source choices.\n"
        "3. Rendered outputs from your intermediate SVGs show your own current mistakes and must guide revisions.\n"
        "4. Asset manifest and native_backfill_request entries are authoritative for allowed crop/crop_nobg image hrefs in every SVG generation stage.\n"
        "5. OCR is an auxiliary source for text details.\n"
        "6. SVG template IR, layout IR, and attempt feedback are fallback hints; re-check the original image and run0 plan before applying them.\n\n"
        "OVERALL SVG/PPT PROFILE\n"
        f"{_template_text_rendering_instruction(text_rendering)}\n"
        f"{_ir_refine_text_rendering_instruction(text_rendering)}\n"
        "For run0 crop/crop_nobg regions, prefer the allowed exact/no-background crop href when the content is complex or visually coupled to raster details. Use editable SVG approximation only when the region is visually simple enough or no allowed href exists, and record that source decision in the iteration log. "
        "Keep panels, arrows, text, formulas, tables, and layout structure editable. Use direct SVG presentation attributes. "
        "Do not use CSS <style> blocks, filters, masks, clipPath, foreignObject, textPath, pattern fills, base64 images, absolute paths, <symbol>, or <use>. "
        "Do not use placeholder metadata such as data-placeholder-kind, data-asset-id, or data-asset-placeholder.\n\n"
        f"{attempt_feedback_section}"
        "FINAL CHECK BEFORE ENDING THIS TURN\n"
        "- semantic_0.svg exists and has render/validation output.\n"
        "- 0-2 refine rounds were run. If 0 rounds were run, explain why Run1 already met the stop condition. If 2 rounds were run, explain the validator failure or high-impact issue that justified it.\n"
        "- semantic.svg and rendered.png are the accepted final outputs.\n"
        "- validation_report_final.json is status=\"ok\".\n"
        "- iteration_log.md and iteration_log.jsonl explain every round and stop/continue decision.\n"
        "- Keep the final chat response short; files are the source of truth.\n"
    )


def _native_backfill_shared_prompt(kwargs: Mapping[str, Any]) -> str:
    request_path = kwargs.get("native_backfill_request_path")
    if not request_path:
        return ""
    return (
        "NATIVE SVG BACKFILL MODE\n"
        f"- Candidate request JSON: {_path_for_prompt(request_path)}\n"
        f"- Helper tools directory: {_path_for_prompt(kwargs.get('native_backfill_tools_dir'))}\n"
        f"- Writable backfill assets directory: {_path_for_prompt(kwargs.get('native_backfill_assets_dir'))}\n"
        "- This mode exists only for candidate regions where native SVG visibly fails after rendering or where visual evidence indicates the region should be restored from an exact/no-background crop instead of redrawn.\n"
        "- Prefer editable SVG whenever it is visually acceptable. Backfill only candidate regions with visible failures or content that is unsuitable for faithful native-SVG reconstruction, such as lost photos, dense icons, screenshots, or texture-like patches.\n"
        "- SVG image href values must come only from the run0 asset manifest or from candidate.preserve_href/candidate.nobg_href in native_backfill_request.json.\n"
        "- Treat source_image, source_region_preview, native_backfill_previews, and svg_to_ppt/assets/crops files as read-only visual evidence; never paste those paths into an SVG href.\n"
        "- Never backfill panels, arrows, text, formulas, tables, grids, borders, or whole-slide structure.\n\n"
    )


def _native_backfill_mode_prompt(kwargs: Mapping[str, Any], phase: str) -> str:
    request_path = kwargs.get("native_backfill_request_path")
    if not request_path:
        return ""
    tools_dir = _path_for_prompt(kwargs.get("native_backfill_tools_dir"))
    assets_dir = _path_for_prompt(kwargs.get("native_backfill_assets_dir"))
    href_prefix = _path_for_prompt(kwargs.get("native_backfill_asset_href_prefix"))
    candidate_count = kwargs.get("native_backfill_candidate_count")
    if phase in {"template"} or str(phase).startswith("visual_review_"):
        permission = (
            "In this stage, inspect native/backfill candidates only as risk signals. "
            "Do not create or reference raster backfill images yet; leave the region as editable SVG or a neutral supported shape and note the risk."
        )
    else:
        permission = (
            "In this final/merged stage, you should backfill a candidate when your rendered SVG is worse than the original exact region, "
            "or when you judge from visual evidence that the region should not be made as native SVG and should instead be restored by crop backfill. "
            "Use one exact crop or one no-background crop per selected candidate, and use the href listed in native_backfill_request.json."
        )
    return (
        "NATIVE SVG BACKFILL MODE\n"
        f"- Candidate request JSON: {_path_for_prompt(request_path)}\n"
        f"- Candidate count: {candidate_count if candidate_count is not None else '-'}\n"
        f"- Helper tools directory: {tools_dir}\n"
        f"- Writable assets directory: {assets_dir}\n"
        f"- Allowed href prefix: {href_prefix}\n"
        f"- {permission}\n"
        "- For each candidate you consider, compare candidate.source_region_preview and an exact crop from your rendered SVG at the same bbox.\n"
        "- Exact crop command for original source assets:\n"
        f"  python {tools_dir}/crop_region.py --request {_path_for_prompt(request_path)} --asset-id <asset_id>\n"
        "- Optional exact crop command for checking a rendered SVG region:\n"
        f"  python {tools_dir}/crop_region.py --request {_path_for_prompt(request_path)} --asset-id <asset_id> --source rendered --rendered-image <rendered_png> --out <debug_crop_png>\n"
        "- Optional lightweight background removal command:\n"
        f"  python {tools_dir}/remove_background.py --request {_path_for_prompt(request_path)} --asset-id <asset_id>\n"
        "- Use background removal only for an isolated foreground subject on a removable plain/light/neutral background, or when policy.background_policy says transparent_subject. Preserve the crop for landscape/photo/texture/heatmap-like regions.\n"
        "- Use href=\"<candidate.preserve_href>\" for preserved crop or href=\"<candidate.nobg_href>\" for no-background crop. If you run a helper tool, copy the JSON result's href value exactly.\n"
        "- Do not use source_image, source_region_preview, native_backfill_previews, ../svg_to_ppt/assets/crops/*.png, absolute paths, file:// URLs, external URLs, or guessed crop paths as SVG href values.\n"
        "- The validator allows only manifest hrefs and the native backfill hrefs listed in native_backfill_request.json; any other local image path is invalid.\n\n"
    )


def _thread_turn_base_svg_line(kwargs: Mapping[str, Any]) -> str:
    base_svg_path = kwargs.get("base_svg_path")
    if not base_svg_path:
        return ""
    return f"- Current input template SVG: {_path_for_prompt(base_svg_path)}\n"


def _base_svg_source_section(kwargs: Mapping[str, Any], file_context_mode: bool, *, heading: str) -> str:
    if file_context_mode:
        base_svg_path = kwargs.get("base_svg_path")
        if base_svg_path:
            source_label = "validated visual template SVG" if "Validated visual template" in heading else "current template SVG"
            return (
                f"{heading}:\n"
                f"Read the {source_label} from: {_path_for_prompt(base_svg_path)}\n"
                "Do not rely on an inline SVG copy; inspect that file directly in the workspace before editing.\n\n"
            )
    return f"{heading}:\n{kwargs.get('base_svg') or ''}\n\n"


def _codex_workspace_context_addendum(kwargs: Mapping[str, Any]) -> str:
    lines = [
        "\n\nMUST READ FILES:",
        f"- Sandbox cwd / run root: {_path_for_prompt(kwargs.get('workspace_dir'))}",
        f"- Target figure image: {_path_for_prompt(kwargs.get('figure_path'))}",
        f"- Reference image: {_path_for_prompt(kwargs.get('reference_image_path'))}",
        f"- layout IR JSON: {_path_for_prompt('box_ir/box_ir.json')}",
        f"- SVG template IR JSON: {_path_for_prompt('svg/svg_template_ir.json')}",
        f"- Asset manifest JSON: {_path_for_prompt('svg_to_ppt/assets/asset_manifest.json')}",
        f"- Codex run0 refined asset/source analysis JSON: {_path_for_prompt('reports/element_analysis_codex/element_analysis.json')}",
        f"- Attempt request context: {_path_for_prompt(kwargs.get('request_context_path'))}",
        f"- Attempt prompt copy: {_path_for_prompt(kwargs.get('prompt_path'))}",
    ]
    base_svg_path = kwargs.get("base_svg_path")
    if base_svg_path:
        lines.append(f"- Current input template SVG: {_path_for_prompt(base_svg_path)}")
    output_svg_path = kwargs.get("output_svg_path")
    output_response_path = kwargs.get("output_response_path")
    lines.extend(
        [
            "",
            "WORKSPACE RULES:",
            "- You may use shell commands inside this workspace to inspect files, compare SVGs, render/check intermediate outputs, and write outputs.",
            "- You may freely read files under the sandbox cwd / run root listed above.",
            "- Do not use MCP tools, apps, web search, memories, multi-agent delegation, hooks, or files outside this workspace.",
            "- Do not write outputs anywhere except the required SVG path, optional notes path, validator/render intermediates, iteration logs, and any native_backfill assets explicitly named in the current turn.",
            "",
            "OUTPUT CONTRACT:",
        ]
    )
    if output_svg_path:
        lines.append(
            f"- Write exactly one complete SVG document to: {_path_for_prompt(output_svg_path)}"
        )
    else:
        lines.append("- Write exactly one complete SVG document to the required SVG output path.")
    if output_response_path:
        lines.append(
            f"- Optional notes/response path: {_path_for_prompt(output_response_path)}"
        )
    lines.extend(
        [
            "- The SVG file must start with <svg and end with </svg>.",
            "- Do not put SVG code in the final chat response.",
            "- Keep the final chat response short; the SVG output file is the source of truth.",
        ]
    )
    return "\n".join(lines) + "\n"


def _path_for_prompt(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def _template_ir_source_section(
    template_ir: Mapping[str, Any], *, file_context_mode: bool
) -> str:
    if file_context_mode:
        return (
            "Compact Template IR source:\n"
            f"Read the compact template IR from: {_path_for_prompt('svg/svg_template_ir.json')}\n"
            "Use it only as a low-priority geometry hint for broad content boxes and arrows; verify every change against Image 1.\n\n"
        )
    return (
        "Compact Template IR JSON:\n"
        f"{json.dumps(_json_safe(template_ir), ensure_ascii=False, indent=2)}\n\n"
    )


def _attempt_feedback_section(
    feedback: Mapping[str, Any],
    *,
    file_context_mode: bool,
    request_context_path: Any,
) -> str:
    if file_context_mode:
        if feedback:
            validation_report = feedback.get("validation_report")
            validation_line = (
                f"- Previous validation report: {_path_for_prompt(validation_report)}\n"
                if validation_report
                else ""
            )
            return (
                "Attempt feedback source:\n"
                f"- Read the feedback field from: {_path_for_prompt(request_context_path)}\n"
                f"{validation_line}"
                "Use prior validation issues only as repair hints; re-check the current images and files before editing.\n\n"
            )
        return (
            "Attempt feedback source:\n"
            f"- No previous attempt feedback for this attempt. Attempt context: {_path_for_prompt(request_context_path)}\n\n"
        )
    return (
        "Attempt feedback JSON:\n"
        f"{json.dumps(_json_safe(feedback), ensure_ascii=False, indent=2)}"
    )


def _raster_asset_exclusion_addendum(
    asset_manifest: Mapping[str, Any],
    *,
    file_context_mode: bool = False,
) -> str:
    exclusions: list[dict[str, Any]] = []
    for asset in iter_manifest_image_items(asset_manifest):
        bbox = _prompt_bbox(asset.get("bbox"))
        if bbox is None:
            continue
        exclusion: dict[str, Any] = {"bbox": bbox}
        asset_id = _non_empty_str(asset.get("asset_id"))
        if asset_id is not None:
            exclusion["asset_id"] = asset_id
        render_policy = _non_empty_str(asset.get("render_policy"))
        if render_policy is not None:
            exclusion["render_policy"] = render_policy
        exclusions.append(exclusion)
    if not exclusions:
        return ""
    if file_context_mode:
        return (
            "RASTER ASSET EXCLUSION ZONES:\n"
            "Raster asset exclusion zones are listed in the asset manifest. Read bbox, asset_id, and render_policy from: "
            f"{_path_for_prompt('svg_to_ppt/assets/asset_manifest.json')}\n"
            "These zones come from the run0-refined asset manifest and may be inserted as local raster <image> elements in every Run 1-3 SVG. "
            "Keep all surrounding structure editable SVG and do not redraw complex crop/crop_nobg content when an allowed href exists. "
            "Keep only simple neutral underlays where surrounding editable structure needs continuity.\n\n"
        )
    return (
        "RASTER ASSET EXCLUSION ZONES:\n"
        "These bboxes come from the run0-refined asset manifest and may be inserted as local raster <image> elements in every Run 1-3 SVG. "
        "Keep all surrounding structure editable SVG and do not redraw complex crop/crop_nobg content when an allowed href exists. "
        "Keep only simple neutral underlays where surrounding editable structure needs continuity.\n"
        f"{json.dumps(_json_safe(exclusions), ensure_ascii=False, indent=2)}\n\n"
    )


def _asset_restoration_constraints_addendum(
    asset_manifest: Mapping[str, Any],
    *,
    file_context_mode: bool = False,
) -> str:
    constraints: list[dict[str, Any]] = []
    for asset in iter_manifest_image_items(asset_manifest):
        href = _non_empty_str(asset.get("svg_href"))
        if href is None:
            continue
        record: dict[str, Any] = {
            "svg_href": href,
        }
        for source_field, target_field in (
            ("asset_id", "asset_id"),
            ("component_id", "component_id"),
            ("parent_asset_id", "parent_asset_id"),
            ("box_id", "box_id"),
            ("render_policy", "render_policy"),
            ("background_policy", "background_policy"),
            ("split_policy", "split_policy"),
        ):
            value = _non_empty_str(asset.get(source_field))
            if value is not None:
                record[target_field] = value
        bbox = _prompt_bbox(asset.get("bbox"))
        if bbox is not None:
            record["bbox"] = bbox
        constraints.append(record)

    if not constraints:
        return ""
    if file_context_mode:
        return (
            "Asset constraints for manifest-backed raster restoration:\n"
            f"Read the only allowed local raster image entries from: {_path_for_prompt('svg_to_ppt/assets/asset_manifest.json')}\n"
            "Use each asset svg_href exactly, preserve its bbox when present, and keep all other structure outside these asset bboxes editable SVG. "
            "If an asset has insertable_components, follow those component entries instead of inventing new hrefs or bboxes.\n\n"
        )
    return (
        "Compact asset constraints for manifest-backed raster restoration:\n"
        "These are the only local raster image entries the SVG may reference. "
        "Use svg_href exactly, preserve each bbox when present, and keep all other structure outside these asset bboxes editable SVG.\n"
        f"{json.dumps(_json_safe({'schema': 'drawai.svg_asset_constraints.v1', 'assets': constraints}), ensure_ascii=False, indent=2)}\n\n"
    )


def _canvas_size_for_prompt(box_ir: Mapping[str, Any]) -> tuple[int, int]:
    canvas = box_ir.get("canvas") if isinstance(box_ir, Mapping) else None
    if isinstance(canvas, Mapping):
        raw_width = canvas.get("width")
        raw_height = canvas.get("height")
    else:
        raw_width = raw_height = None
    try:
        width = int(round(float(raw_width)))
        height = int(round(float(raw_height)))
    except (TypeError, ValueError):
        return (0, 0)
    return (max(0, width), max(0, height))


def _grid_prompt_addendum(
    box_ir: Mapping[str, Any],
    phase: str,
    *,
    file_context_mode: bool = False,
) -> str:
    grid_boxes = _grid_prompt_boxes(box_ir)
    if not grid_boxes:
        return ""
    shared_rules = (
        "GRID/TABLE SVG SKILL:\n"
        "Detected grid/table layout IR regions are present. Treat these regions as soft structural hints and verify them "
        "against Image 1 before drawing. Use editable rect/line/polyline primitives for visible grid or table rules, "
        "cell boundaries, matrix frames, and row/column dividers. Do not rasterize grids or tables as image assets, "
        "pattern, mask, clipPath, filter, or CSS <style> for grid structure. Do not invent rows or columns that are not "
        "visible in Image 1. Keep cell text/formulas editable and visually aligned to their cells. Mark the main table "
        "or grid group with data-pb-role=\"grid\" or data-pb-role=\"table\" when a stable group is useful.\n"
    )
    if file_context_mode:
        shared_rules += (
            "Detected grid/table layout IR regions are available in the layout IR file. Read type=\"grid\" boxes and their bboxes from: "
            f"{_path_for_prompt('box_ir/box_ir.json')}\n"
        )
    else:
        shared_rules += (
            "Detected grid/table layout IR regions:\n"
            f"{json.dumps(_json_safe(grid_boxes), ensure_ascii=False, indent=2)}\n"
        )
    if phase == "template":
        return (
            shared_rules +
            "Template-stage instruction: create only the visible table/grid framework. Reconstruct complex non-grid regions "
            "with editable primitives or ordinary simplified shapes; do not turn grid detections into asset placeholders.\n\n"
        )
    if phase.startswith("visual_review_"):
        return (
            shared_rules +
            "Visual-review instruction: correct grid/table alignment, line counts, stroke weights, and cell spacing only "
            "where Image 1 supports the change. Delete grid lines invented by the previous template.\n\n"
        )
    if phase == "ir_refine":
        return (
            shared_rules +
            "IR-refine instruction: Preserve existing editable grid/table groups and their visible row/column structure. "
            "Do not replace them with raster assets or asset placeholders.\n\n"
        )
    return shared_rules + "\n"


def _grid_prompt_boxes(box_ir: Mapping[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    canvas = box_ir.get("canvas") if isinstance(box_ir, Mapping) else {}
    width, height = _canvas_size_for_prompt({"canvas": canvas} if isinstance(canvas, Mapping) else {})
    canvas_area = width * height
    raw_boxes = box_ir.get("boxes") if isinstance(box_ir, Mapping) else []
    if not isinstance(raw_boxes, list):
        return []

    grid_boxes: list[dict[str, Any]] = []
    for box in raw_boxes:
        if not isinstance(box, Mapping) or normalize_box_type(box.get("type")) != "grid":
            continue
        box_id = box.get("id")
        bbox = _prompt_bbox(box.get("bbox"))
        if not isinstance(box_id, str) or not box_id.strip() or bbox is None:
            continue
        area = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])
        record: dict[str, Any] = {
            "id": box_id.strip(),
            "type": "grid",
            "bbox": bbox,
        }
        if canvas_area > 0:
            record["area_ratio"] = round(area / canvas_area, 4)
        grid_boxes.append(record)

    grid_boxes.sort(key=lambda item: item.get("area_ratio", 0.0), reverse=True)
    return grid_boxes[:limit]


def _prompt_bbox(raw_bbox: Any) -> list[int] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        values = [max(0, int(round(float(value)))) for value in raw_bbox]
    except (TypeError, ValueError):
        return None
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        return None
    return values


def _positive_int_or_default(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _normalize_svg_text_rendering(value: Any) -> str:
    normalized = str(value or "model_text").strip().lower()
    return normalized if normalized == "model_text" else "model_text"


def _response_format_instruction(phase: str | None) -> str:
    if phase == "ir_refine" or str(phase or "").startswith("visual_review_"):
        return (
            "Return exactly two fenced blocks and no extra prose: first a ```modification_notes block, "
            "then a ```svg block. The modification notes must be concise, whole-figure review notes that cover all regions you changed or intentionally corrected."
        )
    return "Return raw SVG only, or a fenced ```svg block; do not include explanation."


def _template_text_rendering_instruction(text_rendering: str) -> str:
    return "render visible text directly as editable SVG <text>/<tspan> elements using OCR hints and the original image."


def _visual_review_text_rendering_instruction(text_rendering: str) -> str:
    return "Text is part of the editable reconstruction; refine visible text, formulas, orientation, font style, and placement directly."


def _ir_refine_text_rendering_instruction(text_rendering: str) -> str:
    return (
        "For complex crop-like regions, use editable SVG primitives or ordinary neutral shapes without placeholder metadata. "
        "For text and formulas, render the actual editable text directly with controlled SVG text attributes; "
        "do not defer text to local placeholder filling."
    )


def _model_text_contract(*, use_ocr_hints: bool) -> str:
    evidence_sentence = (
        "Use OCR hints as evidence, but correct OCR mistakes when Image 1 visibly disagrees. "
        if use_ocr_hints
        else "Use the visible image evidence and current template text directly; no OCR hint list is provided in this phase. "
    )
    return (
        "MODEL TEXT CONTRACT:\n"
        "Render visible labels, titles, legends, numbers, and formulas as editable SVG <text>/<tspan>; never convert text to paths or images. "
        "Each non-empty <text> must carry data-pb-role=\"label|formula|title|legend|axis\", data-pb-editable=\"true\", "
        "data-pb-text-source=\"ocr|visual_inferred|model_inferred\", and data-pb-orientation=\"horizontal|vertical-rl\". "
        "Use font-family, font-size, font-style, font-weight, fill, x, and y directly on text or tspan elements. "
        "For formulas, use Unicode math characters plus <tspan baseline-shift=\"super|sub\"> or dy adjustments for the visible SVG fallback, "
        "and store the original LaTeX source on the enclosing formula group with data-pb-formula-latex-b64 and data-pb-formula-bbox=\"x y width height\" when the source is known. "
        "A formula includes standalone mathematical variables or symbols with subscripts, superscripts, accents, Greek letters, operators, or relation signs. "
        "Mark these as formula groups even when they are short labels, legends, or isolated variables. "
        "Do not flatten formula structure into plain text such as alphai, xi2, yhat, or theta0. "
        "Do not show raw LaTeX as visible text; svg_to_ppt uses this hidden metadata to export editable Office Math when possible. "
        "For vertical text, prefer transform=\"rotate(90 cx cy)\" on the <text> element and set data-pb-orientation=\"vertical-rl\"; "
        "this is more stable for SVG-to-PPT conversion than writing-mode alone. "
        f"{evidence_sentence}"
        "Do not emit data-placeholder-kind=\"text\" or data-text-box-id text placeholders.\n\n"
    )


def _ocr_text_hint_section(box_ir: Mapping[str, Any], *, file_context_mode: bool = False) -> str:
    if file_context_mode:
        return (
            "OCR text evidence source:\n"
            f"- OCR boxes JSON: {_path_for_prompt('ocr/ocr_boxes.json')}\n"
            f"- layout IR OCR text boxes: {_path_for_prompt('box_ir/box_ir.json')}\n"
            "Use OCR text as evidence only; correct OCR mistakes when Image 1 visibly disagrees.\n\n"
        )
    hints = _ocr_text_hints(box_ir)
    return (
        "OCR Text Hints JSON (evidence only; model must still verify against Image 1):\n"
        f"{json.dumps(_json_safe({'schema': 'drawai.svg_model_text_hints.v1', 'texts': hints}), ensure_ascii=False, indent=2)}\n\n"
    )


def _ocr_text_hints(box_ir: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_texts = box_ir.get("ocr_text_boxes") if isinstance(box_ir, Mapping) else []
    if not isinstance(raw_texts, list):
        return []
    hints: list[dict[str, Any]] = []
    for item in raw_texts:
        if not isinstance(item, Mapping):
            continue
        text = str(item.get("text") or "").strip()
        bbox = _prompt_bbox(item.get("bbox"))
        if not text or bbox is None:
            continue
        x1, y1, x2, y2 = bbox
        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        orientation = "vertical-rl" if height > width * 1.6 and len(text) > 2 else "horizontal"
        hint: dict[str, Any] = {
            "id": str(item.get("id") or ""),
            "text": text,
            "bbox": bbox,
            "orientation_hint": orientation,
        }
        hints.append(hint)
    return hints


def _non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _visual_review_focus_instruction(focus: str) -> str:
    if focus == "text_style":
        return (
            "Text/style + conservative layout review: fix readable editable text, formulas, font style/weight/color/size, baselines, "
            "superscript/subscript, legend labels, and vertical text. Also fix only obvious full-image layout issues: panel boundaries, "
            "connector endpoints/arrowheads, grid/table alignment, spacing, overlap, and z-order. Fix OCR text only when Image 1 supports it. "
            "For connector fixes, modify or delete existing geometry instead of adding parallel duplicate lines."
        )
    if focus == "layout":
        return (
            "Layout review: focus on module geometry, panel boundaries, connector routing, arrowheads, grid/table structure, overlap, "
            "z-order, spacing, and object alignment. Preserve text/style decisions unless moving them is necessary for layout fidelity, "
            "but correct visible text/style regressions when they are clearly worse than Image 1."
        )
    return "General visual review: compare the current SVG render to the original and repair the highest-impact visible differences."


def _drawai_svg_profile_prompt() -> str:
    return (
        "Target the DrawAI Scientific SVG Profile v1 for editable PPT conversion: "
        "Treat the input as an editable scientific structure diagram, not as a bitmap tracing task. "
        "First infer the visual language: background, major modules, arrows/connectors, annotations, legends, "
        "stroke weights, rounded corners, palette, gradients, typography, and flow direction. "
        "Generate the PPT-stable SVG subset that the local svg_to_ppt tool maps to native PowerPoint objects. "
        "Use rect for panels/modules/boxes, with rx/ry only for simple rounded corners. "
        "Use circle/ellipse only for simple nodes, badges, dots, or flat geometric icons. "
        "Use line/polyline for straight or orthogonal connectors, and simple path only when bends, curves, brackets, or custom geometry are really needed. "
        "Use polygon for explicit arrowheads or simple closed geometric decorations. "
        "Use text/tspan for all visible text and formulas; text must remain editable and must not be converted to paths or images. "
        "Use g for stable grouping, transforms, inherited style, and object identity. "
        "Use defs only for simple reusable markers or supported linearGradient/radialGradient fills; prefer solid fills for core semantic objects. "
        "Use image elements only for explicit local raster assets from the run0-refined asset manifest; "
        "manifest-backed images are allowed in template, visual-review, and IR-refine stages when the corresponding run0 source decision is crop or crop_nobg. "
        "Avoid symbol/use in model output; duplicate simple geometry explicitly unless a local canonicalizer expands it before conversion. "
        "Do not output CSS <style> blocks, SVG filters, feDropShadow, mask, clipPath, foreignObject, textPath, pattern fills, "
        "base64 images, external image URLs, absolute paths, or full-slide images for core semantics. "
        "Do not output <symbol> or <use>; duplicate simple geometry explicitly. "
        "Prefer explicit SVG presentation attributes on each object over CSS <style> blocks; classes may be used for identity, "
        "but fill, stroke, font-size, opacity, and dash styling should remain directly visible on the converted elements. "
        "Use stable semantic groups for major objects, for example ids prefixed with module-, flow-, annotation-, "
        "legend-, panel-, connector-, or label-. "
        "For numbered or lettered circular badges, use a simple circle/ellipse plus centered editable text; the local SVG postprocessor may bind these into data-pb-role=\"badge\" groups. "
        "Prefer orthogonal connector geometry when the source figure uses horizontal/vertical flows; route connectors "
        "to module edges and avoid crossing text, formulas, simplified complex regions, or panel centers. "
        "Use one object for each arrow whenever practical: single polygon for filled block arrows, and line/polyline/path with marker-end for thin connectors so the shaft and arrowhead stay together after SVG-to-PPT conversion. Filled or thick block arrows must be one closed shape, not a separate rectangle shaft plus triangle head. "
        "Use explicit polygon arrowheads only when marker-end cannot reproduce the source; if doing so, group the shaft and head contiguously and keep them in the same z-order band. "
        "Render connector arrows after background panels/modules and before raster image assets so they are not hidden by panel fills or restored icon crops. "
        "Preserve editable text with text/tspan throughout the SVG pipeline; formulas should render a visible SVG fallback with Unicode math characters and tspan superscript/subscript, "
        "while the enclosing formula group stores the original LaTeX source in data-pb-formula-latex-b64 and an explicit data-pb-formula-bbox=\"x y width height\" for PPT Office Math export. "
        "A formula includes standalone mathematical variables or symbols with subscripts, superscripts, accents, Greek letters, operators, or relation signs. "
        "Mark these as formula groups even when they are short labels, legends, or isolated variables. "
        "Do not flatten formula structure into plain text such as alphai, xi2, yhat, or theta0. "
        "Formula SVG example: <g id=\"label-formula-example\" data-pb-role=\"formula\" data-pb-editable=\"true\" data-pb-formula-bbox=\"100 112 220 40\" data-pb-formula-latex-b64=\"XGFscGhhX2leMitcYmV0YV9pPWNfaQ==\"><text id=\"label-formula-example-fallback\" x=\"100\" y=\"140\" font-family=\"Arial, Helvetica, sans-serif\" font-size=\"30\" font-weight=\"700\" fill=\"#111\" text-anchor=\"start\" data-pb-role=\"formula\" data-pb-editable=\"true\" data-pb-text-source=\"visual_inferred\" data-pb-orientation=\"horizontal\">&#945;<tspan baseline-shift=\"sub\" font-size=\"18\">i</tspan><tspan baseline-shift=\"super\" font-size=\"18\">2</tspan> + &#946;<tspan baseline-shift=\"sub\" font-size=\"18\">i</tspan> = c<tspan baseline-shift=\"sub\" font-size=\"18\">i</tspan></text><desc>LaTeX: \\alpha_i^2+\\beta_i=c_i</desc></g>. "
        "Do not display raw LaTeX in the visible SVG text layer, and do not use formula screenshots. "
        "Do not use filter, mask, clipPath, foreignObject, textPath, CSS animation, blend modes, or pattern fills for core semantics. "
        "Do not rasterize panels, arrows, text, formulas, grids, or whole diagram structure as images or base64. "
        "In staged generation, use <image> only for manifest-listed crop/crop_nobg assets and keep the surrounding structure editable. "
        "Add stable id/class and data-pb-role attributes to major objects: panel, connector, label, node, image, decorative, or background; "
        "mark non-editable raster assets with data-pb-editable=\"false\" and editable vectors/text with data-pb-editable=\"true\"."
    )


def _check_svg_to_ppt(
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    asset_manifest: Mapping[str, Any],
    compiler: CompilerCallable | None,
) -> dict[str, Any]:
    if not cfg.svg_to_ppt.enabled:
        return {
            "status": "ok",
            "enabled": False,
            "export_pptx": False,
            "issues": [],
            "pptx_path": None,
            "requested_export_mode": None,
            "effective_export_mode": None,
            "export_mode": None,
        }
    output_dir = paths.root / "svg_to_ppt"
    output_pptx = output_dir / f"{paths.semantic_svg.stem}.svg_to_ppt.pptx"
    if not cfg.svg_to_ppt.export_pptx:
        try:
            output_pptx.unlink()
        except FileNotFoundError:
            pass
        return {
            "status": "ok",
            "enabled": True,
            "export_pptx": False,
            "issues": [],
            "pptx_path": str(output_pptx),
            "export_backend": None,
            "requested_export_mode": None,
            "effective_export_mode": None,
            "export_mode": None,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        output_pptx.unlink()
    except FileNotFoundError:
        pass

    report_path = output_dir / "svg_to_ppt_report.json"
    try:
        if compiler is not None:
            compiler_report = compiler(paths.semantic_svg, output_pptx)
        else:
            from drawai.svg_to_ppt import SvgToPptCompiler

            compiler_report = SvgToPptCompiler().compile(
                svg_path=paths.semantic_svg,
                output_path=output_pptx,
                report_path=report_path,
            )
    except Exception as exc:  # noqa: BLE001 - export failures must be persisted in the stage report.
        return {
            "status": "failed",
            "enabled": True,
            "export_pptx": True,
            "failure_class": "svg_to_pptx_export_error",
            "issues": [
                {
                    "code": "svg_to_pptx_export_exception",
                    "message": "SVG-to-PPTX export raised an exception.",
                    "detail": _exception_payload(exc),
                }
            ],
            "exception": _exception_payload(exc),
            "pptx_path": str(output_pptx),
            "requested_export_mode": "native_shapes",
            "effective_export_mode": None,
            "export_mode": None,
        }

    if not output_pptx.exists():
        return {
            "status": "failed",
            "enabled": True,
            "export_pptx": True,
            "failure_class": "svg_to_pptx_export_error",
            "issues": [
                {
                    "code": "pptx_missing",
                    "message": "SVG-to-PPTX exporter returned without writing the expected PPTX.",
                    "detail": {"expected_pptx": str(output_pptx)},
                }
            ],
            "pptx_path": str(output_pptx),
            "compiler_report": _json_safe(compiler_report),
            "requested_export_mode": _svg_to_ppt_requested_export_mode(compiler_report),
            "effective_export_mode": _svg_to_ppt_effective_export_mode(compiler_report),
            "export_mode": _svg_to_ppt_effective_export_mode(compiler_report),
        }

    return {
        "status": "ok",
        "enabled": True,
        "export_pptx": True,
        "issues": [],
        "pptx_path": str(output_pptx),
        "export_backend": compiler_report.get("backend") if isinstance(compiler_report, Mapping) else None,
        "editable_surface": _svg_to_ppt_editable_surface(compiler_report),
        "requested_export_mode": _svg_to_ppt_requested_export_mode(compiler_report),
        "effective_export_mode": _svg_to_ppt_effective_export_mode(compiler_report),
        "export_mode": _svg_to_ppt_effective_export_mode(compiler_report),
        "compiler_report": _json_safe(compiler_report),
    }


def _svg_to_ppt_requested_export_mode(compiler_report: Any) -> str | None:
    if isinstance(compiler_report, Mapping):
        mode = compiler_report.get("requested_export_mode")
        if mode:
            return str(mode)
        return _svg_to_ppt_effective_export_mode(compiler_report)
    return None


def _agent_cli_label(agent: str) -> str:
    agent_name = str(agent or "").strip().lower()
    if agent_name == "kimi":
        return "Kimi CLI"
    if agent_name == "claude":
        return "Claude CLI"
    if agent_name == "codex":
        return "Codex CLI"
    return "Agent CLI"


def _acp_agent_label(agent: str) -> str:
    return acp_agent_label(str(agent or "").strip().lower())


def _svg_to_ppt_effective_export_mode(compiler_report: Any) -> str | None:
    if not isinstance(compiler_report, Mapping):
        return None
    mode = compiler_report.get("effective_export_mode") or compiler_report.get("export_mode")
    if mode:
        return str(mode)
    backend = str(compiler_report.get("backend") or "")
    if backend == "drawai_native_shapes":
        return "native_shapes"
    return None


def _svg_to_ppt_editable_surface(compiler_report: Any) -> str | None:
    if not isinstance(compiler_report, Mapping):
        return None
    editable_surface = compiler_report.get("editable_surface")
    if editable_surface:
        return str(editable_surface)
    backend = str(compiler_report.get("backend") or "")
    if backend == "drawai_native_shapes":
        return "native_shapes"
    return None


def _exception_payload(exc: BaseException) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _svg_to_ppt_validation_asset_manifest(
    paths: DrawAiArtifactPaths,
    asset_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    return extend_asset_manifest_for_svg_export(paths.root, asset_manifest)


def _native_backfill_validation_assets_for_export(paths: DrawAiArtifactPaths) -> list[dict[str, Any]]:
    return native_backfill_validation_assets_for_export(paths.root)


def _run_codex_run0_asset_analysis(cfg: DrawAiPipelineConfig, paths: DrawAiArtifactPaths) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    build_report_script = repo_root / "scripts" / "build_assemble_debug_report.py"
    element_analysis_script = repo_root / "scripts" / "run_codex_element_analysis.py"
    _run_repo_script(
        [
            sys.executable,
            str(build_report_script),
            str(paths.root),
        ],
        repo_root=repo_root,
        label="assemble debug report",
    )
    if cfg.svg.generation_backend == "acp_agent" or cfg.model_runtime.provider == "acp-agent":
        element_analysis_invoker = "acp_agent"
    elif cfg.svg.generation_backend == "agent_cli" or cfg.model_runtime.provider == "agent-cli":
        element_analysis_invoker = "agent_cli"
    else:
        element_analysis_invoker = "cli"
    command = [
        sys.executable,
        str(element_analysis_script),
        str(paths.root),
        "--max-workers",
        "1",
        "--invoker",
        element_analysis_invoker,
        "--reasoning-effort",
        "medium",
        "--timeout-seconds",
        str(float(cfg.model_runtime.timeout_seconds)),
    ]
    model_name = str(cfg.model_runtime.model_name or "").strip()
    if model_name:
        command.extend(["--model", model_name])
    if element_analysis_invoker == "agent_cli":
        command.extend(["--agent-cli-agent", cfg.model_runtime.cli.agent])
        if cfg.model_runtime.cli.command:
            command.append("--agent-cli-command")
            command.extend(cfg.model_runtime.cli.command)
    if element_analysis_invoker == "acp_agent":
        command.extend(["--acp-agent", cfg.model_runtime.acp.agent])
        if cfg.model_runtime.acp.command:
            command.append("--acp-agent-command")
            command.extend(cfg.model_runtime.acp.command)
    _run_repo_script(command, repo_root=repo_root, label="Codex run0 asset analysis")


def _run_repo_script(command: list[str], *, repo_root: Path, label: str) -> None:
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr_tail = completed.stderr[-4000:] if completed.stderr else ""
        stdout_tail = completed.stdout[-2000:] if completed.stdout else ""
        raise RuntimeError(
            f"{label} failed with returncode={completed.returncode}. "
            f"stdout tail: {stdout_tail} stderr tail: {stderr_tail}"
        )


def _reset_run_owned_outputs(
    paths: DrawAiArtifactPaths,
    *,
    preserve_external_refinement_analysis: bool = False,
) -> None:
    files = [
        paths.stage_status_json,
        paths.pipeline_summary_json,
        paths.stage_io_manifest_json,
        paths.run_package_json,
        paths.v2_fusion_trace_json,
        paths.v2_refine_trace_json,
        paths.v2_processor_trace_jsonl,
        paths.v2_processor_trace_jsonl.with_suffix(".plan.json"),
        paths.original_image,
        paths.figure_image,
        paths.source_metadata,
        paths.raw_regions_json,
        paths.sam_boxes_by_prompt_json,
        paths.semantic_svg,
        paths.rendered_png,
        paths.svg_validation_report_json,
        paths.svg_to_ppt_export_report_json,
        paths.svg_dir / "svg_validation_report.json",
        paths.element_analysis_request_json,
        paths.element_analysis_validation_json,
        paths.element_analysis_status_json,
        paths.element_analysis_prompt_txt,
        paths.element_analysis_trace_jsonl,
        paths.ocr_boxes_json,
        paths.initial_asset_decisions_json,
        paths.svg_recoverable_assets_json,
        paths.asset_decisions_json,
        paths.asset_manifest_json,
        _asset_policy_report_path(paths),
        paths.asset_recovery_reference_png,
        paths.asset_recovery_reference_legend_png,
        paths.svg_generation_reference_png,
        paths.svg_generation_reference_legend_png,
        paths.svg_dir / "svg_generation_reference_legend.json",
        paths.template_reference_png,
        paths.template_reference_legend_png,
        paths.svg_dir / "asset_recovery_reference.png",
        paths.svg_dir / "asset_recovery_reference_legend.png",
        paths.svg_dir / "asset_recovery_reference_legend.json",
        paths.svg_template_ir_json,
        paths.template_svg,
        paths.template_rendered_png,
    ]
    if not preserve_external_refinement_analysis:
        files.append(paths.element_analysis_json)
    files.extend(paths.box_ir_dir.glob("*.json"))
    files.extend(paths.box_ir_dir.glob("*.png"))
    for path in files:
        _unlink_run_owned_path(path, paths.root)
    for directory in (
        paths.prompt_runs_dir,
        paths.sam_prompt_overlays_dir,
        paths.crops_dir,
        paths.attempts_dir,
        paths.template_iterations_dir,
        paths.trace_dir,
        paths.root / "svg_to_ppt",
        paths.reports_dir / "assemble_debug",
        paths.v2_elements_dir,
        paths.v2_parser_outputs_dir,
        paths.exports_dir,
    ):
        _clear_run_owned_directory_contents(directory, paths.root)
    _clear_refinement_analysis_dir(
        paths,
        preserve_external_refinement_analysis=preserve_external_refinement_analysis,
    )


def _reset_outputs_from_stage(paths: DrawAiArtifactPaths, from_stage: str) -> None:
    if from_stage == "input_normalized":
        _reset_run_owned_outputs(paths)
        return

    for report_path in (paths.stage_status_json, paths.pipeline_summary_json):
        _unlink_run_owned_path(report_path, paths.root)

    start_index = RERUNNABLE_STAGE_ORDER.index(from_stage)
    for stage in RERUNNABLE_STAGE_ORDER[start_index:]:
        _clear_stage_outputs(paths, stage)


def _clear_stage_outputs(paths: DrawAiArtifactPaths, stage: str) -> None:
    if stage == "input_normalized":
        for path in (paths.original_image, paths.figure_image, paths.source_metadata):
            _unlink_run_owned_path(path, paths.root)
        return

    if stage == "sam3_completed":
        for path in (paths.raw_regions_json, paths.sam_boxes_by_prompt_json):
            _unlink_run_owned_path(path, paths.root)
        for directory in (paths.prompt_runs_dir, paths.sam_prompt_overlays_dir):
            _clear_run_owned_directory_contents(directory, paths.root)
        return

    if stage == "box_ir_merged":
        for path in (
            paths.box_ir_raw_json,
            paths.box_ir_merged_json,
            paths.box_ir_json,
            paths.merge_trace_json,
            paths.box_merge_diagnostics_json,
        ):
            _unlink_run_owned_path(path, paths.root)
        return

    if stage == "semantic_overlay_rendered":
        for path in (
            paths.semantic_overlay_png,
            paths.semantic_overlay_legend_png,
            paths.box_ir_dir / "semantic_overlay_legend.json",
        ):
            _unlink_run_owned_path(path, paths.root)
        return

    if stage == "ocr_completed":
        for path in (
            paths.ocr_boxes_json,
            paths.box_ir_json,
            paths.svg_template_ir_json,
            paths.final_semantic_overlay_png,
            paths.final_semantic_overlay_legend_png,
        ):
            _unlink_run_owned_path(path, paths.root)
        return

    if stage == "asset_decisions_completed":
        for path in _asset_decision_stage_outputs(paths, include_asset_policy=True).values():
            _unlink_run_owned_path(Path(path), paths.root)
        return

    if stage == "assets_materialized":
        _unlink_run_owned_path(paths.asset_manifest_json, paths.root)
        _clear_run_owned_directory_contents(paths.crops_dir, paths.root)
        return

    if stage == "codex_run0_asset_analysis_completed":
        _clear_run_owned_directory_contents(paths.element_analysis_dir, paths.root)
        _clear_run_owned_directory_contents(paths.reports_dir / "assemble_debug", paths.root)
        return

    if stage == "svg_generated":
        for path in (
            paths.semantic_svg,
            paths.rendered_png,
            paths.template_svg,
            paths.template_rendered_png,
            paths.svg_validation_report_json,
            paths.svg_dir / "svg_validation_report.json",
        ):
            _unlink_run_owned_path(path, paths.root)
        for directory in (paths.attempts_dir, paths.template_iterations_dir, paths.trace_dir):
            _clear_run_owned_directory_contents(directory, paths.root)
        return

    if stage == "svg_to_ppt_exported":
        for path in (
            paths.svg_to_ppt_export_report_json,
            paths.root / "svg_to_ppt" / "semantic.svg_to_ppt.pptx",
            paths.root / "svg_to_ppt" / "svg_to_ppt_report.json",
        ):
            _unlink_run_owned_path(path, paths.root)
        return

    raise ValueError(f"Unsupported stage for reset: {stage}")


def _reset_v2_outputs_from_stage(
    paths: DrawAiArtifactPaths,
    from_stage: str,
    *,
    preserve_external_refinement_analysis: bool = False,
) -> None:
    if from_stage == "prepare":
        _reset_run_owned_outputs(
            paths,
            preserve_external_refinement_analysis=preserve_external_refinement_analysis,
        )
        return

    for report_path in (paths.stage_status_json, paths.pipeline_summary_json):
        _unlink_run_owned_path(report_path, paths.root)

    start_index = V2_RERUNNABLE_STAGE_ORDER.index(from_stage)
    for stage in V2_RERUNNABLE_STAGE_ORDER[start_index:]:
        _clear_v2_stage_outputs(
            paths,
            stage,
            preserve_external_refinement_analysis=preserve_external_refinement_analysis,
        )


def _clear_v2_stage_outputs(
    paths: DrawAiArtifactPaths,
    stage: str,
    *,
    preserve_external_refinement_analysis: bool = False,
) -> None:
    if stage == "prepare":
        for path in (paths.original_image, paths.figure_image, paths.source_metadata):
            _unlink_run_owned_path(path, paths.root)
        return

    if stage == "parse_elements":
        for path in (paths.raw_regions_json, paths.sam_boxes_by_prompt_json, paths.ocr_boxes_json):
            _unlink_run_owned_path(path, paths.root)
        for directory in (paths.prompt_runs_dir, paths.sam_prompt_overlays_dir, paths.v2_parser_outputs_dir):
            _clear_run_owned_directory_contents(directory, paths.root)
        return

    if stage == "fuse_elements":
        for path in (
            paths.run_package_json,
            paths.v2_fusion_trace_json,
            paths.v2_refine_trace_json,
            paths.v2_processor_trace_jsonl,
            paths.v2_processor_trace_jsonl.with_suffix(".plan.json"),
            paths.asset_manifest_json,
            paths.box_ir_raw_json,
            paths.box_ir_merged_json,
            paths.box_ir_json,
            paths.merge_trace_json,
            paths.box_merge_diagnostics_json,
            paths.svg_template_ir_json,
        ):
            _unlink_run_owned_path(path, paths.root)
        _clear_refinement_analysis_dir(
            paths,
            preserve_external_refinement_analysis=preserve_external_refinement_analysis,
        )
        _clear_run_owned_directory_contents(paths.v2_elements_dir, paths.root)
        return

    if stage == "refine_elements":
        for path in (
            paths.v2_refine_trace_json,
            paths.v2_processor_trace_jsonl,
            paths.v2_processor_trace_jsonl.with_suffix(".plan.json"),
            paths.asset_manifest_json,
        ):
            _unlink_run_owned_path(path, paths.root)
        _clear_refinement_analysis_dir(
            paths,
            preserve_external_refinement_analysis=preserve_external_refinement_analysis,
        )
        return

    if stage == "plan_assets":
        for path in (
            paths.v2_processor_trace_jsonl,
            paths.v2_processor_trace_jsonl.with_suffix(".plan.json"),
            paths.asset_manifest_json,
        ):
            _unlink_run_owned_path(path, paths.root)
        return

    if stage == "process_assets":
        for path in (
            paths.v2_processor_trace_jsonl,
            paths.asset_manifest_json,
        ):
            _unlink_run_owned_path(path, paths.root)
        return

    if stage == "compose_svg":
        for path in (
            paths.semantic_svg,
            paths.rendered_png,
            paths.svg_validation_report_json,
        ):
            _unlink_run_owned_path(path, paths.root)
        return

    if stage == "export":
        for path in (
            paths.svg_to_ppt_export_report_json,
            paths.root / "svg_to_ppt" / "semantic.svg_to_ppt.pptx",
            paths.root / "svg_to_ppt" / "svg_to_ppt_report.json",
        ):
            _unlink_run_owned_path(path, paths.root)
        _clear_run_owned_directory_contents(paths.exports_dir, paths.root)
        return

    if stage == "package_run":
        # The v2 run package is a rolling state file read and rewritten by
        # late stages, so downstream resets must not remove it.
        return

    raise ValueError(f"Unsupported v2 stage for reset: {stage}")


def _unlink_run_owned_path(path: Path, root: Path) -> None:
    path = Path(path)
    if not _is_relative_to(path, root):
        raise RuntimeError(f"Refusing to delete path outside DrawAI output root: {path}")
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except FileNotFoundError:
        pass


def _clear_run_owned_directory_contents(directory: Path, root: Path) -> None:
    directory = Path(directory)
    if not _is_relative_to(directory, root):
        raise RuntimeError(f"Refusing to clear directory outside DrawAI output root: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    for child in directory.iterdir():
        _unlink_run_owned_path(child, root)


def _clear_refinement_analysis_dir(
    paths: DrawAiArtifactPaths,
    *,
    preserve_external_refinement_analysis: bool,
) -> None:
    if preserve_external_refinement_analysis:
        _clear_run_owned_directory_contents_preserving(
            paths.element_analysis_dir,
            paths.root,
            preserved_paths=(paths.element_analysis_json,),
        )
        return
    _clear_run_owned_directory_contents(paths.element_analysis_dir, paths.root)


def _clear_run_owned_directory_contents_preserving(
    directory: Path,
    root: Path,
    *,
    preserved_paths: Sequence[Path],
) -> None:
    directory = Path(directory)
    if not _is_relative_to(directory, root):
        raise RuntimeError(f"Refusing to clear directory outside DrawAI output root: {directory}")
    preserved = {Path(path).resolve() for path in preserved_paths}
    directory.mkdir(parents=True, exist_ok=True)
    for child in directory.iterdir():
        if child.resolve() in preserved:
            continue
        _unlink_run_owned_path(child, root)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _validate_or_raise(box_ir: Mapping[str, Any], label: str) -> None:
    issues = validate_box_ir(box_ir)
    if issues:
        raise ValueError(f"Invalid {label}: " + "; ".join(issues))


def _summary(
    status: str,
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    stages: list[str],
    *,
    failed_stage: str | None = None,
    exception: BaseException | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "drawai.pipeline_summary.v1",
        "status": status,
        "config_path": str(cfg.config_path) if cfg.config_path is not None else None,
        "output_dir": str(paths.root),
        "stages": stages,
        "artifacts": _artifact_summary(paths),
    }
    if failed_stage is not None:
        payload["failed_stage"] = failed_stage
    if exception is not None:
        payload["exception"] = _exception_summary(exception)
    return payload


def _exception_summary(exception: BaseException) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": type(exception).__name__,
        "message": _sanitize_summary_string(str(exception)),
        "traceback": _safe_metadata(traceback.format_exception_only(type(exception), exception)),
    }
    if isinstance(exception, AssetSelectionError):
        payload["asset_selection"] = {
            "attempt_issues": _safe_metadata(exception.attempt_issues),
        }
    if isinstance(exception, SvgGenerationError):
        payload["svg_generation"] = {
            "attempt_reports": _safe_metadata(exception.attempt_reports),
            "last_issues": _safe_metadata(exception.last_issues),
            "metadata": _safe_metadata(exception.metadata),
        }
    return payload


def _config_load_failure_summary(
    config_path_or_config: str | Path | DrawAiPipelineConfig,
    exception: BaseException,
) -> dict[str, Any]:
    if isinstance(config_path_or_config, DrawAiPipelineConfig):
        config_path = (
            str(config_path_or_config.config_path) if config_path_or_config.config_path else None
        )
    else:
        config_path = str(config_path_or_config)
    return {
        "schema": "drawai.pipeline_summary.v1",
        "status": "failed",
        "config_path": config_path,
        "output_dir": None,
        "stages": [],
        "failed_stage": "config_loaded",
        "artifacts": {},
        "exception": _exception_summary(exception),
    }


def _artifact_summary(paths: DrawAiArtifactPaths) -> dict[str, str]:
    return {
        "run_package": str(paths.run_package_json),
        "v2_elements": str(paths.v2_elements_dir),
        "v2_parser_outputs": str(paths.v2_parser_outputs_dir),
        "v2_fusion_trace": str(paths.v2_fusion_trace_json),
        "v2_refine_trace": str(paths.v2_refine_trace_json),
        "v2_processor_trace": str(paths.v2_processor_trace_jsonl),
        "exports": str(paths.exports_dir),
        "original_image": str(paths.original_image),
        "figure_image": str(paths.figure_image),
        "source_metadata": str(paths.source_metadata),
        "raw_regions": str(paths.raw_regions_json),
        "sam_boxes_by_prompt": str(paths.sam_boxes_by_prompt_json),
        "sam_prompt_overlays": str(paths.sam_prompt_overlays_dir),
        "box_ir_raw": str(paths.box_ir_raw_json),
        "box_ir_merged": str(paths.box_ir_merged_json),
        "box_ir": str(paths.box_ir_json),
        "merge_trace": str(paths.merge_trace_json),
        "box_merge_diagnostics": str(paths.box_merge_diagnostics_json),
        "semantic_overlay": str(paths.semantic_overlay_png),
        "semantic_overlay_legend_image": str(paths.semantic_overlay_legend_png),
        "final_semantic_overlay": str(paths.final_semantic_overlay_png),
        "final_semantic_overlay_legend_image": str(paths.final_semantic_overlay_legend_png),
        "ocr_boxes": str(paths.ocr_boxes_json),
        "initial_asset_decisions": str(paths.initial_asset_decisions_json),
        "svg_recoverable_assets": str(paths.svg_recoverable_assets_json),
        "asset_decisions": str(paths.asset_decisions_json),
        "asset_manifest": str(paths.asset_manifest_json),
        "asset_policy_report": str(_asset_policy_report_path(paths)),
        "asset_recovery_reference": str(paths.asset_recovery_reference_png),
        "asset_recovery_reference_legend_image": str(paths.asset_recovery_reference_legend_png),
        "svg_generation_reference": str(paths.svg_generation_reference_png),
        "svg_generation_reference_legend_image": str(paths.svg_generation_reference_legend_png),
        "visual_template_reference": str(paths.template_reference_png),
        "visual_template_reference_legend_image": str(paths.template_reference_legend_png),
        "svg_template_ir": str(paths.svg_template_ir_json),
        "template_iterations": str(paths.template_iterations_dir),
        "template_svg": str(paths.template_svg),
        "template_rendered_png": str(paths.template_rendered_png),
        "semantic_svg": str(paths.semantic_svg),
        "rendered_png": str(paths.rendered_png),
        "svg_validation_report": str(paths.svg_validation_report_json),
        "svg_to_ppt_export_report": str(paths.svg_to_ppt_export_report_json),
        "element_analysis": str(paths.element_analysis_json),
        "element_analysis_validation": str(paths.element_analysis_validation_json),
        "element_analysis_status": str(paths.element_analysis_status_json),
        "stage_status": str(paths.stage_status_json),
        "stage_io_manifest": str(paths.stage_io_manifest_json),
        "pipeline_summary": str(paths.pipeline_summary_json),
    }


def _copy_if_exists(source: Path, target: Path) -> None:
    if not source.exists() or source.resolve(strict=False) == target.resolve(strict=False):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value


def _safe_metadata(value: Any) -> Any:
    safe = _json_safe(value)
    return _redact_sensitive_metadata(safe)


def _redact_sensitive_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lower_key = key_text.lower()
            normalized_key = lower_key.replace("-", "_")
            if lower_key == "authorization" or "api_key" in normalized_key:
                redacted[key_text] = "[redacted]"
            elif lower_key in {"image_base64", "base64", "data", "payload"} and (
                lower_key == "payload" or _looks_like_base64(item)
            ):
                redacted[key_text] = "[redacted-base64]" if _looks_like_base64(item) else "[redacted]"
            elif lower_key.endswith("payload") and isinstance(item, str) and _looks_like_base64(item):
                redacted[key_text] = "[redacted-base64]"
            else:
                redacted[key_text] = _redact_sensitive_metadata(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_metadata(item) for item in value]
    if isinstance(value, str):
        return _sanitize_summary_string(value)
    return value


_DATA_URL_RE = re.compile(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+")
_AUTH_BEARER_RE = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;\"']+")
_AUTH_HEADER_RE = re.compile(r"(?i)(authorization\s*:\s*)[^\n\r,;\"']+")
_BARE_BEARER_RE = re.compile(
    r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{20,}|[A-Za-z0-9._~+/=-]*[._~+/=-][A-Za-z0-9._~+/=-]*)"
)
_API_KEY_ASSIGN_RE = re.compile(r"(?i)(\bapi[_-]?key\s*[=:]\s*)[^\s,;\"']+")
_X_API_KEY_HEADER_RE = re.compile(r"(?i)(\bx-api-key\s*:\s*)[^\s,;\"']+")
_BASE64_ASSIGN_RE = re.compile(
    r"(?i)(\b(?:payload|image_base64|data)\s*=\s*)([A-Za-z0-9+/=]{24,})"
)


def _sanitize_summary_string(value: str) -> str:
    text = _DATA_URL_RE.sub("[redacted-inline-image-base64]", value)
    text = _AUTH_BEARER_RE.sub(r"\1[redacted]", text)
    text = _AUTH_HEADER_RE.sub(r"\1[redacted]", text)
    text = _X_API_KEY_HEADER_RE.sub(r"\1[redacted]", text)
    text = _API_KEY_ASSIGN_RE.sub(r"\1[redacted]", text)
    text = _BASE64_ASSIGN_RE.sub(r"\1[redacted-base64]", text)
    text = _BARE_BEARER_RE.sub(r"\1[redacted]", text)
    if len(text) > 4000:
        return f"{text[:1000]}\n...[summary metadata truncated len={len(text)}]"
    return text


def _looks_like_base64(value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 32:
        return False
    return all(char.isalnum() or char in "+/=\n\r\t " for char in value)


__all__ = ["STAGE_ORDER", "run_drawai_pipeline"]
