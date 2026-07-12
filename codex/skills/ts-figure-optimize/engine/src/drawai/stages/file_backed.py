from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from drawai.artifacts import DrawAiArtifactPaths
from drawai.config import DrawAiPipelineConfig
from drawai.core import ArtifactRef, ArtifactStore, ProviderRef, RunContext, StageResult, StageSpec
from drawai.svg_to_ppt_check import CompilerCallable
from drawai.v2.stages import V2_STAGE_ORDER, V2StageOptions, build_v2_stage_specs

FILE_BACKED_STAGE_ORDER = (
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
)

_CHAIN_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "input_normalized": (),
    "sam3_completed": ("input_normalized",),
    "box_ir_merged": ("sam3_completed",),
    "semantic_overlay_rendered": ("box_ir_merged",),
    "ocr_completed": ("semantic_overlay_rendered",),
    "asset_decisions_completed": ("ocr_completed",),
    "codex_run0_asset_analysis_completed": ("asset_decisions_completed",),
    "assets_materialized": ("codex_run0_asset_analysis_completed",),
    "svg_generated": ("assets_materialized",),
    "svg_to_ppt_exported": ("svg_generated",),
}

_STAGE_OUTPUT_PATHS: Mapping[str, Mapping[str, str]] = {
    "input_normalized": {
        "original_image": "original_image",
        "figure_image": "figure_image",
        "source_metadata": "source_metadata",
    },
    "sam3_completed": {
        "raw_regions": "raw_regions_json",
        "sam_boxes_by_prompt": "sam_boxes_by_prompt_json",
    },
    "box_ir_merged": {
        "raw_box_ir": "box_ir_raw_json",
        "merged_box_ir": "box_ir_merged_json",
        "box_ir": "box_ir_json",
        "merge_trace": "merge_trace_json",
        "box_merge_diagnostics": "box_merge_diagnostics_json",
    },
    "semantic_overlay_rendered": {
        "semantic_overlay": "semantic_overlay_png",
        "semantic_overlay_legend_image": "semantic_overlay_legend_png",
        "semantic_overlay_legend": "semantic_overlay_legend_json",
    },
    "ocr_completed": {
        "ocr_boxes": "ocr_boxes_json",
        "box_ir": "box_ir_json",
        "svg_template_ir": "svg_template_ir_json",
        "final_semantic_overlay": "final_semantic_overlay_png",
        "final_semantic_overlay_legend_image": "final_semantic_overlay_legend_png",
    },
    "asset_decisions_completed": {
        "initial_asset_decisions": "initial_asset_decisions_json",
        "svg_recoverable_assets": "svg_recoverable_assets_json",
        "asset_decisions": "asset_decisions_json",
        "asset_recovery_reference": "asset_recovery_reference_png",
        "asset_recovery_reference_legend_image": "asset_recovery_reference_legend_png",
        "svg_generation_reference": "svg_generation_reference_png",
        "svg_generation_reference_legend_image": "svg_generation_reference_legend_png",
        "visual_template_reference": "template_reference_png",
        "visual_template_reference_legend_image": "template_reference_legend_png",
    },
    "codex_run0_asset_analysis_completed": {
        "element_analysis": "element_analysis_json",
        "element_analysis_validation": "element_analysis_validation_json",
        "element_analysis_status": "element_analysis_status_json",
    },
    "assets_materialized": {
        "asset_manifest": "asset_manifest_json",
    },
    "svg_generated": {
        "semantic_svg": "semantic_svg",
        "rendered_png": "rendered_png",
        "svg_validation_report": "svg_validation_report_json",
    },
    "svg_to_ppt_exported": {
        "svg_to_ppt_export_report": "svg_to_ppt_export_report_json",
    },
}

_PROVIDER_REFS: Mapping[str, tuple[ProviderRef, ...]] = {
    "sam3_completed": (ProviderRef("sam3_transport", "SamDetector", required=False),),
    "ocr_completed": (ProviderRef("ocr_provider", "OcrDetector", required=False),),
    "assets_materialized": (ProviderRef("rmbg_client", "BackgroundRemover", required=False),),
    "codex_run0_asset_analysis_completed": (
        ProviderRef("model_runtime", "ModelRuntime", required=False),
    ),
    "svg_generated": (
        ProviderRef("svg_invoker", "SvgGenerator", required=False),
        ProviderRef("model_runtime", "ModelRuntime", required=False),
    ),
    "svg_to_ppt_exported": (ProviderRef("svg_to_ppt_compiler", "PptExporter", required=False),),
}


