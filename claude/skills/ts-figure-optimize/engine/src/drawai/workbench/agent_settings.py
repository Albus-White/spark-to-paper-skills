from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from drawai.acp_agent_presets import ACP_AGENT_PRESETS
from drawai.codex_cli import resolve_codex_executable
from drawai.tool_agent_runtime import DRAWAI_TOOL_AGENT_PROVIDER
from drawai.workflow.agents import SUPPORTED_REASONING_EFFORTS


SETTINGS_SCHEMA = "drawai.workbench.agent_settings.v1"
DEFAULT_AGENT_PROVIDER_ID = "codex_sdk"
DEFAULT_LLM_PROVIDER_ID = "openai_compatible"
DEFAULT_LLM_WIRE_API = "chat_completions"
SUPPORTED_LLM_WIRE_APIS = ("chat_completions", "responses")
VERSION_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class WorkbenchAgentDefinition:
    provider_id: str
    label: str
    kind: str
    workflow_provider_id: str
    pipeline_agent: str
    default_command: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class WorkbenchAgentSettings:
    selected_provider_id: str = DEFAULT_AGENT_PROVIDER_ID
    model: str = ""
    reasoning_effort: str = ""
    fast: bool = False
    timeout_seconds: int = 0
    llm_api_preset_id: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_api_key_env: str = "OPENAI_API_KEY"
    llm_wire_api: str = DEFAULT_LLM_WIRE_API
    llm_extra_body: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema"] = SETTINGS_SCHEMA
        return payload


AGENT_DEFINITIONS: dict[str, WorkbenchAgentDefinition] = {
    "codex_sdk": WorkbenchAgentDefinition(
        provider_id="codex_sdk",
        label="Codex SDK",
        kind="sdk",
        workflow_provider_id="codex_sdk",
        pipeline_agent="",
        description="OpenAI Codex Python SDK provider.",
    ),
    "codex_cli": WorkbenchAgentDefinition(
        provider_id="codex_cli",
        label="Codex CLI",
        kind="cli",
        workflow_provider_id="codex_cli",
        pipeline_agent="codex",
        default_command=("codex", "exec"),
        description="Codex CLI provider for all file-backed Agent stages.",
    ),
    "kimi_cli": WorkbenchAgentDefinition(
        provider_id="kimi_cli",
        label="Kimi CLI",
        kind="cli",
        workflow_provider_id="kimi_cli",
        pipeline_agent="kimi",
        default_command=("kimi",),
        description="Kimi CLI provider for all file-backed Agent stages.",
    ),
    **{
        preset.provider_id: WorkbenchAgentDefinition(
            provider_id=preset.provider_id,
            label=preset.label,
            kind="acp",
            workflow_provider_id=preset.provider_id,
            pipeline_agent=preset.agent_id,
            default_command=preset.default_command,
            description=preset.description,
        )
        for preset in ACP_AGENT_PRESETS.values()
    },
    "claude_cli": WorkbenchAgentDefinition(
        provider_id="claude_cli",
        label="Claude CLI",
        kind="cli",
        workflow_provider_id="claude_cli",
        pipeline_agent="claude",
        default_command=("claude",),
        description="Claude CLI provider for local Agent stages.",
    ),
    "openclaw_cli": WorkbenchAgentDefinition(
        provider_id="openclaw_cli",
        label="OpenClaw CLI",
        kind="cli",
        workflow_provider_id="openclaw_cli",
        pipeline_agent="openclaw",
        default_command=("openclaw", "agent"),
        description="OpenClaw local Agent CLI provider.",
    ),
    "hermes_cli": WorkbenchAgentDefinition(
        provider_id="hermes_cli",
        label="Hermes CLI",
        kind="cli",
        workflow_provider_id="hermes_cli",
        pipeline_agent="hermes",
        default_command=("hermes", "chat"),
        description="Hermes local Agent CLI provider.",
    ),
    DRAWAI_TOOL_AGENT_PROVIDER: WorkbenchAgentDefinition(
        provider_id=DRAWAI_TOOL_AGENT_PROVIDER,
        label="内置 Agent",
        kind="api",
        workflow_provider_id=DRAWAI_TOOL_AGENT_PROVIDER,
        pipeline_agent="",
        description="OpenAI-compatible API provider with DrawAI-owned file and tool loop.",
    ),
}

WORKBENCH_SELECTABLE_AGENT_PROVIDER_IDS: tuple[str, ...] = tuple(AGENT_DEFINITIONS)


