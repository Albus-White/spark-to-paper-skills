from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from drawai.workflow.agent_prompt_defaults import PAGE_SPEC_PROCESSING_OPERATIONS

from .api_presets import ApiPreset, api_preset_by_id, read_workbench_api_presets


PROCESSOR_SETTINGS_SCHEMA = "drawai.workbench.processor_settings.v1"


@dataclass(frozen=True)
class ProcessorOperation:
    meaning: str
    choose_when: str
    avoid_when: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ProcessorDriverDefinition:
    driver_id: str
    label: str
    kind: str
    description: str
    required_api_preset_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProcessorDefinition:
    processing_type: str
    label: str
    default_enabled: bool
    default_driver_id: str
    supported_driver_ids: tuple[str, ...]
    default_operation: ProcessorOperation

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["supported_driver_ids"] = list(self.supported_driver_ids)
        payload["default_operation"] = self.default_operation.to_dict()
        return payload


@dataclass(frozen=True)
class ProcessorSetting:
    enabled: bool
    driver_id: str
    api_preset_id: str
    operation: ProcessorOperation

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "driver_id": self.driver_id,
            "api_preset_id": self.api_preset_id,
            "operation": self.operation.to_dict(),
        }


PROCESSOR_DRIVER_DEFINITIONS: dict[str, ProcessorDriverDefinition] = {
    "builtin_no_process": ProcessorDriverDefinition(
        driver_id="builtin_no_process",
        label="Built-in no process",
        kind="builtin",
        description="Keep the element structural and do not materialize an asset.",
    ),
    "builtin_crop": ProcessorDriverDefinition(
        driver_id="builtin_crop",
        label="Built-in crop",
        kind="builtin",
        description="Crop source pixels from the normalized figure image.",
    ),
    "rmbg_service": ProcessorDriverDefinition(
        driver_id="rmbg_service",
        label="RMBG service",
        kind="service",
        description="Crop the source region and call the configured RMBG service.",
    ),
    "builtin_svg_self_draw": ProcessorDriverDefinition(
        driver_id="builtin_svg_self_draw",
        label="Built-in SVG self draw",
        kind="builtin",
        description="Write editable SVG self-draw constraints for downstream composition.",
    ),
    "codex_imagegen_builtin": ProcessorDriverDefinition(
        driver_id="codex_imagegen_builtin",
        label="Codex ImageGen built-in",
        kind="builtin",
        description="Use DrawAI's Codex Python SDK image generation adapter.",
    ),
    "codex_image_edit_builtin": ProcessorDriverDefinition(
        driver_id="codex_image_edit_builtin",
        label="Codex Image Edit built-in",
        kind="builtin",
        description="Use DrawAI's Codex Python SDK image editing adapter.",
    ),
    "openai_images_api": ProcessorDriverDefinition(
        driver_id="openai_images_api",
        label="Images API preset",
        kind="api_preset",
        description="Use a compatible images_api preset.",
        required_api_preset_type="images_api",
    ),
    "reserved": ProcessorDriverDefinition(
        driver_id="reserved",
        label="Reserved",
        kind="reserved",
        description="Registered in schema but not executable yet.",
    ),
}


def _default_operation(processing_type: str) -> ProcessorOperation:
    operation = PAGE_SPEC_PROCESSING_OPERATIONS[processing_type]
    return ProcessorOperation(
        meaning=operation.meaning,
        choose_when=operation.choose_when,
        avoid_when=operation.avoid_when,
    )