@dataclass(frozen=True)
class FileBackedStageOptions:
    sam3_transport: Any | None = None
    ocr_provider: Any | None = None
    rmbg_client: Any | None = None
    svg_invoker: Any | None = None
    svg_to_ppt_compiler: CompilerCallable | None = None

    def provider_mapping(self) -> dict[str, Any]:
        providers = {
            "sam3_transport": self.sam3_transport,
            "ocr_provider": self.ocr_provider,
            "rmbg_client": self.rmbg_client,
            "svg_invoker": self.svg_invoker,
            "svg_to_ppt_compiler": self.svg_to_ppt_compiler,
        }
        return {name: provider for name, provider in providers.items() if provider is not None}


def build_file_backed_run_context(
    cfg: DrawAiPipelineConfig,
    paths: DrawAiArtifactPaths,
    *,
    options: FileBackedStageOptions | None = None,
) -> RunContext:
    resolved_options = options or FileBackedStageOptions()
    return RunContext(
        config={
            "pipeline_config": cfg,
            "artifact_paths": paths,
            "file_backed_stage_options": resolved_options,
        },
        artifacts=ArtifactStore(paths.root),
        providers=resolved_options.provider_mapping(),
        metadata={"execution_mode": "file_stage_runner"},
    )


def build_file_backed_stage_specs(
    stage_ids: Iterable[str],
    *,
    options: FileBackedStageOptions | None = None,
) -> list[StageSpec]:
    selected = tuple(stage_ids)
    if selected and all(stage_id in V2_STAGE_ORDER for stage_id in selected):
        v2_options = V2StageOptions(
            sam3_transport=(options.sam3_transport if options is not None else None),
            ocr_provider=(options.ocr_provider if options is not None else None),
            rmbg_client=(options.rmbg_client if options is not None else None),
            svg_invoker=(options.svg_invoker if options is not None else None),
            svg_to_ppt_compiler=(options.svg_to_ppt_compiler if options is not None else None),
        )
        return build_v2_stage_specs(selected, options=v2_options)
    _validate_stage_ids(selected)
    selected_set = set(selected)
    return [
        StageSpec(
            stage_id=stage_id,
            depends_on=tuple(dependency for dependency in _CHAIN_DEPENDENCIES[stage_id] if dependency in selected_set),
            outputs=tuple(_STAGE_OUTPUT_PATHS[stage_id]),
            providers=_PROVIDER_REFS.get(stage_id, ()),
            run=_stage_runner(stage_id, options or FileBackedStageOptions()),
        )
        for stage_id in selected
    ]


def _stage_runner(stage_id: str, options: FileBackedStageOptions):
    def run(context: RunContext) -> StageResult:
        from drawai.pipeline import _run_file_backed_stage

        cfg = cast(DrawAiPipelineConfig, context.config["pipeline_config"])
        paths = cast(DrawAiArtifactPaths, context.config["artifact_paths"])
        _run_file_backed_stage(
            stage_id,
            cfg,
            paths,
            sam3_transport=options.sam3_transport,
            ocr_provider=options.ocr_provider,
            rmbg_client=options.rmbg_client,
            svg_invoker=options.svg_invoker,
            svg_to_ppt_compiler=options.svg_to_ppt_compiler,
        )
        return StageResult.ok(
            stage_id,
            artifacts=_register_stage_outputs(context.artifacts, paths, stage_id),
        )

    return run


def _register_stage_outputs(
    store: ArtifactStore,
    paths: DrawAiArtifactPaths,
    stage_id: str,
) -> dict[str, ArtifactRef]:
    return {
        artifact_id: store.register(artifact_id, _resolve_stage_output(paths, path_name))
        for artifact_id, path_name in _STAGE_OUTPUT_PATHS[stage_id].items()
    }


def _resolve_stage_output(paths: DrawAiArtifactPaths, path_name: str) -> Path:
    if path_name == "semantic_overlay_legend_json":
        return paths.box_ir_dir / "semantic_overlay_legend.json"
    return cast(Path, getattr(paths, path_name))


def _validate_stage_ids(stage_ids: tuple[str, ...]) -> None:
    if len(stage_ids) == 0:
        raise ValueError("at least one file-backed stage is required")
    unknown = [stage_id for stage_id in stage_ids if stage_id not in FILE_BACKED_STAGE_ORDER]
    if unknown:
        raise ValueError(f"unknown file-backed stage: {', '.join(unknown)}")