def agent_settings_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve(strict=False) / "settings" / "agent.json"


def read_workbench_agent_settings(workspace: str | Path) -> WorkbenchAgentSettings:
    path = agent_settings_path(workspace)
    if not path.is_file():
        return WorkbenchAgentSettings()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Workbench agent settings must be a JSON object: {path}")
    return normalize_workbench_agent_settings(payload, fallback_hidden_provider=True)


def write_workbench_agent_settings(
    workspace: str | Path,
    payload: Mapping[str, Any],
) -> WorkbenchAgentSettings:
    settings = normalize_workbench_agent_settings(payload, require_selected_api_preset=True)
    path = agent_settings_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return settings


def normalize_workbench_agent_settings(
    payload: Mapping[str, Any] | None,
    *,
    fallback_hidden_provider: bool = False,
    require_selected_api_preset: bool = False,
) -> WorkbenchAgentSettings:
    data = dict(payload or {})
    raw_llm_api_key_env = data.get("llm_api_key_env")
    provider_id = str(data.get("selected_provider_id") or data.get("provider_id") or DEFAULT_AGENT_PROVIDER_ID).strip()
    if provider_id not in AGENT_DEFINITIONS:
        supported = ", ".join(WORKBENCH_SELECTABLE_AGENT_PROVIDER_IDS)
        raise ValueError(f"unsupported Workbench agent provider: {provider_id!r}. Expected one of: {supported}")
    if provider_id not in WORKBENCH_SELECTABLE_AGENT_PROVIDER_IDS:
        if fallback_hidden_provider:
            provider_id = DEFAULT_AGENT_PROVIDER_ID
        else:
            supported = ", ".join(WORKBENCH_SELECTABLE_AGENT_PROVIDER_IDS)
            raise ValueError(f"Workbench agent provider is not selectable yet: {provider_id!r}. Expected one of: {supported}")
    reasoning_effort = str(data.get("reasoning_effort") or "").strip().lower()
    if reasoning_effort and reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
        supported = ", ".join(SUPPORTED_REASONING_EFFORTS)
        raise ValueError(f"unsupported reasoning_effort: {reasoning_effort!r}. Expected one of: {supported}")
    llm_wire_api = str(data.get("llm_wire_api") or DEFAULT_LLM_WIRE_API).strip().lower().replace("-", "_")
    if llm_wire_api in {"chat", "chat_completion"}:
        llm_wire_api = "chat_completions"
    if llm_wire_api not in SUPPORTED_LLM_WIRE_APIS:
        supported = ", ".join(SUPPORTED_LLM_WIRE_APIS)
        raise ValueError(f"unsupported llm_wire_api: {llm_wire_api!r}. Expected one of: {supported}")
    llm_extra_body = data.get("llm_extra_body") or {}
    if not isinstance(llm_extra_body, Mapping):
        raise ValueError("llm_extra_body must be a JSON object")
    timeout_seconds = _settings_timeout_seconds(data.get("timeout_seconds"))
    llm_model = str(data.get("llm_model") or "").strip()
    llm_base_url = str(data.get("llm_base_url") or "").strip().rstrip("/")
    if require_selected_api_preset and provider_id == DRAWAI_TOOL_AGENT_PROVIDER and (not llm_model or not llm_base_url):
        raise ValueError("内置 Agent 需要选择 API 预设")
    return WorkbenchAgentSettings(
        selected_provider_id=provider_id,
        model=str(data.get("model") or "").strip(),
        reasoning_effort=reasoning_effort,
        fast=_settings_fast(data.get("fast")),
        timeout_seconds=timeout_seconds,
        llm_api_preset_id=str(data.get("llm_api_preset_id") or "").strip(),
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_api_key=str(data.get("llm_api_key") or "").strip(),
        llm_api_key_env=("OPENAI_API_KEY" if raw_llm_api_key_env is None else str(raw_llm_api_key_env)).strip(),
        llm_wire_api=llm_wire_api,
        llm_extra_body=dict(llm_extra_body),
    )


def discover_workbench_agent(provider_id: str) -> dict[str, Any]:
    if provider_id not in AGENT_DEFINITIONS:
        supported = ", ".join(WORKBENCH_SELECTABLE_AGENT_PROVIDER_IDS)
        raise ValueError(f"unsupported Workbench agent provider: {provider_id!r}. Expected one of: {supported}")
    return _discover_agent(AGENT_DEFINITIONS[provider_id])


