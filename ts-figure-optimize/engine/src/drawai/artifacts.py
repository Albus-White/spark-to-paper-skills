from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DrawAiArtifactPaths:
    root: Path
    inputs_dir: Path
    original_image: Path
    figure_image: Path
    source_metadata: Path
    sam3_dir: Path
    sam_masks_dir: Path
    prompt_runs_dir: Path
    sam_prompt_overlays_dir: Path
    raw_regions_json: Path
    sam_boxes_by_prompt_json: Path
    box_ir_dir: Path
    box_ir_raw_json: Path
    box_ir_merged_json: Path
    box_ir_json: Path
    merge_trace_json: Path
    box_merge_diagnostics_json: Path
    semantic_overlay_png: Path
    semantic_overlay_legend_png: Path
    final_semantic_overlay_png: Path
    final_semantic_overlay_legend_png: Path
    ocr_dir: Path
    ocr_boxes_json: Path
    assets_dir: Path
    crops_dir: Path
    initial_asset_decisions_json: Path
    svg_recoverable_assets_json: Path
    asset_decisions_json: Path
    asset_manifest_json: Path
    svg_dir: Path
    asset_recovery_reference_png: Path
    asset_recovery_reference_legend_png: Path
    svg_generation_reference_png: Path
    svg_generation_reference_legend_png: Path
    template_reference_png: Path
    template_reference_legend_png: Path
    svg_template_ir_json: Path
    template_svg: Path
    template_rendered_png: Path
    semantic_svg: Path
    rendered_png: Path
    attempts_dir: Path
    template_iterations_dir: Path
    reports_dir: Path
    pipeline_summary_json: Path
    svg_validation_report_json: Path
    svg_to_ppt_export_report_json: Path
    element_analysis_dir: Path
    element_analysis_json: Path
    element_analysis_request_json: Path
    element_analysis_validation_json: Path
    element_analysis_status_json: Path
    element_analysis_prompt_txt: Path
    element_analysis_trace_jsonl: Path
    stage_status_json: Path
    stage_io_manifest_json: Path
    trace_dir: Path


