from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Any

import yaml

from .prompt_plan import DEFAULT_SAM3_PROMPTS, Sam3Prompt

RECOGNIZED_OCR_PROVIDERS = frozenset({"remote_paddleocr", "fixture"})
RECOGNIZED_ASSET_SELECTION_PROVIDERS = frozenset({"deterministic"})
RECOGNIZED_SVG_GENERATION_BACKENDS = frozenset(
    {"responses", "sdk_tool_loop", "codex_python_sdk_controlled", "agent_cli"}
)
RECOGNIZED_SVG_TEXT_RENDERING = frozenset({"model_text"})
RECOGNIZED_VISUAL_REVIEW_ROUNDS = frozenset({"text_style", "layout"})
RECOGNIZED_RMBG_PROVIDERS = frozenset({"service"})
RECOGNIZED_CODEX_REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})
RECOGNIZED_AGENT_CLI_AGENTS = frozenset({"kimi", "claude", "codex", "openclaw", "hermes", "custom"})


@dataclass(frozen=True)
class InputNormalizationConfig:
    enabled: bool = True
    target_long_edge: int = 3840
    upscale_only: bool = True
    flatten_transparency_background: str = "#ffffff"


@dataclass(frozen=True)
class DrawAiInputConfig:
    image: Path
    output_dir: Path
    normalization: InputNormalizationConfig = InputNormalizationConfig()


@dataclass(frozen=True)
class Sam3Config:
    base_url: str = "http://127.0.0.1:18080"
    timeout_seconds: float = 600
    return_overlay: bool = True
    return_masks: bool = False
    service_merge_threshold: float = 0.0
    prompts: tuple[Sam3Prompt, ...] = DEFAULT_SAM3_PROMPTS


@dataclass(frozen=True)
class Sam3PromptConfig(Sam3Prompt):
    level: str | None = None
    max_masks: int | None = None


@dataclass(frozen=True)
class RemotePaddleOcrConfig:
    base_url: str = "http://127.0.0.1:18080"
    timeout_seconds: float = 600


@dataclass(frozen=True)
class FixtureOcrConfig:
    path: Path | None = None


@dataclass(frozen=True)
class OcrConfig:
    provider: str = "remote_paddleocr"
    remote_paddleocr: RemotePaddleOcrConfig = RemotePaddleOcrConfig()
    fixture: FixtureOcrConfig = FixtureOcrConfig()


@dataclass(frozen=True)
class AssetSelectionConfig:
    provider: str = "deterministic"
    max_attempts: int = 3
    disallow_crop_roles: tuple[str, ...] = ("arrow", "border", "grid", "text", "content_box")
    max_area_ratio: float = 0.35


@dataclass(frozen=True)
class RmbgConfig:
    enabled: bool = False
    provider: str = "service"
    base_url: str = "http://127.0.0.1:18080"
    timeout_seconds: float = 600
    model_path: str = ""


@dataclass(frozen=True)
class AssetMaterializationConfig:
    rmbg: RmbgConfig = RmbgConfig()


@dataclass(frozen=True)
class AssetPolicyConfig:
    enabled: bool = True


@dataclass(frozen=True)
class DrawAiSvgConfig:
    max_attempts: int = 8
    timeout_seconds: float = 1500
    generation_backend: str = "codex_python_sdk_controlled"
    staged_generation: bool = True
    text_rendering: str = "model_text"
    visual_review_rounds: tuple[str, ...] = ("text_style",)


@dataclass(frozen=True)
class DrawAiSvgToPptConfig:
    enabled: bool = True
    export_pptx: bool = True


@dataclass(frozen=True)
class AgentCliConfig:
    agent: str = "kimi"
    command: tuple[str, ...] = ()

    def to_runtime_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "command": list(self.command),
        }