PROCESSOR_DEFINITIONS: dict[str, ProcessorDefinition] = {
    "no_process": ProcessorDefinition(
        processing_type="no_process",
        label="No process",
        default_enabled=True,
        default_driver_id="builtin_no_process",
        supported_driver_ids=("builtin_no_process",),
        default_operation=_default_operation("no_process"),
    ),
    "crop": ProcessorDefinition(
        processing_type="crop",
        label="Crop",
        default_enabled=True,
        default_driver_id="builtin_crop",
        supported_driver_ids=("builtin_crop",),
        default_operation=_default_operation("crop"),
    ),
    "crop_nobg": ProcessorDefinition(
        processing_type="crop_nobg",
        label="Crop no background",
        default_enabled=True,
        default_driver_id="rmbg_service",
        supported_driver_ids=("rmbg_service",),
        default_operation=_default_operation("crop_nobg"),
    ),
    "svg_self_draw": ProcessorDefinition(
        processing_type="svg_self_draw",
        label="SVG self draw",
        default_enabled=False,
        default_driver_id="builtin_svg_self_draw",
        supported_driver_ids=("builtin_svg_self_draw",),
        default_operation=_default_operation("svg_self_draw"),
    ),
    "image_generate": ProcessorDefinition(
        processing_type="image_generate",
        label="Image generate",
        default_enabled=False,
        default_driver_id="codex_imagegen_builtin",
        supported_driver_ids=("codex_imagegen_builtin", "openai_images_api"),
        default_operation=_default_operation("image_generate"),
    ),
    "image_edit": ProcessorDefinition(
        processing_type="image_edit",
        label="Image edit",
        default_enabled=False,
        default_driver_id="codex_image_edit_builtin",
        supported_driver_ids=("codex_image_edit_builtin", "openai_images_api"),
        default_operation=_default_operation("image_edit"),
    ),
    "chart_rebuild_reserved": ProcessorDefinition(
        processing_type="chart_rebuild_reserved",
        label="Chart rebuild reserved",
        default_enabled=False,
        default_driver_id="reserved",
        supported_driver_ids=("reserved",),
        default_operation=_default_operation("chart_rebuild_reserved"),
    ),
}


def processor_settings_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve(strict=False) / "settings" / "processor.json"


def read_workbench_processor_settings(workspace: str | Path) -> dict[str, ProcessorSetting]:
    path = processor_settings_path(workspace)
    api_presets = read_workbench_api_presets(workspace)
    if not path.is_file():
        return _default_processor_settings()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Workbench processor settings must be a JSON object: {path}")
    return normalize_workbench_processor_settings(payload, api_presets=api_presets)


def write_workbench_processor_settings(
    workspace: str | Path,
    payload: Mapping[str, Any],
) -> dict[str, ProcessorSetting]:
    api_presets = read_workbench_api_presets(workspace)
    settings = normalize_workbench_processor_settings(payload, api_presets=api_presets)
    path = processor_settings_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_processor_settings_document(settings), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return settings


def normalize_workbench_processor_settings(
    payload: Mapping[str, Any] | None,
    *,
    api_presets: Sequence[ApiPreset] = (),
) -> dict[str, ProcessorSetting]:
    data = dict(payload or {})
    raw_processors = data.get("processors", {})
    if not isinstance(raw_processors, Mapping):
        raise ValueError("processor settings payload must contain a processors object")
    settings = _default_processor_settings()
    for processing_type, raw_setting in raw_processors.items():
        if processing_type not in PROCESSOR_DEFINITIONS:
            raise ValueError(f"unsupported processor: {processing_type}")
        if not isinstance(raw_setting, Mapping):
            raise ValueError(f"processors.{processing_type} must be an object")
        definition = PROCESSOR_DEFINITIONS[processing_type]
        current = settings[processing_type]
        enabled = _bool(raw_setting.get("enabled", current.enabled), f"processors.{processing_type}.enabled")
        driver_id = str(raw_setting.get("driver_id") or current.driver_id).strip()
        api_preset_id = str(raw_setting.get("api_preset_id") or "").strip()
        operation = _operation_from_payload(
            raw_setting.get("operation"),
            fallback=current.operation,
            field_prefix=f"processors.{processing_type}.operation",
        )
        setting = ProcessorSetting(
            enabled=enabled,
            driver_id=driver_id,
            api_preset_id=api_preset_id,
            operation=operation,
        )
        _validate_processor_setting(processing_type, definition, setting, api_presets=api_presets)
        settings[processing_type] = setting
    return settings


