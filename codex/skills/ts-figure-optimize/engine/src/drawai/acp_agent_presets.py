from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcpAgentPreset:
    agent_id: str
    provider_id: str
    label: str
    executable: str
    default_command: tuple[str, ...]
    description: str
    default_max_concurrent: int = 1
    supports_images: bool = True


ACP_AGENT_PRESETS: dict[str, AcpAgentPreset] = {
    "kimi": AcpAgentPreset(
        agent_id="kimi",
        provider_id="kimi_acp",
        label="Kimi ACP",
        executable="kimi",
        default_command=("kimi", "acp"),
        description="Kimi Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "gemini": AcpAgentPreset(
        agent_id="gemini",
        provider_id="gemini_acp",
        label="Gemini CLI ACP",
        executable="gemini",
        default_command=("gemini", "--experimental-acp"),
        description="Gemini CLI Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "qwen": AcpAgentPreset(
        agent_id="qwen",
        provider_id="qwen_acp",
        label="Qwen Code ACP",
        executable="qwen",
        default_command=("qwen", "--acp"),
        description="Qwen Code Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "opencode": AcpAgentPreset(
        agent_id="opencode",
        provider_id="opencode_acp",
        label="OpenCode ACP",
        executable="opencode",
        default_command=("opencode", "acp"),
        description="OpenCode Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "goose": AcpAgentPreset(
        agent_id="goose",
        provider_id="goose_acp",
        label="Goose ACP",
        executable="goose",
        default_command=("goose", "acp"),
        description="Goose Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "kiro": AcpAgentPreset(
        agent_id="kiro",
        provider_id="kiro_acp",
        label="Kiro CLI ACP",
        executable="kiro-cli",
        default_command=("kiro-cli", "acp"),
        description="Kiro CLI Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "qoder": AcpAgentPreset(
        agent_id="qoder",
        provider_id="qoder_acp",
        label="Qoder CLI ACP",
        executable="qodercli",
        default_command=("qodercli", "--acp"),
        description="Qoder CLI Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "cursor": AcpAgentPreset(
        agent_id="cursor",
        provider_id="cursor_acp",
        label="Cursor ACP",
        executable="agent",
        default_command=("agent", "acp"),
        description="Cursor CLI Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "cline": AcpAgentPreset(
        agent_id="cline",
        provider_id="cline_acp",
        label="Cline ACP",
        executable="cline",
        default_command=("cline", "--acp"),
        description="Cline Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "copilot": AcpAgentPreset(
        agent_id="copilot",
        provider_id="copilot_acp",
        label="GitHub Copilot ACP",
        executable="copilot",
        default_command=("copilot", "--acp", "--stdio"),
        description="GitHub Copilot CLI Agent Client Protocol provider for file-backed Agent tasks.",
    ),
    "hermes": AcpAgentPreset(
        agent_id="hermes",
        provider_id="hermes_acp",
        label="Hermes ACP",
        executable="hermes",
        default_command=("hermes", "acp"),
        description="Hermes Agent Client Protocol provider for file-backed Agent tasks.",
    ),
}

ACP_AGENT_BY_PROVIDER_ID: dict[str, AcpAgentPreset] = {
    preset.provider_id: preset for preset in ACP_AGENT_PRESETS.values()
}
ACP_AGENT_PROVIDER_IDS: tuple[str, ...] = tuple(
    preset.provider_id for preset in ACP_AGENT_PRESETS.values()
)
SUPPORTED_ACP_AGENTS = frozenset((*ACP_AGENT_PRESETS, "custom"))


def acp_agent_from_value(value: str) -> str | None:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in ACP_AGENT_PRESETS:
        return normalized
    preset = ACP_AGENT_BY_PROVIDER_ID.get(normalized)
    if preset is not None:
        return preset.agent_id
    return None


def acp_agent_default_command(agent_id: str) -> tuple[str, ...]:
    preset = ACP_AGENT_PRESETS.get(agent_id)
    return preset.default_command if preset is not None else ()


def acp_agent_label(agent_id: str) -> str:
    preset = ACP_AGENT_PRESETS.get(agent_id)
    return preset.label if preset is not None else "ACP Agent"