@dataclass(frozen=True)
class ModelRuntimeConfig:
    provider: str = "codex-python-sdk"
    connection_id: str = "codex-python-sdk-controlled"
    model_name: str = "gpt-5.5"
    reasoning_effort: str = "xhigh"
    image_model_name: str = ""
    base_url: str = ""
    api_key: str = ""
    extra_headers: dict[str, str] | None = None
    timeout_seconds: float = 600
    concurrency_mode: str = "auto"
    max_concurrent: int = 20
    max_critic_rounds: int = 3
    cli: AgentCliConfig = AgentCliConfig()

    def to_runtime_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "connection_id": self.connection_id,
            "model_name": self.model_name,
            "reasoning_effort": self.reasoning_effort,
            "image_model_name": self.image_model_name,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "extra_headers": dict(self.extra_headers or {}),
            "timeout_seconds": self.timeout_seconds,
            "concurrency_mode": self.concurrency_mode,
            "max_concurrent": self.max_concurrent,
            "max_critic_rounds": self.max_critic_rounds,
            "cli": self.cli.to_runtime_dict(),
        }


@dataclass(frozen=True)
class DrawAiPipelineConfig:
    input: DrawAiInputConfig
    sam3: Sam3Config = Sam3Config()
    ocr: OcrConfig = OcrConfig()
    asset_selection: AssetSelectionConfig = AssetSelectionConfig()
    asset_materialization: AssetMaterializationConfig = AssetMaterializationConfig()
    asset_policy: AssetPolicyConfig = AssetPolicyConfig()
    svg: DrawAiSvgConfig = DrawAiSvgConfig()
    svg_to_ppt: DrawAiSvgToPptConfig = DrawAiSvgToPptConfig()
    model_runtime: ModelRuntimeConfig = ModelRuntimeConfig()
    config_path: Path | None = None


def load_drawai_config(path: str | Path, validate_input_exists: bool = True) -> DrawAiPipelineConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"DrawAI config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    data = _require_mapping(payload, "config")

    cfg = DrawAiPipelineConfig(
        input=_parse_input_config(data.get("input"), config_path.parent),
        sam3=_parse_sam3_config(data.get("sam3")),
        ocr=_parse_ocr_config(data.get("ocr"), config_path.parent),
        asset_selection=_parse_asset_selection_config(data.get("asset_selection")),
        asset_materialization=_parse_asset_materialization_config(data.get("asset_materialization")),
        asset_policy=_parse_asset_policy_config(data.get("asset_policy")),
        svg=_parse_svg_config(data.get("svg")),
        svg_to_ppt=_parse_svg_to_ppt_config(data.get("svg_to_ppt")),
        model_runtime=_parse_model_runtime_config(data.get("model_runtime")),
        config_path=config_path,
    )
    _validate_config(cfg, validate_input_exists=validate_input_exists)
    return cfg


def _parse_input_config(raw: Any, base_dir: Path) -> DrawAiInputConfig:
    data = _require_mapping(raw, "input")
    image = _resolve_config_path(_require_value(data, "input.image"), base_dir, "input.image")
    output_dir = _resolve_config_path(
        _require_value(data, "input.output_dir"),
        base_dir,
        "input.output_dir",
    )
    normalization = _parse_normalization_config(data.get("normalization"))
    return DrawAiInputConfig(image=image, output_dir=output_dir, normalization=normalization)


def _parse_normalization_config(raw: Any) -> InputNormalizationConfig:
    if raw is None:
        return InputNormalizationConfig()
    data = _require_mapping(raw, "input.normalization")
    return InputNormalizationConfig(
        enabled=_as_bool(
            data.get("enabled", InputNormalizationConfig.enabled),
            "input.normalization.enabled",
        ),
        target_long_edge=_as_int(
            data.get("target_long_edge", InputNormalizationConfig.target_long_edge),
            "input.normalization.target_long_edge",
        ),
        upscale_only=_as_bool(
            data.get("upscale_only", InputNormalizationConfig.upscale_only),
            "input.normalization.upscale_only",
        ),
        flatten_transparency_background=_as_non_empty_str(
            data.get(
                "flatten_transparency_background",
                InputNormalizationConfig.flatten_transparency_background,
            ),
            "input.normalization.flatten_transparency_background",
        ),
    )