def workbench_processor_settings_payload(workspace: str | Path) -> dict[str, Any]:
    api_presets = read_workbench_api_presets(workspace)
    settings = read_workbench_processor_settings(workspace)
    return {
        "schema": PROCESSOR_SETTINGS_SCHEMA,
        "definitions": processor_definitions_payload(),
        "settings": _processor_settings_document(settings),
        "validation": processor_settings_validation(settings, api_presets=api_presets),
    }


def processor_definitions_payload() -> dict[str, Any]:
    return {
        "processors": {
            processing_type: definition.to_dict()
            for processing_type, definition in PROCESSOR_DEFINITIONS.items()
        },
        "drivers": {
            driver_id: definition.to_dict()
            for driver_id, definition in PROCESSOR_DRIVER_DEFINITIONS.items()
        },
    }


def processor_settings_validation(
    settings: Mapping[str, ProcessorSetting],
    *,
    api_presets: Sequence[ApiPreset] = (),
) -> dict[str, Any]:
    processors: dict[str, Any] = {}
    for processing_type, definition in PROCESSOR_DEFINITIONS.items():
        setting = settings[processing_type]
        message = ""
        configured = False
        try:
            _validate_processor_setting(processing_type, definition, setting, api_presets=api_presets)
            configured = setting.enabled and _processor_setting_configured(setting, api_presets=api_presets)
        except ValueError as exc:
            message = str(exc)
        processors[processing_type] = {
            "enabled": setting.enabled,
            "configured": configured,
            "valid": message == "",
            "message": message,
        }
    return {"processors": processors}


def resolved_processor_operation_config(workspace: str | Path) -> dict[str, Any]:
    api_presets = read_workbench_api_presets(workspace)
    settings = read_workbench_processor_settings(workspace)
    return resolved_processor_operation_config_from_settings(settings, api_presets=api_presets)


def resolved_processor_operation_config_from_settings(
    settings: Mapping[str, ProcessorSetting],
    *,
    api_presets: Sequence[ApiPreset] = (),
) -> dict[str, Any]:
    validation = processor_settings_validation(settings, api_presets=api_presets)["processors"]
    processing_types: list[str] = []
    operations: dict[str, Any] = {}
    for processing_type in PROCESSOR_DEFINITIONS:
        setting = settings[processing_type]
        status = validation[processing_type]
        if not setting.enabled or not status["configured"] or not status["valid"]:
            continue
        processing_types.append(processing_type)
        operations[processing_type] = setting.operation.to_dict()
    if not processing_types:
        raise ValueError("at least one configured processor must be enabled")
    return {
        "page_spec_processing_types": processing_types,
        "page_spec_processing_operations": operations,
    }


def require_processor_configured(
    workspace: str | Path,
    processing_type: str,
) -> ProcessorSetting:
    api_presets = read_workbench_api_presets(workspace)
    settings = read_workbench_processor_settings(workspace)
    return require_processor_configured_from_settings(settings, processing_type, api_presets=api_presets)


def require_processor_configured_from_settings(
    settings: Mapping[str, ProcessorSetting],
    processing_type: str,
    *,
    api_presets: Sequence[ApiPreset] = (),
) -> ProcessorSetting:
    if processing_type not in PROCESSOR_DEFINITIONS:
        raise ValueError(f"unsupported processor: {processing_type}")
    setting = settings.get(processing_type)
    if setting is None:
        raise ValueError(f"processor setting is missing: {processing_type}")
    if not setting.enabled:
        raise ValueError(f"processor is disabled: {processing_type}")
    definition = PROCESSOR_DEFINITIONS[processing_type]
    _validate_processor_setting(processing_type, definition, setting, api_presets=api_presets)
    if not _processor_setting_configured(setting, api_presets=api_presets):
        raise ValueError(f"processor is not configured: {processing_type}")
    return setting