def discover_workbench_agents() -> list[dict[str, Any]]:
    return [discover_workbench_agent(provider_id) for provider_id in WORKBENCH_SELECTABLE_AGENT_PROVIDER_IDS]


def workbench_agent_settings_payload(
    workspace: str | Path,
    *,
    include_agents: bool = True,
    agents: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not include_agents:
        agent_payload: list[dict[str, Any]] = []
    elif agents is not None:
        agent_payload = [dict(agent) for agent in agents]
    else:
        agent_payload = discover_workbench_agents()
    return {
        "settings": read_workbench_agent_settings(workspace).to_dict(),
        "agents": agent_payload,
    }


def apply_workbench_agent_settings_to_node_config(
    node_config: Mapping[str, Any],
    settings: WorkbenchAgentSettings,
) -> dict[str, Any]:
    definition = AGENT_DEFINITIONS[settings.selected_provider_id]
    config = dict(node_config)
    config["provider_id"] = definition.workflow_provider_id
    if definition.provider_id == DRAWAI_TOOL_AGENT_PROVIDER:
        if settings.llm_api_preset_id:
            config["api_preset_id"] = settings.llm_api_preset_id
        if settings.llm_model or settings.model:
            config["model"] = settings.llm_model or settings.model
        if settings.llm_base_url:
            config["base_url"] = settings.llm_base_url
        if settings.llm_api_key:
            config["api_key"] = settings.llm_api_key
        if settings.llm_api_key_env:
            config["api_key_env"] = settings.llm_api_key_env
        config["wire_api"] = "chat_completions"
        if settings.llm_extra_body:
            config["extra_body"] = dict(settings.llm_extra_body)
        if settings.timeout_seconds:
            config["timeout_seconds"] = settings.timeout_seconds
        return config
    if settings.model:
        config["model"] = settings.model
    if settings.reasoning_effort:
        config["reasoning_effort"] = settings.reasoning_effort
    if settings.fast:
        config["fast"] = True
    if settings.timeout_seconds:
        config["timeout_seconds"] = settings.timeout_seconds
    return config


def apply_workbench_llm_settings_to_node_config(
    node_config: Mapping[str, Any],
    settings: WorkbenchAgentSettings,
) -> dict[str, Any]:
    config = dict(node_config)
    config["provider_id"] = DEFAULT_LLM_PROVIDER_ID
    if settings.llm_api_preset_id:
        config["api_preset_id"] = settings.llm_api_preset_id
    if settings.llm_model:
        config["model"] = settings.llm_model
    if settings.reasoning_effort:
        config["reasoning_effort"] = settings.reasoning_effort
    if settings.timeout_seconds:
        config["timeout_seconds"] = settings.timeout_seconds
    if settings.llm_base_url:
        config["base_url"] = settings.llm_base_url
    if settings.llm_api_key:
        config["api_key"] = settings.llm_api_key
    if settings.llm_api_key_env:
        config["api_key_env"] = settings.llm_api_key_env
    config["wire_api"] = settings.llm_wire_api
    if settings.llm_extra_body:
        config["extra_body"] = dict(settings.llm_extra_body)
    return config


def workbench_agent_runtime_options(settings: WorkbenchAgentSettings) -> dict[str, Any]:
    definition = AGENT_DEFINITIONS[settings.selected_provider_id]
    command = resolved_agent_command(settings.selected_provider_id)
    options: dict[str, Any] = {"fast": True} if settings.fast else {}
    if definition.kind == "acp":
        if command:
            options["acp_agent_command"] = command
        return options
    if command:
        options["agent_cli_command"] = command
    return options


def apply_workbench_agent_settings_to_config_payload(
    payload: dict[str, Any],
    settings: WorkbenchAgentSettings,
    *,
    execution_mode: str = "default",
) -> None:
    mode = execution_mode.strip().lower()
    if mode == "llm":
        _apply_workbench_llm_settings_to_config_payload(payload, settings)
        return
    if mode not in {"default", "agent"}:
        raise ValueError(f"unsupported execution_mode: {execution_mode!r}. Expected one of: default, agent, llm")
    definition = AGENT_DEFINITIONS[settings.selected_provider_id]
    svg_config = _mapping_child(payload, "svg")
    runtime_config = _mapping_child(payload, "model_runtime")
    if definition.provider_id == "codex_sdk":
        svg_config["generation_backend"] = "codex_python_sdk_controlled"
        runtime_config["provider"] = "codex-python-sdk"
        runtime_config["connection_id"] = "codex-python-sdk-controlled"
        if settings.model:
            runtime_config["model_name"] = settings.model
    elif definition.provider_id == DRAWAI_TOOL_AGENT_PROVIDER:
        svg_config["generation_backend"] = "tool_agent"
        runtime_config["provider"] = DRAWAI_TOOL_AGENT_PROVIDER
        runtime_config["connection_id"] = DRAWAI_TOOL_AGENT_PROVIDER
        runtime_config["model_name"] = settings.llm_model or settings.model
        runtime_config["wire_api"] = "chat_completions"
        if settings.llm_api_preset_id:
            runtime_config["api_preset_id"] = settings.llm_api_preset_id
        if settings.llm_base_url:
            runtime_config["base_url"] = settings.llm_base_url
        if settings.llm_api_key:
            runtime_config["api_key"] = settings.llm_api_key
        if settings.llm_api_key_env:
            runtime_config["api_key_env"] = settings.llm_api_key_env
        if settings.llm_extra_body:
            runtime_config["extra_body"] = dict(settings.llm_extra_body)
    elif definition.kind == "acp":
        svg_config["generation_backend"] = "acp_agent"
        runtime_config["provider"] = "acp-agent"
        runtime_config["connection_id"] = definition.pipeline_agent
        runtime_config["model_name"] = settings.model
        acp_config = _mapping_child(runtime_config, "acp")
        acp_config["agent"] = definition.pipeline_agent
        acp_config["command"] = resolved_agent_command(definition.provider_id)
    else:
        svg_config["generation_backend"] = "agent_cli"
        runtime_config["provider"] = "agent-cli"
        runtime_config["connection_id"] = definition.pipeline_agent
        runtime_config["model_name"] = settings.model
        cli_config = _mapping_child(runtime_config, "cli")
        cli_config["agent"] = definition.pipeline_agent
        cli_config["command"] = resolved_agent_command(definition.provider_id)
    if settings.reasoning_effort:
        runtime_config["reasoning_effort"] = settings.reasoning_effort
    if settings.fast:
        runtime_config["fast"] = True
    if settings.timeout_seconds:
        runtime_config["timeout_seconds"] = settings.timeout_seconds


def _apply_workbench_llm_settings_to_config_payload(
    payload: dict[str, Any],
    settings: WorkbenchAgentSettings,
) -> None:
    svg_config = _mapping_child(payload, "svg")
    runtime_config = _mapping_child(payload, "model_runtime")
    svg_config["generation_backend"] = "responses"
    runtime_config["provider"] = DEFAULT_LLM_PROVIDER_ID
    runtime_config["connection_id"] = DEFAULT_LLM_PROVIDER_ID
    if settings.llm_api_preset_id:
        runtime_config["api_preset_id"] = settings.llm_api_preset_id
    if settings.llm_model:
        runtime_config["model_name"] = settings.llm_model
    if settings.reasoning_effort:
        runtime_config["reasoning_effort"] = settings.reasoning_effort
    if settings.timeout_seconds:
        runtime_config["timeout_seconds"] = settings.timeout_seconds
    if settings.llm_base_url:
        runtime_config["base_url"] = settings.llm_base_url
    if settings.llm_api_key:
        runtime_config["api_key"] = settings.llm_api_key
    if settings.llm_base_url:
        api_provider = _mapping_child(runtime_config, "api_provider")
        api_provider["mode"] = "thirdparty"
        thirdparty = _mapping_child(api_provider, "thirdparty")
        thirdparty["base_url"] = settings.llm_base_url
        thirdparty["wire_api"] = settings.llm_wire_api
        thirdparty["model_provider"] = DEFAULT_LLM_PROVIDER_ID
        if settings.llm_api_key:
            thirdparty["api_key"] = settings.llm_api_key
        if settings.llm_api_key_env:
            thirdparty["api_key_env"] = settings.llm_api_key_env


def resolved_agent_command(provider_id: str) -> list[str]:
    definition = AGENT_DEFINITIONS[provider_id]
    if definition.kind not in {"cli", "acp"}:
        return []
    if definition.provider_id == "codex_cli":
        path = resolve_codex_executable()
    else:
        executable = definition.default_command[0] if definition.default_command else definition.pipeline_agent
        found = shutil.which(executable)
        path = Path(found).expanduser().resolve(strict=False) if found else None
    if path is None:
        return list(definition.default_command)
    return [str(path), *definition.default_command[1:]]


def _discover_agent(definition: WorkbenchAgentDefinition) -> dict[str, Any]:
    if definition.kind == "sdk":
        package_available = importlib.util.find_spec("openai_codex") is not None
        auth = _codex_auth_status()
        status = "ok" if package_available and auth["available"] else "missing"
        detail = "Codex SDK package and auth are available." if status == "ok" else "Codex SDK needs package import and auth."
        return {
            "provider_id": definition.provider_id,
            "label": definition.label,
            "kind": definition.kind,
            "available": status == "ok",
            "status": status,
            "detail": detail,
            "fix": "" if status == "ok" else "Install the local runtime and run Codex login or set OPENAI_API_KEY.",
            "executable_path": "",
            "command": [],
            "version": "",
            "auth": auth,
            "workflow_provider_id": definition.workflow_provider_id,
            "pipeline_agent": definition.pipeline_agent,
            "description": definition.description,
        }
    if definition.kind == "api":
        return {
            "provider_id": definition.provider_id,
            "label": definition.label,
            "kind": definition.kind,
            "available": True,
            "status": "ok",
            "detail": "使用 workspace API 预设连接 OpenAI-compatible 模型。",
            "fix": "",
            "executable_path": "",
            "command": [],
            "version": "",
            "auth": {"available": True, "detail": "Set an API key or API key environment variable."},
            "workflow_provider_id": definition.workflow_provider_id,
            "pipeline_agent": definition.pipeline_agent,
            "description": definition.description,
        }
    command = resolved_agent_command(definition.provider_id)
    executable_path = command[0] if command else ""
    executable_exists = bool(executable_path and Path(executable_path).is_file())
    version = _agent_version(command) if executable_exists else ""
    status = "ok" if executable_exists else "missing"
    return {
        "provider_id": definition.provider_id,
        "label": definition.label,
        "kind": definition.kind,
        "available": executable_exists,
        "status": status,
        "detail": f"{definition.label} executable found." if executable_exists else f"{definition.label} executable was not found.",
        "fix": "" if executable_exists else f"Install {definition.default_command[0]} or add it to PATH.",
        "executable_path": executable_path,
        "command": command,
        "version": version,
        "auth": _codex_auth_status() if definition.provider_id == "codex_cli" else {"available": True, "detail": ""},
        "workflow_provider_id": definition.workflow_provider_id,
        "pipeline_agent": definition.pipeline_agent,
        "description": definition.description,
    }


def _agent_version(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            [command[0], "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    output = (completed.stdout or completed.stderr).strip()
    return " ".join(output.split())


def _codex_auth_status() -> dict[str, Any]:
    if os.environ.get("OPENAI_API_KEY"):
        return {"available": True, "detail": "OPENAI_API_KEY is set"}
    candidates = _codex_auth_candidate_paths()
    for path in candidates:
        if path.is_file():
            return {"available": True, "detail": f"{path} exists"}
    return {
        "available": False,
        "detail": "Checked: " + ", ".join(str(path) for path in candidates),
    }


def _codex_auth_candidate_paths() -> list[Path]:
    paths: list[Path] = []

    def append(path: Path) -> None:
        resolved = path.expanduser().resolve(strict=False)
        if resolved not in paths:
            paths.append(resolved)

    codex_home = os.environ.get("DRAWAI_HOST_CODEX_HOME") or os.environ.get("CODEX_HOME")
    if codex_home:
        append(Path(codex_home) / "auth.json")
    for home_var in ("DRAWAI_HOST_HOME", "HOME", "USERPROFILE"):
        value = os.environ.get(home_var)
        if value:
            append(Path(value) / ".codex" / "auth.json")
    append(Path.home() / ".codex" / "auth.json")
    return paths


def _settings_timeout_seconds(raw: Any) -> int:
    if raw in (None, ""):
        return 0
    value = int(raw)
    if value < 0:
        raise ValueError("timeout_seconds must be positive")
    return value


def _settings_fast(raw: Any) -> bool:
    if raw in (None, ""):
        return False
    if isinstance(raw, bool):
        return raw
    raise ValueError("fast must be a boolean")


def _mapping_child(parent: dict[str, Any], key: str) -> dict[str, Any]:
    child = parent.get(key)
    if not isinstance(child, dict):
        child = {}
        parent[key] = child
    return child