def _parse_sam3_config(raw: Any) -> Sam3Config:
    if raw is None:
        return Sam3Config()
    data = _require_mapping(raw, "sam3")
    prompts = DEFAULT_SAM3_PROMPTS
    if "prompts" in data:
        prompts_raw = data["prompts"]
        if not isinstance(prompts_raw, list):
            raise ValueError("sam3.prompts must be a list")
        prompts = tuple(_parse_sam3_prompt(item, index) for index, item in enumerate(prompts_raw))
    return Sam3Config(
        base_url=_as_non_empty_str(data.get("base_url", Sam3Config.base_url), "sam3.base_url"),
        timeout_seconds=_as_float(
            data.get("timeout_seconds", Sam3Config.timeout_seconds),
            "sam3.timeout_seconds",
        ),
        return_overlay=_as_bool(data.get("return_overlay", Sam3Config.return_overlay), "sam3.return_overlay"),
        return_masks=_as_bool(data.get("return_masks", Sam3Config.return_masks), "sam3.return_masks"),
        service_merge_threshold=_as_float(
            data.get("service_merge_threshold", Sam3Config.service_merge_threshold),
            "sam3.service_merge_threshold",
        ),
        prompts=prompts,
    )


def _parse_sam3_prompt(raw: Any, index: int) -> Sam3Prompt:
    data = _require_mapping(raw, f"sam3.prompts[{index}]")
    prompt_id = _as_non_empty_str(_require_value(data, "id"), f"sam3.prompts[{index}].id")
    text = _as_non_empty_str(_require_value(data, "text"), f"sam3.prompts[{index}].text")
    threshold = _as_float(
        _require_value(data, "confidence_threshold"),
        f"sam3.prompts[{index}].confidence_threshold",
    )
    level = None
    if "level" in data:
        level = _as_non_empty_str(data["level"], f"sam3.prompts[{index}].level")
    max_masks = None
    if "max_masks" in data:
        max_masks = _as_int(data["max_masks"], f"sam3.prompts[{index}].max_masks")
    if level is not None or max_masks is not None:
        return Sam3PromptConfig(
            id=prompt_id,
            text=text,
            confidence_threshold=threshold,
            level=level,
            max_masks=max_masks,
        )
    return Sam3Prompt(id=prompt_id, text=text, confidence_threshold=threshold)


def _parse_ocr_config(raw: Any, base_dir: Path) -> OcrConfig:
    if raw is None:
        return OcrConfig()
    data = _require_mapping(raw, "ocr")
    return OcrConfig(
        provider=_as_non_empty_str(data.get("provider", OcrConfig.provider), "ocr.provider"),
        remote_paddleocr=_parse_remote_paddleocr_config(data.get("remote_paddleocr")),
        fixture=_parse_fixture_ocr_config(data.get("fixture"), base_dir),
    )


def _parse_remote_paddleocr_config(raw: Any) -> RemotePaddleOcrConfig:
    if raw is None:
        return RemotePaddleOcrConfig()
    data = _require_mapping(raw, "ocr.remote_paddleocr")
    return RemotePaddleOcrConfig(
        base_url=_as_non_empty_str(
            data.get("base_url", RemotePaddleOcrConfig.base_url),
            "ocr.remote_paddleocr.base_url",
        ),
        timeout_seconds=_as_float(
            data.get("timeout_seconds", RemotePaddleOcrConfig.timeout_seconds),
            "ocr.remote_paddleocr.timeout_seconds",
        ),
    )


def _parse_fixture_ocr_config(raw: Any, base_dir: Path) -> FixtureOcrConfig:
    if raw is None:
        return FixtureOcrConfig()
    data = _require_mapping(raw, "ocr.fixture")
    fixture_path = None
    if "path" in data:
        fixture_path = _resolve_config_path(data["path"], base_dir, "ocr.fixture.path")
    return FixtureOcrConfig(path=fixture_path)


