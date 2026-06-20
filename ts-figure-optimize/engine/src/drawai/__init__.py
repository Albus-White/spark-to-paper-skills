"""DrawAI SVG reconstruction pipeline primitives."""

from .config import (
    DrawAiInputConfig,
    DrawAiPipelineConfig,
    DrawAiSvgConfig,
    DrawAiSvgToPptConfig,
    InputNormalizationConfig,
    OcrConfig,
    Sam3Config,
    load_drawai_config,
)
from .prompt_plan import DEFAULT_SAM3_PROMPTS, Sam3Prompt


def run_drawai_pipeline(*args, **kwargs):
    from .pipeline import run_drawai_pipeline as _run_drawai_pipeline

    return _run_drawai_pipeline(*args, **kwargs)


def run_drawai_pipeline_from_stage(*args, **kwargs):
    from .pipeline import run_drawai_pipeline_from_stage as _run_drawai_pipeline_from_stage

    return _run_drawai_pipeline_from_stage(*args, **kwargs)


__all__ = [
    "DrawAiInputConfig",
    "DrawAiPipelineConfig",
    "DrawAiSvgConfig",
    "DrawAiSvgToPptConfig",
    "DEFAULT_SAM3_PROMPTS",
    "InputNormalizationConfig",
    "OcrConfig",
    "Sam3Config",
    "Sam3Prompt",
    "load_drawai_config",
    "run_drawai_pipeline",
    "run_drawai_pipeline_from_stage",
]