def prepare_artifact_paths(root: str | Path) -> DrawAiArtifactPaths:
    root_path = Path(root).expanduser().resolve()
    inputs_dir = root_path / "inputs"
    sam3_dir = root_path / "sam3"
    sam_masks_dir = sam3_dir / "masks"
    prompt_runs_dir = sam3_dir / "prompt_runs"
    sam_prompt_overlays_dir = sam3_dir / "prompt_overlays"
    box_ir_dir = root_path / "box_ir"
    ocr_dir = root_path / "ocr"
    svg_dir = root_path / "svg"
    assets_dir = root_path / "svg_to_ppt" / "assets"
    crops_dir = assets_dir / "crops"
    attempts_dir = svg_dir / "attempts"
    template_iterations_dir = svg_dir / "template_iterations"
    reports_dir = root_path / "reports"
    element_analysis_dir = reports_dir / "element_analysis_codex"
    trace_dir = root_path / "trace"

    for directory in (
        root_path,
        inputs_dir,
        sam3_dir,
        sam_masks_dir,
        prompt_runs_dir,
        sam_prompt_overlays_dir,
        box_ir_dir,
        ocr_dir,
        assets_dir,
        crops_dir,
        svg_dir,
        attempts_dir,
        template_iterations_dir,
        reports_dir,
        trace_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    return DrawAiArtifactPaths(
        root=root_path,
        inputs_dir=inputs_dir,
        original_image=inputs_dir / "original.png",
        figure_image=inputs_dir / "figure.png",
        source_metadata=inputs_dir / "source_metadata.json",
        sam3_dir=sam3_dir,
        sam_masks_dir=sam_masks_dir,
        prompt_runs_dir=prompt_runs_dir,
        sam_prompt_overlays_dir=sam_prompt_overlays_dir,
        raw_regions_json=sam3_dir / "raw_regions.json",
        sam_boxes_by_prompt_json=sam3_dir / "sam_boxes_by_prompt.json",
        box_ir_dir=box_ir_dir,
        box_ir_raw_json=box_ir_dir / "box_ir.raw.json",
        box_ir_merged_json=box_ir_dir / "box_ir.merged.json",
        box_ir_json=box_ir_dir / "box_ir.json",
        merge_trace_json=box_ir_dir / "merge_trace.json",
        box_merge_diagnostics_json=box_ir_dir / "box_merge_diagnostics.json",
        semantic_overlay_png=box_ir_dir / "semantic_overlay.png",
        semantic_overlay_legend_png=box_ir_dir / "semantic_overlay_legend.png",
        final_semantic_overlay_png=box_ir_dir / "final_semantic_overlay.png",
        final_semantic_overlay_legend_png=box_ir_dir / "final_semantic_overlay_legend.png",
        ocr_dir=ocr_dir,
        ocr_boxes_json=ocr_dir / "ocr_boxes.json",
        assets_dir=assets_dir,
        crops_dir=crops_dir,
        initial_asset_decisions_json=assets_dir / "initial_asset_decisions.json",
        svg_recoverable_assets_json=assets_dir / "svg_recoverable_assets.json",
        asset_decisions_json=assets_dir / "asset_decisions.json",
        asset_manifest_json=assets_dir / "asset_manifest.json",
        svg_dir=svg_dir,
        asset_recovery_reference_png=svg_dir / "asset_recovery_reference.png",
        asset_recovery_reference_legend_png=svg_dir / "asset_recovery_reference_legend.png",
        svg_generation_reference_png=svg_dir / "svg_generation_reference.png",
        svg_generation_reference_legend_png=svg_dir / "svg_generation_reference_legend.png",
        template_reference_png=svg_dir / "template_reference.png",
        template_reference_legend_png=svg_dir / "template_reference_legend.png",
        svg_template_ir_json=svg_dir / "svg_template_ir.json",
        template_svg=svg_dir / "template.svg",
        template_rendered_png=svg_dir / "template_rendered.png",
        semantic_svg=svg_dir / "semantic.svg",
        rendered_png=svg_dir / "rendered.png",
        attempts_dir=attempts_dir,
        template_iterations_dir=template_iterations_dir,
        reports_dir=reports_dir,
        pipeline_summary_json=reports_dir / "pipeline_summary.json",
        svg_validation_report_json=reports_dir / "svg_validation_report.json",
        svg_to_ppt_export_report_json=reports_dir / "svg_to_ppt_export_report.json",
        element_analysis_dir=element_analysis_dir,
        element_analysis_json=element_analysis_dir / "element_analysis.json",
        element_analysis_request_json=element_analysis_dir / "element_analysis_request.json",
        element_analysis_validation_json=element_analysis_dir / "validation.json",
        element_analysis_status_json=element_analysis_dir / "run_status.json",
        element_analysis_prompt_txt=element_analysis_dir / "prompt.txt",
        element_analysis_trace_jsonl=element_analysis_dir / "codex_element_analysis_trace.jsonl",
        stage_status_json=reports_dir / "stage_status.json",
        stage_io_manifest_json=reports_dir / "stage_io_manifest.json",
        trace_dir=trace_dir,
    )


def write_json(path: str | Path, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_stage_status(
    paths: DrawAiArtifactPaths,
    stage: str,
    status: str,
    message: str = "",
) -> None:
    payload: dict[str, Any] = {}
    if paths.stage_status_json.exists():
        with paths.stage_status_json.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            payload = loaded

    stages = payload.get("stages")
    if not isinstance(stages, dict):
        stages = {}
    stages[stage] = {"status": status, "message": message}
    payload["latest_stage"] = stage
    payload["latest_status"] = status
    payload["stages"] = stages
    write_json(paths.stage_status_json, payload)
