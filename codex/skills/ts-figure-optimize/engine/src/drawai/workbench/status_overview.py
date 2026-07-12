from __future__ import annotations

from pathlib import Path
from collections.abc import Iterable
from typing import Any, Mapping, Sequence

from .agent_settings import WorkbenchAgentSettings, discover_workbench_agent, read_workbench_agent_settings
from .api_presets import ApiPreset, read_workbench_api_presets
from .models import WorkbenchSettings
from .processor_settings import (
    PROCESSOR_DEFINITIONS,
    ProcessorSetting,
    processor_settings_validation,
    read_workbench_processor_settings,
)


STATUS_OVERVIEW_SCHEMA = "drawai.workbench.status_overview.v1"
SEVERITY_ORDER = {"ok": 0, "warning": 1, "error": 2}
BASELINE_PROCESSORS = ("no_process", "crop", "crop_nobg")
CAPABILITY_PROCESSORS = ("image_generate", "image_edit")
RUNTIME_SERVICE_LABELS = {
    "sam3": "SAM3",
    "ocr": "OCR",
    "rmbg": "RMBG",
}
CAPABILITY_LABELS = {
    "image_generate": "图像生成",
    "image_edit": "图像编辑",
}


def workbench_status_overview_payload(
    workspace: str | Path,
    *,
    settings: WorkbenchSettings,
    runtime_services: Mapping[str, Any],
) -> dict[str, Any]:
    api_presets, api_error = _read_api_presets(workspace)
    agent_settings, agent_error = _read_agent_settings(workspace)
    processor_settings, processor_error = _read_processor_settings(workspace)
    issues: list[dict[str, Any]] = []
    groups = [
        _runtime_group(runtime_services, issues),
        _api_group(api_presets, api_error, issues),
        _agent_group(agent_settings, agent_error, issues),
        _llm_group(agent_settings, agent_error, issues),
        _processor_group(processor_settings, processor_error, api_presets, issues),
        _capability_group(processor_settings, processor_error, runtime_services, api_presets, issues),
    ]
    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    severity = "error" if error_count else "warning" if warning_count else "ok"
    return {
        "schema": STATUS_OVERVIEW_SCHEMA,
        "workspace": str(Path(workspace).expanduser().resolve(strict=False)),
        "cloud_mode": settings.cloud_mode,
        "overall": {
            "severity": severity,
            "label": _overall_label(severity),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "groups": groups,
        "issues": sorted(issues, key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["id"])),
    }


def _read_api_presets(workspace: str | Path) -> tuple[tuple[ApiPreset, ...], str]:
    try:
        return read_workbench_api_presets(workspace), ""
    except ValueError as exc:
        return (), str(exc)


def _read_agent_settings(workspace: str | Path) -> tuple[WorkbenchAgentSettings | None, str]:
    try:
        return read_workbench_agent_settings(workspace), ""
    except ValueError as exc:
        return None, str(exc)


def _read_processor_settings(workspace: str | Path) -> tuple[dict[str, ProcessorSetting] | None, str]:
    try:
        return read_workbench_processor_settings(workspace), ""
    except ValueError as exc:
        return None, str(exc)