def _parse_asset_selection_config(raw: Any) -> AssetSelectionConfig:
    if raw is None:
        return AssetSelectionConfig()
    data = _require_mapping(raw, "asset_selection")
    disallow_raw = data.get("disallow_crop_roles", AssetSelectionConfig.disallow_crop_roles)
    if not isinstance(disallow_raw, (list, tuple)):
        raise ValueError("asset_selection.disallow_crop_roles must be a list")
    return AssetSelectionConfig(
        provider=_as_non_empty_str(
            data.get("provider", AssetSelectionConfig.provider),
            "asset_selection.provider",
        ),
        max_attempts=_as_int(
            data.get("max_attempts", AssetSelectionConfig.max_attempts),
            "asset_selection.max_attempts",
        ),
        disallow_crop_roles=tuple(
            _as_non_empty_str(role, f"asset_selection.disallow_crop_roles[{index}]")
            for index, role in enumerate(disallow_raw)
        ),
        max_area_ratio=_as_float(
            data.get("max_area_ratio", AssetSelectionConfig.max_area_ratio),
            "asset_selection.max_area_ratio",
        ),
    )


def _parse_asset_materialization_config(raw: Any) -> AssetMaterializationConfig:
    if raw is None:
        return AssetMaterializationConfig()
    data = _require_mapping(raw, "asset_materialization")
    return AssetMaterializationConfig(
        rmbg=_parse_rmbg_config(data.get("rmbg")),
    )


def _parse_rmbg_config(raw: Any) -> RmbgConfig:
    if raw is None:
        return RmbgConfig()
    data = _require_mapping(raw, "asset_materialization.rmbg")
    return RmbgConfig(
        enabled=_as_bool(data.get("enabled", RmbgConfig.enabled), "asset_materialization.rmbg.enabled"),
        provider=_as_non_empty_str(
            data.get("provider", RmbgConfig.provider),
            "asset_materialization.rmbg.provider",
        ),
        base_url=_as_str(data.get("base_url", RmbgConfig.base_url), "asset_materialization.rmbg.base_url"),
        timeout_seconds=_as_float(
            data.get("timeout_seconds", RmbgConfig.timeout_seconds),
            "asset_materialization.rmbg.timeout_seconds",
        ),
        model_path=_as_str(
            data.get("model_path", RmbgConfig.model_path),
            "asset_materialization.rmbg.model_path",
        ),
    )


def _parse_asset_policy_config(raw: Any) -> AssetPolicyConfig:
    if raw is None:
        return AssetPolicyConfig()
    data = _require_mapping(raw, "asset_policy")
    return AssetPolicyConfig(
        enabled=_as_bool(data.get("enabled", AssetPolicyConfig.enabled), "asset_policy.enabled"),
    )


def _parse_svg_config(raw: Any) -> DrawAiSvgConfig:
    if raw is None:
        return DrawAiSvgConfig()
    data = _require_mapping(raw, "svg")
    if "template_visual_refine_rounds" in data:
        raise ValueError(
            "svg.template_visual_refine_rounds is deprecated; use svg.visual_review_rounds "
            "with text_style/layout instead"
        )
    if "local_codex_context_mode" in data:
        raise ValueError(
            "svg.local_codex_context_mode is no longer supported; use "
            "svg.generation_backend: codex_python_sdk_controlled instead"
        )
    if "sdk_runner" in data:
        raise ValueError("svg.sdk_runner is no longer supported; use svg.generation_backend directly")
    if "acp_generation_mode" in data:
        raise ValueError("svg.acp_generation_mode has been removed; use svg.generation_backend: agent_cli")
    visual_review_rounds_raw = data.get("visual_review_rounds", DrawAiSvgConfig.visual_review_rounds)
    if not isinstance(visual_review_rounds_raw, (list, tuple)):
        raise ValueError("svg.visual_review_rounds must be a list")
    return DrawAiSvgConfig(
        max_attempts=_as_int(data.get("max_attempts", DrawAiSvgConfig.max_attempts), "svg.max_attempts"),
        timeout_seconds=_as_float(
            data.get("timeout_seconds", DrawAiSvgConfig.timeout_seconds),
            "svg.timeout_seconds",
        ),
        generation_backend=_as_non_empty_str(
            data.get("generation_backend", DrawAiSvgConfig.generation_backend),
            "svg.generation_backend",
        ),
        staged_generation=_as_bool(
            data.get("staged_generation", DrawAiSvgConfig.staged_generation),
            "svg.staged_generation",
        ),
        text_rendering=_as_non_empty_str(
            data.get("text_rendering", DrawAiSvgConfig.text_rendering),
            "svg.text_rendering",
        ),
        visual_review_rounds=tuple(
            _as_non_empty_str(round_name, f"svg.visual_review_rounds[{index}]")
            for index, round_name in enumerate(visual_review_rounds_raw)
        ),
    )


