from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .agent_settings import WorkbenchAgentSettings, normalize_workbench_agent_settings, read_workbench_agent_settings
from .api_presets import (
    API_PRESETS_SCHEMA,
    ApiPreset,
    normalize_workbench_api_presets,
    read_workbench_api_presets,
)
from .processor_settings import (
    PROCESSOR_DEFINITIONS,
    PROCESSOR_SETTINGS_SCHEMA,
    ProcessorSetting,
    normalize_workbench_processor_settings,
    read_workbench_processor_settings,
)


CASE_SETTINGS_SNAPSHOT_SCHEMA = "drawai.workbench.case_settings_snapshot.v1"


@dataclass(frozen=True)
class CaseSettingsSnapshot:
    agent_settings: WorkbenchAgentSettings
    api_presets: tuple[ApiPreset, ...]
    processor_settings: dict[str, ProcessorSetting]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CASE_SETTINGS_SNAPSHOT_SCHEMA,
            "agent_settings": self.agent_settings.to_dict(),
            "api_presets": {
                "schema": API_PRESETS_SCHEMA,
                "presets": [preset.to_dict() for preset in self.api_presets],
            },
            "processor_settings": {
                "schema": PROCESSOR_SETTINGS_SCHEMA,
                "processors": {
                    processing_type: self.processor_settings[processing_type].to_dict()
                    for processing_type in PROCESSOR_DEFINITIONS
                },
            },
        }


def case_settings_snapshot_path(run_root: str | Path) -> Path:
    return Path(run_root).expanduser().resolve(strict=False) / "reports" / "workbench" / "settings_snapshot.json"


def case_settings_snapshot_from_workspace(
    workspace: str | Path,
    *,
    agent_settings: WorkbenchAgentSettings | None = None,
    api_presets: Sequence[ApiPreset] | None = None,
    processor_settings: Mapping[str, ProcessorSetting] | None = None,
) -> CaseSettingsSnapshot:
    resolved_api_presets = tuple(api_presets) if api_presets is not None else read_workbench_api_presets(workspace)
    resolved_processor_settings = (
        dict(processor_settings)
        if processor_settings is not None
        else read_workbench_processor_settings(workspace)
    )
    return CaseSettingsSnapshot(
        agent_settings=agent_settings or read_workbench_agent_settings(workspace),
        api_presets=resolved_api_presets,
        processor_settings=resolved_processor_settings,
    )


def write_case_settings_snapshot(run_root: str | Path, snapshot: CaseSettingsSnapshot) -> Path:
    path = case_settings_snapshot_path(run_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_case_settings_snapshot(run_root: str | Path) -> CaseSettingsSnapshot:
    path = case_settings_snapshot_path(run_root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"case settings snapshot must be a JSON object: {path}")
    raw_agent_settings = payload.get("agent_settings")
    if not isinstance(raw_agent_settings, Mapping):
        raise ValueError(f"case settings snapshot is missing agent_settings: {path}")
    raw_api_presets = payload.get("api_presets")
    if not isinstance(raw_api_presets, Mapping):
        raise ValueError(f"case settings snapshot is missing api_presets: {path}")
    raw_processor_settings = payload.get("processor_settings")
    if not isinstance(raw_processor_settings, Mapping):
        raise ValueError(f"case settings snapshot is missing processor_settings: {path}")
    api_presets = normalize_workbench_api_presets(raw_api_presets)
    return CaseSettingsSnapshot(
        agent_settings=normalize_workbench_agent_settings(raw_agent_settings, fallback_hidden_provider=True),
        api_presets=api_presets,
        processor_settings=normalize_workbench_processor_settings(raw_processor_settings, api_presets=api_presets),
    )


def read_case_settings_snapshot_or_workspace(
    run_root: str | Path,
    workspace: str | Path,
) -> CaseSettingsSnapshot:
    if case_settings_snapshot_path(run_root).is_file():
        return read_case_settings_snapshot(run_root)
    return case_settings_snapshot_from_workspace(workspace)


__all__ = [
    "CASE_SETTINGS_SNAPSHOT_SCHEMA",
    "CaseSettingsSnapshot",
    "case_settings_snapshot_from_workspace",
    "case_settings_snapshot_path",
    "read_case_settings_snapshot",
    "read_case_settings_snapshot_or_workspace",
    "write_case_settings_snapshot",
]