def _runtime_group(runtime_services: Mapping[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    offline_labels: list[str] = []
    for service_id, label in RUNTIME_SERVICE_LABELS.items():
        service = runtime_services.get(service_id)
        online = isinstance(service, Mapping) and service.get("status") == "online"
        detail = _runtime_service_detail(service)
        items.append(
            _item(
                service_id,
                label,
                "ok" if online else "error",
                "在线" if online else "离线",
                detail,
            )
        )
        if not online:
            offline_labels.append(label)
            issues.append(
                _issue(
                    f"runtime.{service_id}.offline",
                    "error",
                    f"{label} 服务离线",
                    f"{label} 当前不可用，基础可编辑化流程会被阻断。",
                    "运行服务",
                    _action("查看", "overview", service_id),
                )
            )
    severity = _max_severity(item["severity"] for item in items)
    summary = "、".join(offline_labels) + " 离线" if offline_labels else "SAM3、OCR、RMBG 在线"
    return _group("runtime", "运行服务", severity, summary, items)


def _api_group(api_presets: Sequence[ApiPreset], api_error: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
    images_presets = [preset for preset in api_presets if preset.type == "images_api"]
    llm_presets = [preset for preset in api_presets if preset.type in {"llm_chat_completions", "llm_responses"}]
    items = [
        _item("api.total", "API 预设", "ok" if api_presets else "warning", str(len(api_presets)), "workspace settings"),
        _item("api.images", "Images API", "ok" if images_presets else "warning", str(len(images_presets)), "图像生成/编辑模型"),
        _item("api.llm", "LLM API", "ok" if llm_presets else "warning", str(len(llm_presets)), "默认 LLM 候选"),
    ]
    if api_error:
        issues.append(
            _issue(
                "settings.api.invalid",
                "error",
                "API 预设文件无效",
                api_error,
                "API 预设",
                _action("去配置", "api", ""),
            )
        )
        return _group("api", "API 预设", "error", "API 预设文件无效", items)
    if not api_presets:
        issues.append(
            _issue(
                "api.presets.missing",
                "warning",
                "未配置 API 预设",
                "当前 workspace 还没有可复用的模型 API 预设。",
                "API 预设",
                _action("去配置", "api", ""),
            )
        )
    if not images_presets:
        issues.append(
            _issue(
                "api.images_api.missing",
                "warning",
                "未配置图像 API 预设",
                "没有 images_api 预设时，图像生成/编辑 processor 无法选择 API 驱动。",
                "API 预设",
                _action("去配置", "api", "", mode="create_images_api"),
            )
        )
    if not llm_presets:
        issues.append(
            _issue(
                "api.llm_api.missing",
                "warning",
                "未配置 LLM API 预设",
                "默认 LLM 配置没有可选择的 LLM API 预设。",
                "API 预设",
                _action("去配置", "api", "", mode="create_llm_api"),
            )
        )
    severity = _max_severity(item["severity"] for item in items)
    summary = f"{len(api_presets)} 个 API 预设"
    return _group("api", "API 预设", severity, summary, items)


def _agent_group(
    agent_settings: WorkbenchAgentSettings | None,
    agent_error: str,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    if agent_error or agent_settings is None:
        issues.append(
            _issue(
                "settings.agent.invalid",
                "error",
                "Agent 设置文件无效",
                agent_error or "Agent 设置不可读取。",
                "Agent",
                _action("去配置", "agent", ""),
            )
        )
        return _group("agent", "Agent", "error", "Agent 设置无效", [_item("agent.selected", "当前 Agent", "error", "不可读取", agent_error)])
    try:
        discovery = discover_workbench_agent(agent_settings.selected_provider_id)
    except ValueError as exc:
        issues.append(
            _issue(
                "settings.agent.provider.invalid",
                "error",
                "当前 Agent 不可用",
                str(exc),
                "Agent",
                _action("去配置", "agent", agent_settings.selected_provider_id),
            )
        )
        return _group(
            "agent",
            "Agent",
            "error",
            "当前 Agent 不可用",
            [_item("agent.selected", "当前 Agent", "error", agent_settings.selected_provider_id, str(exc))],
        )
    available = bool(discovery.get("available"))
    auth = discovery.get("auth") if isinstance(discovery.get("auth"), Mapping) else {}
    auth_available = bool(auth.get("available", True))
    severity = "ok" if available and auth_available else "error"
    if not available:
        issues.append(
            _issue(
                "agent.selected.unavailable",
                "error",
                f"{discovery.get('label') or agent_settings.selected_provider_id} 不可用",
                str(discovery.get("fix") or discovery.get("detail") or "当前 Agent 未通过可用性检查。"),
                "Agent",
                _action("去配置", "agent", agent_settings.selected_provider_id),
            )
        )
    if available and not auth_available:
        issues.append(
            _issue(
                "agent.selected.auth_missing",
                "error",
                f"{discovery.get('label') or agent_settings.selected_provider_id} 缺少认证",
                str(auth.get("detail") or "当前 Agent 缺少认证。"),
                "Agent",
                _action("去配置", "agent", agent_settings.selected_provider_id),
            )
        )
    label = str(discovery.get("label") or agent_settings.selected_provider_id)
    detail = str(discovery.get("detail") or "")
    return _group(
        "agent",
        "Agent",
        severity,
        f"{label} {'可用' if severity == 'ok' else '未通过'}",
        [_item("agent.selected", "当前 Agent", severity, label, detail)],
    )


def _llm_group(
    agent_settings: WorkbenchAgentSettings | None,
    agent_error: str,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    if agent_error or agent_settings is None:
        return _group("llm", "LLM", "error", "LLM 设置不可读取", [_item("llm.default", "默认 LLM", "error", "不可读取", agent_error)])
    has_model = bool(agent_settings.llm_model.strip())
    has_base_url = bool(agent_settings.llm_base_url.strip())
    has_key = bool(agent_settings.llm_api_key.strip() or agent_settings.llm_api_key_env.strip())
    if has_model and has_base_url and has_key:
        return _group(
            "llm",
            "LLM",
            "ok",
            f"{agent_settings.llm_model} 已配置",
            [_item("llm.default", "默认 LLM", "ok", agent_settings.llm_model, agent_settings.llm_base_url)],
        )
    if not has_model and not has_base_url:
        issues.append(
            _issue(
                "llm.default.missing",
                "warning",
                "未选择默认 LLM",
                "需要默认 LLM 的节点会回到各自默认配置，建议在设置里选择一个 LLM API 预设。",
                "LLM",
                _action("选择", "llm", ""),
            )
        )
        return _group("llm", "LLM", "warning", "默认 LLM 未选择", [_item("llm.default", "默认 LLM", "warning", "未选择", "无完整 LLM 连接")])
    missing = []
    if not has_model:
        missing.append("model")
    if not has_base_url:
        missing.append("base_url")
    if not has_key:
        missing.append("api_key/api_key_env")
    issues.append(
        _issue(
            "llm.default.incomplete",
            "error",
            "默认 LLM 配置不完整",
            "缺少字段：" + "、".join(missing),
            "LLM",
            _action("去配置", "llm", ""),
        )
    )
    return _group("llm", "LLM", "error", "默认 LLM 配置不完整", [_item("llm.default", "默认 LLM", "error", "不完整", "缺少 " + "、".join(missing))])


def _processor_group(
    processor_settings: Mapping[str, ProcessorSetting] | None,
    processor_error: str,
    api_presets: Sequence[ApiPreset],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    if processor_error or processor_settings is None:
        target_id = _processor_target_from_error(processor_error)
        issues.append(
            _issue(
                "settings.processor.invalid",
                "error",
                "Processor 设置文件无效",
                processor_error or "Processor 设置不可读取。",
                "处理器",
                _action("去配置", "processor", target_id),
            )
        )
        return _group(
            "processor",
            "处理器",
            "error",
            "Processor 设置无效",
            [_item("processor.invalid", "设置文件", "error", "无效", processor_error)],
        )
    validation = processor_settings_validation(processor_settings, api_presets=api_presets)["processors"]
    items: list[dict[str, Any]] = []
    enabled_configured = 0
    enabled_invalid: list[str] = []
    for processing_type, definition in PROCESSOR_DEFINITIONS.items():
        setting = processor_settings[processing_type]
        status = validation[processing_type]
        if setting.enabled and status["valid"] and status["configured"]:
            enabled_configured += 1
            severity = "ok"
            value = "可用"
            detail = setting.driver_id
        elif setting.enabled:
            severity = "error"
            value = "未配置"
            detail = status["message"] or "Processor 已启用但未配置完整。"
            enabled_invalid.append(processing_type)
            issues.append(
                _issue(
                    f"processor.{processing_type}.invalid",
                    "error",
                    f"{definition.label} 未配置完整",
                    detail,
                    "处理器",
                    _action("去配置", "processor", processing_type),
                )
            )
        else:
            severity = "warning" if processing_type in CAPABILITY_PROCESSORS else "ok"
            value = "关闭"
            detail = setting.driver_id
        items.append(_item(f"processor.{processing_type}", definition.label, severity, value, detail))
    if enabled_configured == 0:
        issues.append(
            _issue(
                "processor.none_configured",
                "error",
                "没有可用 Processor",
                "至少需要一个启用且配置完整的 processor。",
                "处理器",
                _action("去配置", "processor", ""),
            )
        )
    severity = "error" if enabled_invalid or enabled_configured == 0 else _max_severity(item["severity"] for item in items)
    summary = f"{enabled_configured} 个处理器可用"
    return _group("processor", "处理器", severity, summary, items)


def _capability_group(
    processor_settings: Mapping[str, ProcessorSetting] | None,
    processor_error: str,
    runtime_services: Mapping[str, Any],
    api_presets: Sequence[ApiPreset],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime_ok = all(
        isinstance(runtime_services.get(service_id), Mapping) and runtime_services[service_id].get("status") == "online"
        for service_id in RUNTIME_SERVICE_LABELS
    )
    items: list[dict[str, Any]] = []
    if processor_error or processor_settings is None:
        items.append(_item("capability.baseline", "基础可编辑化", "error", "不可判断", processor_error))
        for processing_type in CAPABILITY_PROCESSORS:
            items.append(_item(f"capability.{processing_type}", CAPABILITY_LABELS[processing_type], "error", "不可判断", processor_error))
        return _group("capability", "关键能力", "error", "Processor 设置无效", items)
    validation = processor_settings_validation(processor_settings, api_presets=api_presets)["processors"]
    baseline_ready = runtime_ok and all(
        processor_settings[processing_type].enabled
        and validation[processing_type]["valid"]
        and validation[processing_type]["configured"]
        for processing_type in BASELINE_PROCESSORS
    )
    items.append(
        _item(
            "capability.baseline",
            "基础可编辑化",
            "ok" if baseline_ready else "error",
            "可用" if baseline_ready else "未就绪",
            "SAM3/OCR/RMBG + no_process/crop/crop_nobg",
        )
    )
    for processing_type in CAPABILITY_PROCESSORS:
        setting = processor_settings[processing_type]
        status = validation[processing_type]
        label = CAPABILITY_LABELS[processing_type]
        if setting.enabled and status["valid"] and status["configured"]:
            items.append(_item(f"capability.{processing_type}", label, "ok", "可用", setting.driver_id))
            continue
        if setting.enabled:
            detail = status["message"] or f"{processing_type} 已启用但配置不完整。"
            issues.append(
                _issue(
                    f"capability.{processing_type}.invalid",
                    "error",
                    f"{label}未配置完整",
                    detail,
                    label,
                    _action("去配置", "processor", processing_type),
                )
            )
            items.append(_item(f"capability.{processing_type}", label, "error", "未配置", detail))
            continue
        issues.append(
            _issue(
                f"capability.{processing_type}.disabled",
                "warning",
                f"{label}未启用",
                f"{processing_type} processor 目前关闭，涉及{label}的元素不会走这项能力。",
                label,
                _action("去配置", "processor", processing_type),
            )
        )
        items.append(_item(f"capability.{processing_type}", label, "warning", "关闭", setting.driver_id))
    severity = _max_severity(item["severity"] for item in items)
    summary = "关键能力已就绪" if severity == "ok" else "部分能力需要配置"
    return _group("capability", "关键能力", severity, summary, items)


def _processor_target_from_error(message: str) -> str:
    for processing_type in PROCESSOR_DEFINITIONS:
        if processing_type in message:
            return processing_type
    return ""


def _runtime_service_detail(service: Any) -> str:
    if not isinstance(service, Mapping):
        return "服务状态缺失"
    if service.get("status") == "online":
        return str(service.get("base_url") or "")
    return str(service.get("error") or service.get("base_url") or "服务不可用")


def _group(group_id: str, label: str, severity: str, summary: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": group_id,
        "label": label,
        "severity": severity,
        "summary": summary,
        "items": items,
    }


def _item(item_id: str, label: str, severity: str, value: str, detail: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "label": label,
        "severity": severity,
        "value": value,
        "detail": detail,
    }


def _issue(
    issue_id: str,
    severity: str,
    title: str,
    message: str,
    scope: str,
    action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": issue_id,
        "severity": severity,
        "title": title,
        "message": message,
        "scope": scope,
    }
    if action is not None:
        payload["action"] = action
    return payload


def _action(label: str, category: str, target_id: str, *, mode: str = "") -> dict[str, str]:
    payload = {
        "label": label,
        "category": category,
        "target_id": target_id,
    }
    if mode:
        payload["mode"] = mode
    return payload


def _max_severity(values: Iterable[str]) -> str:
    severity = "ok"
    for value in values:
        if SEVERITY_ORDER[value] > SEVERITY_ORDER[severity]:
            severity = value
    return severity


def _overall_label(severity: str) -> str:
    if severity == "error":
        return "需要处理"
    if severity == "warning":
        return "部分能力未启用"
    return "已就绪"


__all__ = [
    "STATUS_OVERVIEW_SCHEMA",
    "workbench_status_overview_payload",
]
