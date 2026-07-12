from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from .artifacts import prepare_artifact_paths, write_json
from .config import DrawAiPipelineConfig
from .pipeline import PipelineInvoker, _load_config, run_drawai_pipeline_from_stage
from .sam3_client import JsonTransport
from .svg_to_ppt_check import CompilerCallable
from .v2.stages import V2_STAGE_ORDER

PUBLIC_STAGE_ORDER = V2_STAGE_ORDER

LEGACY_STAGE_ALIASES = {
    "detect_structure": "parse_elements",
    "detect_text": "parse_elements",
    "assemble_boxir": "fuse_elements",
    "asset_plan": "plan_assets",
    "asset_analyze": "refine_elements",
    "asset_materialize": "process_assets",
    "svg": "compose_svg",
}

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

    canonical_stage = _canonical_stage(stage)
    summary = run_drawai_pipeline_from_stage(
        cfg,
        "prepare",
        to_stage=canonical_stage,
        sam3_transport=sam3_transport,
        ocr_provider=ocr_provider,
        rmbg_client=rmbg_client,
        svg_invoker=svg_invoker,
        svg_to_ppt_compiler=svg_to_ppt_compiler,
    )
    _annotate_public_summary(
        summary,
        cfg,
        public_stage=canonical_stage,
        stage_alias=stage if stage != canonical_stage else None,
        sources=sources,
    )
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
    summary = run_drawai_pipeline_from_stage(
        cfg,
        "prepare",
        to_stage="package_run",
        sam3_transport=sam3_transport,
        ocr_provider=ocr_provider,
        rmbg_client=rmbg_client,
        svg_invoker=svg_invoker,
        svg_to_ppt_compiler=svg_to_ppt_compiler,
    )
    _annotate_public_summary(
        summary,
        cfg,
        public_stage="all",
        stage_alias=None,
        sources=sources,
    )
    return summary


def _canonical_stage(stage: str) -> str:
    canonical_stage = LEGACY_STAGE_ALIASES.get(stage, stage)
    if canonical_stage not in PUBLIC_STAGE_ORDER:
        accepted = ", ".join((*PUBLIC_STAGE_ORDER, *LEGACY_STAGE_ALIASES, "all"))
        raise ValueError(f"stage must be one of {accepted}; got {stage!r}")
    return canonical_stage


def _annotate_public_summary(
    summary: dict[str, Any],
    cfg: DrawAiPipelineConfig,
    *,
    public_stage: str,
    stage_alias: str | None,
    sources: BoxIrAssemblySources,
) -> None:
    summary["public_stage"] = public_stage
    if stage_alias is not None:
        summary["stage_alias"] = stage_alias
    summary["sources"] = sources
    summary["public_stages"] = list(PUBLIC_STAGE_ORDER)
    write_json(prepare_artifact_paths(cfg.input.output_dir).pipeline_summary_json, summary)