def _parse_svg_to_ppt_config(raw: Any) -> DrawAiSvgToPptConfig:
    if raw is None:
        return DrawAiSvgToPptConfig()
    data = _require_mapping(raw, "svg_to_ppt")
    unsupported = sorted(set(data) - {"enabled", "export_pptx"})
    if unsupported:
        raise ValueError(
            "svg_to_ppt now only supports enabled/export_pptx; "
            f"remove unsupported keys: {', '.join(unsupported)}"
        )
    return DrawAiSvgToPptConfig(
        enabled=_as_bool(
            data.get("enabled", DrawAiSvgToPptConfig.enabled),
            "svg_to_ppt.enabled",
        ),
        export_pptx=_as_bool(
            data.get("export_pptx", DrawAiSvgToPptConfig.export_pptx),
            "svg_to_ppt.export_pptx",
        ),
    )


def _parse_model_runtime_config(raw: Any) -> ModelRuntimeConfig:
    if raw is None:
        return ModelRuntimeConfig()
    data = _require_mapping(raw, "model_runtime")
    if "acp_command" in data:
        raise ValueError("model_runtime.acp_command has been removed; use model_runtime.cli.command")
    if "kimi_command" in data:
        raise ValueError("model_runtime.kimi_command has been removed; use model_runtime.cli.command")
    return ModelRuntimeConfig(
        provider=_as_non_empty_str(
            data.get("provider", ModelRuntimeConfig.provider),
            "model_runtime.provider",
        ),
        connection_id=_as_non_empty_str(
            data.get("connection_id", ModelRuntimeConfig.connection_id),
            "model_runtime.connection_id",
        ),
        model_name=_as_str(
            data.get("model_name", ModelRuntimeConfig.model_name),
            "model_runtime.model_name",
        ),
        reasoning_effort=_as_str(
            data.get("reasoning_effort", ModelRuntimeConfig.reasoning_effort),
            "model_runtime.reasoning_effort",
        ).strip().lower(),
        image_model_name=_as_str(
            data.get("image_model_name", ModelRuntimeConfig.image_model_name),
            "model_runtime.image_model_name",
        ),
        base_url=_as_str(data.get("base_url", ModelRuntimeConfig.base_url), "model_runtime.base_url"),
        api_key=_as_str(data.get("api_key", ModelRuntimeConfig.api_key), "model_runtime.api_key"),
        extra_headers=_parse_extra_headers(data.get("extra_headers")),
        timeout_seconds=_as_float(
            data.get("timeout_seconds", ModelRuntimeConfig.timeout_seconds),
            "model_runtime.timeout_seconds",
        ),
        concurrency_mode=_as_non_empty_str(
            data.get("concurrency_mode", ModelRuntimeConfig.concurrency_mode),
            "model_runtime.concurrency_mode",
        ),
        max_concurrent=_as_int(
            data.get("max_concurrent", ModelRuntimeConfig.max_concurrent),
            "model_runtime.max_concurrent",
        ),
        max_critic_rounds=_as_int(
            data.get("max_critic_rounds", ModelRuntimeConfig.max_critic_rounds),
            "model_runtime.max_critic_rounds",
        ),
        cli=_parse_agent_cli_config(data.get("cli")),
    )