def _default_processor_settings() -> dict[str, ProcessorSetting]:
    return {
        processing_type: ProcessorSetting(
            enabled=definition.default_enabled,
            driver_id=definition.default_driver_id,
            api_preset_id="",
            operation=definition.default_operation,
        )
        for processing_type, definition in PROCESSOR_DEFINITIONS.items()
    }


def _processor_settings_document(settings: Mapping[str, ProcessorSetting]) -> dict[str, Any]:
    return {
        "schema": PROCESSOR_SETTINGS_SCHEMA,
        "processors": {
            processing_type: settings[processing_type].to_dict()
            for processing_type in PROCESSOR_DEFINITIONS
        },
    }


def _validate_processor_setting(
    processing_type: str,
    definition: ProcessorDefinition,
    setting: ProcessorSetting,
    *,
    api_presets: Sequence[ApiPreset],
) -> None:
    if setting.driver_id not in definition.supported_driver_ids:
        supported = ", ".join(definition.supported_driver_ids)
        raise ValueError(f"unsupported driver for {processing_type}: {setting.driver_id!r}. Expected one of: {supported}")
    driver = PROCESSOR_DRIVER_DEFINITIONS[setting.driver_id]
    if setting.enabled and driver.required_api_preset_type:
        preset = api_preset_by_id(api_presets, setting.api_preset_id)
        if preset is None:
            raise ValueError(f"API preset not found for {processing_type}: {setting.api_preset_id or '<empty>'}")
        if preset.type != driver.required_api_preset_type:
            raise ValueError(
                f"API preset {preset.id!r} has type {preset.type!r}; "
                f"{processing_type} requires {driver.required_api_preset_type!r}"
            )
    for field_name, value in setting.operation.to_dict().items():
        if not value.strip():
            raise ValueError(f"{processing_type}.operation.{field_name} must be non-empty")


def _processor_setting_configured(
    setting: ProcessorSetting,
    *,
    api_presets: Sequence[ApiPreset],
) -> bool:
    driver = PROCESSOR_DRIVER_DEFINITIONS[setting.driver_id]
    if not driver.required_api_preset_type:
        return True
    preset = api_preset_by_id(api_presets, setting.api_preset_id)
    return preset is not None and preset.type == driver.required_api_preset_type


def _operation_from_payload(
    raw: Any,
    *,
    fallback: ProcessorOperation,
    field_prefix: str,
) -> ProcessorOperation:
    if raw is None:
        return fallback
    if not isinstance(raw, Mapping):
        raise ValueError(f"{field_prefix} must be an object")
    return ProcessorOperation(
        meaning=_operation_field(raw, "meaning", fallback.meaning, field_prefix),
        choose_when=_operation_field(raw, "choose_when", fallback.choose_when, field_prefix),
        avoid_when=_operation_field(raw, "avoid_when", fallback.avoid_when, field_prefix),
    )


def _operation_field(raw: Mapping[str, Any], field_name: str, fallback: str, field_prefix: str) -> str:
    value = raw.get(field_name, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_prefix}.{field_name} must be a non-empty string")
    return value.strip()


def _bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean")


__all__ = [
    "PROCESSOR_DEFINITIONS",
    "PROCESSOR_DRIVER_DEFINITIONS",
    "PROCESSOR_SETTINGS_SCHEMA",
    "ProcessorOperation",
    "ProcessorSetting",
    "processor_definitions_payload",
    "processor_settings_path",
    "processor_settings_validation",
    "read_workbench_processor_settings",
    "require_processor_configured",
    "require_processor_configured_from_settings",
    "resolved_processor_operation_config",
    "resolved_processor_operation_config_from_settings",
    "workbench_processor_settings_payload",
    "write_workbench_processor_settings",
]