def _parse_agent_cli_config(raw: Any) -> AgentCliConfig:
    if raw is None:
        return AgentCliConfig()
    data = _require_mapping(raw, "model_runtime.cli")
    agent = _as_non_empty_str(data.get("agent", AgentCliConfig.agent), "model_runtime.cli.agent").strip().lower()
    command_raw = data.get("command", AgentCliConfig.command)
    command = _parse_agent_cli_command(command_raw)
    return AgentCliConfig(agent=agent, command=command)


def _parse_agent_cli_command(raw: Any) -> tuple[str, ...]:
    if raw in (None, ""):
        return ()
    if isinstance(raw, str):
        command = tuple(shlex.split(raw))
    elif isinstance(raw, (list, tuple)):
        command = tuple(_as_non_empty_str(item, "model_runtime.cli.command[]") for item in raw)
    else:
        raise ValueError("model_runtime.cli.command must be a string or list of strings")
    return command


def _parse_extra_headers(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    data = _require_mapping(raw, "model_runtime.extra_headers")
    return {
        _as_non_empty_str(str(key), f"model_runtime.extra_headers.{key}"): _as_str(
            value,
            f"model_runtime.extra_headers.{key}",
        )
        for key, value in data.items()
    }


def _validate_config(cfg: DrawAiPipelineConfig, validate_input_exists: bool) -> None:
    if validate_input_exists and not cfg.input.image.exists():
        raise FileNotFoundError(f"input.image does not exist: {cfg.input.image}")
    if cfg.input.normalization.target_long_edge <= 0:
        raise ValueError("input.normalization.target_long_edge must be positive")
    if cfg.sam3.timeout_seconds <= 0:
        raise ValueError("sam3.timeout_seconds must be positive")
    if cfg.sam3.service_merge_threshold < 0:
        raise ValueError("sam3.service_merge_threshold must be non-negative")
    if not cfg.sam3.prompts:
        raise ValueError("sam3.prompts must not be empty")
    for prompt in cfg.sam3.prompts:
        if not 0 <= prompt.confidence_threshold <= 1:
            raise ValueError(
                f"sam3 prompt {prompt.id!r} confidence_threshold must be between 0 and 1"
            )
        max_masks = getattr(prompt, "max_masks", None)
        if max_masks is not None and max_masks <= 0:
            raise ValueError(f"sam3 prompt {prompt.id!r} max_masks must be positive")
    if cfg.ocr.provider not in RECOGNIZED_OCR_PROVIDERS:
        supported = ", ".join(sorted(RECOGNIZED_OCR_PROVIDERS))
        raise ValueError(f"Unsupported OCR provider: {cfg.ocr.provider!r}. Expected one of: {supported}")
    if cfg.ocr.remote_paddleocr.timeout_seconds <= 0:
        raise ValueError("ocr.remote_paddleocr.timeout_seconds must be positive")
    if cfg.ocr.provider == "fixture":
        if cfg.ocr.fixture.path is None:
            raise ValueError("ocr.fixture.path is required when ocr.provider is 'fixture'")
        if validate_input_exists and not cfg.ocr.fixture.path.exists():
            raise FileNotFoundError(f"ocr.fixture.path does not exist: {cfg.ocr.fixture.path}")
    if cfg.asset_selection.provider not in RECOGNIZED_ASSET_SELECTION_PROVIDERS:
        supported = ", ".join(sorted(RECOGNIZED_ASSET_SELECTION_PROVIDERS))
        raise ValueError(
            f"Unsupported asset_selection provider: {cfg.asset_selection.provider!r}. "
            f"Expected one of: {supported}"
        )
    if cfg.asset_selection.max_attempts <= 0:
        raise ValueError("asset_selection.max_attempts must be positive")
    if not cfg.asset_selection.disallow_crop_roles:
        raise ValueError("asset_selection.disallow_crop_roles must not be empty")
    if not 0 < cfg.asset_selection.max_area_ratio <= 1:
        raise ValueError("asset_selection.max_area_ratio must be between 0 and 1")
    if cfg.asset_materialization.rmbg.enabled:
        if cfg.asset_materialization.rmbg.provider not in RECOGNIZED_RMBG_PROVIDERS:
            supported = ", ".join(sorted(RECOGNIZED_RMBG_PROVIDERS))
            raise ValueError(
                f"Unsupported asset_materialization.rmbg provider: "
                f"{cfg.asset_materialization.rmbg.provider!r}. Expected one of: {supported}"
            )
        if cfg.asset_materialization.rmbg.timeout_seconds <= 0:
            raise ValueError("asset_materialization.rmbg.timeout_seconds must be positive")
    if cfg.svg.max_attempts <= 0:
        raise ValueError("svg.max_attempts must be positive")
    if cfg.svg.timeout_seconds <= 0:
        raise ValueError("svg.timeout_seconds must be positive")
    if cfg.svg.generation_backend not in RECOGNIZED_SVG_GENERATION_BACKENDS:
        supported = ", ".join(sorted(RECOGNIZED_SVG_GENERATION_BACKENDS))
        raise ValueError(
            f"Unsupported svg.generation_backend: {cfg.svg.generation_backend!r}. "
            f"Expected one of: {supported}"
        )
    if cfg.svg.text_rendering not in RECOGNIZED_SVG_TEXT_RENDERING:
        raise ValueError(
            "svg.text_rendering must be model_text; "
            "ocr_placeholder is deprecated and no longer supported in the mainline"
        )
    for index, round_name in enumerate(cfg.svg.visual_review_rounds):
        if round_name not in RECOGNIZED_VISUAL_REVIEW_ROUNDS:
            supported = ", ".join(sorted(RECOGNIZED_VISUAL_REVIEW_ROUNDS))
            raise ValueError(
                f"svg.visual_review_rounds[{index}]={round_name!r} is unsupported. "
                f"Expected one of: {supported}"
            )
    if cfg.model_runtime.cli.agent not in RECOGNIZED_AGENT_CLI_AGENTS:
        supported = ", ".join(sorted(RECOGNIZED_AGENT_CLI_AGENTS))
        raise ValueError(
            f"Unsupported model_runtime.cli.agent: {cfg.model_runtime.cli.agent!r}. "
            f"Expected one of: {supported}"
        )
    if cfg.model_runtime.cli.agent == "custom" and not cfg.model_runtime.cli.command:
        raise ValueError("model_runtime.cli.command is required when model_runtime.cli.agent is custom")
    if cfg.model_runtime.max_concurrent <= 0:
        raise ValueError("model_runtime.max_concurrent must be positive")
    if cfg.model_runtime.max_critic_rounds < 0:
        raise ValueError("model_runtime.max_critic_rounds must be non-negative")
    if cfg.model_runtime.timeout_seconds <= 0:
        raise ValueError("model_runtime.timeout_seconds must be positive")
    if cfg.model_runtime.reasoning_effort not in RECOGNIZED_CODEX_REASONING_EFFORTS:
        supported = ", ".join(sorted(RECOGNIZED_CODEX_REASONING_EFFORTS))
        raise ValueError(
            f"model_runtime.reasoning_effort={cfg.model_runtime.reasoning_effort!r} is unsupported. "
            f"Expected one of: {supported}"
        )


def _require_mapping(raw: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a mapping")
    return raw


def _require_value(data: dict[str, Any], key: str) -> Any:
    short_key = key.rsplit(".", maxsplit=1)[-1]
    if short_key not in data:
        raise ValueError(f"{key} is required")
    return data[short_key]


def _resolve_config_path(raw: Any, base_dir: Path, field_name: str) -> Path:
    raw_text = _as_non_empty_str(raw, field_name)
    path = Path(raw_text).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _as_non_empty_str(raw: Any, field_name: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return raw


def _as_str(raw: Any, field_name: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{field_name} must be a string")
    return raw


def _as_bool(raw: Any, field_name: str) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return raw


def _as_int(raw: Any, field_name: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"{field_name} must be an integer")
    return raw


def _as_float(raw: Any, field_name: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    return float(raw)
