from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from drawai import model_runtime

from .agents import (
    TYPE_CONTRACTS,
    AgentPreset,
    _agent_constraints,
    _agent_options,
    _agent_task,
    _configured_outputs,
    _drawai_tools_for_inputs,
    _input_absolute_path,
    _ordered_unique,
    _output_absolute_path,
    _output_path_from_run_root,
    _runtime_context,
    _selected_inputs,
    _validate_agent_config,
)
from .formats import default_format_contract_descriptions


LLM_OUTPUT_JSON_FORMATS = {
    "drawai.element_candidates.v1",
    "drawai.element_plans.v1",
    "drawai.page_spec.v1",
    "drawai.codex_element_analysis.v1",
    "drawai.asset_package.v1",
    "drawai.asset_packages.v1",
    "drawai.final_outputs.v1",
}

LLM_OUTPUT_SVG_FORMATS = {"drawai.semantic_svg.v1"}

LLM_OUTPUT_TEXT_TYPES = {"page_spec", "element_plans", "element_analysis", "asset_packages", "final_outputs"}
DEFAULT_LLM_DIRECT_OUTPUT_TOKENS = 32768
DEFAULT_LLM_PASSTHROUGH_OUTPUT_TOKENS = 2048
LLM_PROMPT_RUNTIME_OPTION_EXCLUDES = {
    "api_key",
    "extra_body",
    "reasoning_effort",
    "timeout_seconds",
    "wire_api",
}

FENCE_RE = re.compile(r"```\s*([A-Za-z0-9_.+-]*)\s*\n(.*?)```", re.DOTALL)
SVG_TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z_][\w:.-]*)([^<>]*?)(/?)\s*>", re.DOTALL)
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NAMESPACE)
ET.register_namespace("xlink", XLINK_NAMESPACE)

ModelInvoker = Callable[..., str]


@dataclass(frozen=True)
class LLMPrompt:
    preset_id: str
    provider_id: str
    text: str
    inputs: tuple[Mapping[str, Any], ...]
    outputs: tuple[Mapping[str, Any], ...]
    options: Mapping[str, Any]
    image_paths: tuple[Path, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "provider_id": self.provider_id,
            "text": self.text,
            "inputs": [dict(item) for item in self.inputs],
            "outputs": [dict(item) for item in self.outputs],
            "options": _redact_sensitive_mapping(self.options),
            "image_paths": [str(path) for path in self.image_paths],
        }


@dataclass(frozen=True)
class LLMExecutionRequest:
    prompt: LLMPrompt
    workdir: Path
    run_root: Path
    node_id: str
    node_type: str
    runtime_config: Mapping[str, Any]


@dataclass(frozen=True)
class LLMExecutionResult:
    provider_id: str
    prompt_path: Path
    stdout_path: Path
    trace_path: Path
    execution_manifest_path: Path
    exit_code: int = 0


class LLMExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        prompt_path: Path | None = None,
        stdout_path: Path | None = None,
        trace_path: Path | None = None,
        execution_manifest_path: Path | None = None,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.prompt_path = prompt_path
        self.stdout_path = stdout_path
        self.trace_path = trace_path
        self.execution_manifest_path = execution_manifest_path
        self.exit_code = exit_code


def render_llm_prompt(
    preset: AgentPreset,
    *,
    inputs: Sequence[Mapping[str, Any]],
    node_config: Mapping[str, Any] | None = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> LLMPrompt:
    config = dict(node_config or {})
    _validate_agent_config(config)
    runtime = _runtime_context(runtime_context)
    provider_id = str(config.get("provider_id") or "openai_responses")
    selected_inputs = _selected_inputs(inputs, config)
    outputs = _configured_outputs(preset, config)
    options = _llm_options(config)
    image_paths = _image_paths(selected_inputs, runtime)
    text = _render_llm_prompt_text(
        node_id=str(config.get("node_id") or "<llm_node_id>"),
        provider_id=provider_id,
        inputs=selected_inputs,
        outputs=outputs,
        options=options,
        task=_agent_task(preset, config),
        constraints=_agent_constraints(preset, config),
        drawai_tools=_drawai_tools_for_inputs((), selected_inputs),
        runtime_context=runtime,
    )
    return LLMPrompt(
        preset_id=preset.preset_id,
        provider_id=provider_id,
        text=text,
        inputs=selected_inputs,
        outputs=outputs,
        options=options,
        image_paths=image_paths,
    )


def execute_llm_prompt(
    request: LLMExecutionRequest,
    *,
    invoke_model: ModelInvoker | None = None,
) -> LLMExecutionResult:
    request.workdir.mkdir(parents=True, exist_ok=True)
    prompt_path = request.workdir / "llm_prompt.md"
    stdout_path = request.workdir / "llm_response.txt"
    trace_path = request.workdir / "llm_trace.jsonl"
    prompt_path.write_text(request.prompt.text, encoding="utf-8")
    _validate_declared_output_paths(request, prompt_path=prompt_path)
    _write_execution_request_manifest(request, prompt_path)
    started_at = time.monotonic()
    _append_trace(
        trace_path,
        {
            "type": "llm_request",
            "provider_id": request.prompt.provider_id,
            "node_id": request.node_id,
            "prompt_path": _relative_or_absolute(prompt_path, request.run_root),
            "image_paths": [_relative_or_absolute(path, request.run_root) for path in request.prompt.image_paths],
            "declared_outputs": [dict(item) for item in request.prompt.outputs],
        },
    )
    invoker = invoke_model or model_runtime.invoke_multimodal_text
    fallback_used = False
    response_text = ""
    try:
        response_text = invoker(
            image_paths=request.prompt.image_paths,
            prompt=request.prompt.text,
            task_name=f"drawai.workflow.llm.{request.node_id}",
            runtime_config=_runtime_config_for_model(request),
            trace_path=trace_path,
            max_output_tokens=_max_output_tokens_for_request(request),
        )
        stdout_path.write_text(str(response_text), encoding="utf-8")
        if _passthrough_requested(str(response_text)) and _write_matching_input_fallback(
            request,
            prompt_path=prompt_path,
            stdout_path=stdout_path,
            trace_path=trace_path,
            reason="model_requested_matching_input_passthrough",
        ):
            fallback_used = True
        else:
            _write_declared_outputs(request, str(response_text), prompt_path=prompt_path, stdout_path=stdout_path)
    except (model_runtime.ModelRuntimeError, LLMExecutionError) as exc:
        if not _write_matching_input_fallback(
            request,
            prompt_path=prompt_path,
            stdout_path=stdout_path,
            trace_path=trace_path,
            reason="matching_input_passthrough",
            error=exc,
        ):
            raise
        fallback_used = True
    _append_trace(
        trace_path,
        {
            "type": "llm_response",
            "provider_id": request.prompt.provider_id,
            "node_id": request.node_id,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "response_chars": len(str(response_text)),
            "fallback_used": fallback_used,
            "output_paths": [
                _relative_or_absolute(_declared_output_path(request, output, prompt_path=prompt_path), request.run_root)
                for output in request.prompt.outputs
            ],
        },
    )
    manifest_path = _write_execution_manifest(request, prompt_path, stdout_path, trace_path)
    return LLMExecutionResult(
        provider_id=request.prompt.provider_id,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        trace_path=trace_path,
        execution_manifest_path=manifest_path,
        exit_code=0,
    )


def _render_llm_prompt_text(
    *,
    node_id: str,
    provider_id: str,
    inputs: tuple[Mapping[str, Any], ...],
    outputs: tuple[Mapping[str, Any], ...],
    options: Mapping[str, Any],
    task: str,
    constraints: tuple[str, ...],
    drawai_tools: tuple[str, ...],
    runtime_context: Mapping[str, str],
) -> str:
    workflow_run_root = runtime_context.get("workflow_run_root") or "<workflow_run_root>"
    node_workdir = runtime_context.get("node_workdir") or f"{workflow_run_root}/nodes/{node_id}/runs/<attempt_id>"
    lines = [
        "## LLM 运行上下文",
        f"- Provider: {provider_id}",
        f"- Workflow run root：{workflow_run_root}",
        f"- 当前 node workdir：{node_workdir}",
        f"- Node run manifest path：{node_workdir}/node_run.json",
    ]
    for key, value in options.items():
        if str(key) in LLM_PROMPT_RUNTIME_OPTION_EXCLUDES:
            continue
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## 直接输出运行模式",
            (
                "这个 node 运行在 LLM direct-output 模式：只在最终 assistant message 中返回声明输出的内容。"
            ),
            (
                "如果 task 文本提到写文件、运行命令、validation tools、terminal loops 或保存路径，"
                "把它当作输出质量要求；忽略任何要求你自己运行命令或创建文件的措辞。"
            ),
            (
                "需要 JSON 或 SVG 时，直接返回紧凑且有效的 JSON/SVG；不要加 markdown fence、说明文字或重复 schema example。"
            ),
            (
                "对于 SVG 输出，不要使用 raster image elements、local file references 或 CSS urls。改用可编辑 vector shapes 和 text。"
            ),
            "DrawAI runner 会抽取你的回复，保存到声明输出路径，并在 model call 之后校验。",
        ]
    )
    if _has_matching_input_passthrough(inputs, outputs):
        lines.append(
            '如果声明输出应当与唯一一个 type/format 相同的 connected input 完全一致，直接返回 {"drawai_passthrough_input": true}。'
        )
        lines.append(
            "对于大型结构化输入，除非你非常确定需要修改，否则优先使用这个 passthrough sentinel。"
        )
    lines.extend(
        [
            "",
            "## Task",
            task,
            "",
            "## 已连接输入内容",
            (
                "不要从磁盘读取 workflow files。每个 connected text input 都嵌入在下面；"
                "每个 connected image input 都作为 image content 附加到这个 LLM request。"
            ),
        ]
    )
    if inputs:
        for index, item in enumerate(inputs, start=1):
            lines.extend(_llm_input_section(index, item, runtime_context))
    else:
        lines.append("- 没有提供 connected inputs。")

    lines.extend(
        [
            "",
            "## 必需直接输出",
            (
                "只返回声明输出内容。不要创建文件，不要把路径当作答案，也不要加入说明。"
                "DrawAI runner 会抽取你的回复并保存到声明的 node output path。"
            ),
        ]
    )
    for output in outputs:
        output_type = str(output["type"])
        output_format = str(output["format_id"])
        output_kind = _output_kind_label(output_format, output_type)
        final_run_root_path = _output_path_from_run_root(node_id, output["path"], runtime_context)
        lines.extend(
            [
                f"- Port：{output['port_id']}",
                f"  Format：{output_format}",
                f"  Type：{output_type}",
                f"  Node-output relative path：{output['path']}",
                f"  最终 run-root path：{final_run_root_path}",
                f"  最终 absolute path：{_output_absolute_path(node_id, output['path'], runtime_context)}",
                f"  指令：以 {output_kind} content 返回 {output['port_id']} output。",
                f"  说明：{output['description']}",
            ]
        )

    lines.extend(["", "## 类型和格式契约"])
    format_contracts = default_format_contract_descriptions()
    for type_name in _ordered_unique(
        [str(item.get("type") or "") for item in inputs]
        + [str(output.get("type") or "") for output in outputs]
    ):
        lines.append(
            f"- Type `{type_name}`：{TYPE_CONTRACTS.get(type_name, '没有注册内置 type 说明。按照 node description 和 embedded input content 处理。')}"
        )
    for format_id in _ordered_unique(
        [str(item.get("format_id") or "") for item in inputs]
        + [str(output.get("format_id") or "") for output in outputs]
    ):
        lines.append(
            f"- Format `{format_id}`：{format_contracts.get(format_id, '没有注册内置 format 说明。按照 output declaration 处理。')}"
        )

    if drawai_tools:
        lines.extend(
            [
                "",
                "## DrawAI 工具契约",
                (
                    "这些 tool names 只作为 LLM node 的 format-contract context。不要调用工具；只生成声明的 direct output content。"
                ),
            ]
        )
        for tool_id in drawai_tools:
            lines.append(f"- {tool_id}")

    if constraints:
        lines.extend(["", "## 约束"])
        for constraint in constraints:
            lines.append(f"- {constraint}")

    return "\n".join(lines).strip() + "\n"


def _llm_options(config: Mapping[str, Any]) -> Mapping[str, Any]:
    options = dict(_agent_options(config))
    for key in ("wire_api", "max_output_tokens"):
        if key in config and config[key] not in (None, ""):
            options[key] = config[key]
    if isinstance(config.get("extra_body"), Mapping):
        options["extra_body"] = dict(config["extra_body"])  # type: ignore[index]
    return options


def _llm_input_section(
    index: int,
    item: Mapping[str, Any],
    runtime_context: Mapping[str, str],
) -> list[str]:
    source = _source_label(item)
    format_id = str(item.get("format_id") or "unspecified")
    type_name = str(item.get("type") or "unspecified")
    path_value = str(item.get("path") or "")
    lines = [
        f"### 输入 {index}：{source}",
        f"- Format：{format_id}",
        f"- Type：{type_name}",
        f"- Run-root path：{path_value}",
        f"- Absolute path：{_input_absolute_path(path_value, runtime_context)}",
        f"- 说明：{item.get('description') or 'No description supplied.'}",
    ]
    if _is_image_input(item):
        image_path = _resolve_input_path(path_value, runtime_context)
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        image_bytes = image_path.read_bytes() if image_path.is_file() else b""
        lines.append(
            f"Image content 已附加到这个 LLM request（{mime_type}, {len(image_bytes)} bytes）。"
        )
        return lines

    input_path = _resolve_input_path(path_value, runtime_context)
    content, fence_language = _read_input_content(input_path, format_id=format_id)
    lines.extend(["内容：", f"```{fence_language}", content.rstrip("\n"), "```"])
    return lines


def _read_input_content(path: Path, *, format_id: str) -> tuple[str, str]:
    if not path.is_file():
        raise LLMExecutionError(f"LLM input file does not exist: {path}")
    if path.suffix.lower() == ".json" or mimetypes.guess_type(path.name)[0] == "application/json":
        return path.read_text(encoding="utf-8"), "json"
    if path.suffix.lower() == ".svg":
        return path.read_text(encoding="utf-8"), "svg"
    try:
        return path.read_text(encoding="utf-8"), ""
    except UnicodeDecodeError:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}", "text"


def _write_declared_outputs(
    request: LLMExecutionRequest,
    response_text: str,
    *,
    prompt_path: Path,
    stdout_path: Path,
) -> None:
    response_payload: Mapping[str, Any] | None = None
    if len(request.prompt.outputs) > 1:
        parsed = _extract_json_payload(response_text, prompt_path=prompt_path, stdout_path=stdout_path)
        if not isinstance(parsed, Mapping):
            raise LLMExecutionError(
                "LLM response for multiple outputs must be a JSON object",
                prompt_path=prompt_path,
                stdout_path=stdout_path,
            )
        response_payload = parsed
    for output in request.prompt.outputs:
        output_path = _declared_output_path(request, output, prompt_path=prompt_path)
        source_text = _output_response_text(response_text, response_payload, output)
        _write_output_content(
            output_path,
            source_text,
            output,
            prompt_path=prompt_path,
            stdout_path=stdout_path,
        )


def _write_output_content(
    output_path: Path,
    source_text: str,
    output: Mapping[str, Any],
    *,
    prompt_path: Path,
    stdout_path: Path,
) -> None:
    format_id = str(output.get("format_id") or "")
    type_name = str(output.get("type") or "")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if format_id in LLM_OUTPUT_JSON_FORMATS or type_name in LLM_OUTPUT_TEXT_TYPES:
        payload = _extract_json_payload(source_text, prompt_path=prompt_path, stdout_path=stdout_path)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    if format_id in LLM_OUTPUT_SVG_FORMATS or type_name == "semantic_svg":
        svg = _extract_svg_text(source_text, prompt_path=prompt_path, stdout_path=stdout_path)
        svg = _sanitize_svg_raster_image_refs(
            svg,
            prompt_path=prompt_path,
            stdout_path=stdout_path,
        )
        output_path.write_text(svg.rstrip() + "\n", encoding="utf-8")
        return
    output_path.write_text(source_text.strip() + "\n", encoding="utf-8")


def _extract_json_payload(
    text: str,
    *,
    prompt_path: Path,
    stdout_path: Path,
) -> Any:
    stripped = text.strip()
    if not stripped:
        raise LLMExecutionError(
            "LLM response was empty; expected JSON output",
            prompt_path=prompt_path,
            stdout_path=stdout_path,
        )
    direct = _try_json(stripped)
    if direct is not None:
        return direct
    if stripped.startswith("```"):
        for _language, content in _fenced_blocks(stripped, preferred=("json", "javascript", "js", "")):
            parsed = _try_json(content.strip())
            if parsed is not None:
                return parsed
        raise LLMExecutionError(
            "LLM response did not contain complete parseable JSON in its fenced output",
            prompt_path=prompt_path,
            stdout_path=stdout_path,
        )
    if stripped[0] in "{[":
        raise LLMExecutionError(
            "LLM response did not contain complete parseable JSON",
            prompt_path=prompt_path,
            stdout_path=stdout_path,
        )
    for _language, content in _fenced_blocks(stripped, preferred=("json", "javascript", "js", "")):
        parsed = _try_json(content.strip())
        if parsed is not None:
            return parsed
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "{[":
            continue
        parsed = _try_json_from(decoder, stripped[index:])
        if parsed is not None:
            return parsed
    raise LLMExecutionError(
        "LLM response did not contain a parseable JSON object or array",
        prompt_path=prompt_path,
        stdout_path=stdout_path,
    )


def _write_matching_input_fallback(
    request: LLMExecutionRequest,
    *,
    prompt_path: Path,
    stdout_path: Path,
    trace_path: Path,
    reason: str,
    error: Exception | None = None,
) -> bool:
    if len(request.prompt.outputs) != 1:
        return False
    output = request.prompt.outputs[0]
    input_item = _single_matching_input(request.prompt.inputs, output)
    if input_item is None:
        return False
    source_path = _request_input_path(request, str(input_item.get("path") or ""))
    if not source_path.is_file():
        return False
    if not stdout_path.exists():
        stdout_path.write_text("", encoding="utf-8")
    output_path = _declared_output_path(request, output, prompt_path=prompt_path)
    source_text = source_path.read_text(encoding="utf-8")
    _write_output_content(
        output_path,
        source_text,
        output,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
    )
    _append_trace(
        trace_path,
        {
            "type": "llm_fallback",
            "provider_id": request.prompt.provider_id,
            "node_id": request.node_id,
            "reason": reason,
            "source_input_path": _relative_or_absolute(source_path, request.run_root),
            "output_path": _relative_or_absolute(output_path, request.run_root),
            **({"error_type": type(error).__name__, "error": str(error)} if error is not None else {}),
        },
    )
    return True


def _passthrough_requested(text: str) -> bool:
    stripped = text.strip()
    payload = _try_json(stripped)
    if payload is None and stripped.startswith("```"):
        for _language, content in _fenced_blocks(stripped, preferred=("json", "javascript", "js", "")):
            payload = _try_json(content.strip())
            if payload is not None:
                break
    return isinstance(payload, Mapping) and payload.get("drawai_passthrough_input") is True


def _has_matching_input_passthrough(
    inputs: Sequence[Mapping[str, Any]],
    outputs: Sequence[Mapping[str, Any]],
) -> bool:
    return len(outputs) == 1 and _single_matching_input(inputs, outputs[0]) is not None


def _single_matching_input(
    inputs: Sequence[Mapping[str, Any]],
    output: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    output_format = str(output.get("format_id") or "")
    output_type = str(output.get("type") or "")
    matches = [
        item
        for item in inputs
        if (output_format and str(item.get("format_id") or "") == output_format)
        or (output_type and str(item.get("type") or "") == output_type)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _request_input_path(request: LLMExecutionRequest, path_value: str) -> Path:
    if not path_value:
        raise LLMExecutionError("LLM fallback input path must be a non-empty string")
    path = Path(path_value)
    if path.is_absolute():
        return path.expanduser().resolve(strict=False)
    return (request.run_root / path).expanduser().resolve(strict=False)


def _extract_svg_text(
    text: str,
    *,
    prompt_path: Path,
    stdout_path: Path,
) -> str:
    stripped = text.strip()
    if stripped.startswith("<svg") and stripped.endswith("</svg>"):
        return stripped
    repaired = _repair_truncated_svg(stripped)
    if repaired is not None:
        return repaired
    for _language, content in _fenced_blocks(stripped, preferred=("svg", "xml", "html", "")):
        candidate = content.strip()
        if candidate.startswith("<svg") and candidate.endswith("</svg>"):
            return candidate
        repaired = _repair_truncated_svg(candidate)
        if repaired is not None:
            return repaired
    parsed = _try_json(stripped)
    if isinstance(parsed, Mapping):
        for key in ("svg", "semantic_svg", "content", "output"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip().startswith("<svg"):
                return _extract_svg_text(value, prompt_path=prompt_path, stdout_path=stdout_path)
    start = stripped.find("<svg")
    end = stripped.rfind("</svg>")
    if start >= 0 and end >= start:
        return stripped[start : end + len("</svg>")].strip()
    if start >= 0:
        repaired = _repair_truncated_svg(stripped[start:])
        if repaired is not None:
            return repaired
    raise LLMExecutionError(
        "LLM response did not contain a complete SVG document",
        prompt_path=prompt_path,
        stdout_path=stdout_path,
    )


def _repair_truncated_svg(text: str) -> str | None:
    candidate = text.strip()
    if not candidate.startswith("<svg") or candidate.endswith("</svg>"):
        return None
    last_tag_end = candidate.rfind(">")
    if last_tag_end < 0:
        return None
    candidate = candidate[: last_tag_end + 1]
    stack: list[str] = []
    for match in SVG_TAG_RE.finditer(candidate):
        raw_tag = match.group(0)
        tag_name = match.group(2)
        if raw_tag.startswith("<?") or raw_tag.startswith("<!"):
            continue
        if match.group(1):
            for index in range(len(stack) - 1, -1, -1):
                if stack[index] == tag_name:
                    del stack[index:]
                    break
            continue
        if match.group(4) or match.group(3).rstrip().endswith("/"):
            continue
        stack.append(tag_name)
    if not stack or stack[0].split(":")[-1] != "svg":
        return None
    repaired = candidate + "".join(f"</{tag_name}>" for tag_name in reversed(stack))
    try:
        root = ET.fromstring(repaired)
    except ET.ParseError:
        return None
    if _xml_local_name(root.tag) != "svg":
        return None
    return repaired


def _sanitize_svg_raster_image_refs(
    svg: str,
    *,
    prompt_path: Path,
    stdout_path: Path,
) -> str:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise LLMExecutionError(
            "LLM response SVG was not parseable XML",
            prompt_path=prompt_path,
            stdout_path=stdout_path,
        ) from exc
    if _xml_local_name(root.tag) != "svg":
        raise LLMExecutionError(
            "LLM response SVG root element was not <svg>",
            prompt_path=prompt_path,
            stdout_path=stdout_path,
        )

    parent_by_child = {child: parent for parent in root.iter() for child in list(parent)}
    changed = False
    for element in list(root.iter()):
        if _xml_local_name(element.tag) != "image":
            continue
        parent = parent_by_child.get(element)
        if parent is None:
            element.clear()
        else:
            parent.remove(element)
        changed = True
    if not changed:
        return svg
    return ET.tostring(root, encoding="unicode")


def _xml_local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _output_response_text(
    response_text: str,
    response_payload: Mapping[str, Any] | None,
    output: Mapping[str, Any],
) -> str:
    if response_payload is None:
        return response_text
    keys = (
        str(output.get("port_id") or ""),
        str(output.get("type") or ""),
        Path(str(output.get("path") or "")).name,
    )
    for key in keys:
        value = response_payload.get(key)
        if isinstance(value, str):
            return value
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
    outputs = response_payload.get("outputs")
    if isinstance(outputs, Mapping):
        for key in keys:
            value = outputs.get(key)
            if isinstance(value, str):
                return value
            if value is not None:
                return json.dumps(value, ensure_ascii=False)
    raise LLMExecutionError(f"LLM response JSON did not contain output {keys[0]!r}")


def _try_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _try_json_from(decoder: json.JSONDecoder, text: str) -> Any | None:
    try:
        payload, _end = decoder.raw_decode(text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, Mapping | list):
        return payload
    return None


def _fenced_blocks(text: str, *, preferred: Sequence[str]) -> tuple[tuple[str, str], ...]:
    preferred_set = {language.lower() for language in preferred}
    blocks: list[tuple[str, str]] = []
    fallback: list[tuple[str, str]] = []
    for match in FENCE_RE.finditer(text):
        language = match.group(1).strip().lower()
        block = (language, match.group(2))
        if language in preferred_set:
            blocks.append(block)
        else:
            fallback.append(block)
    return tuple(blocks + fallback)


def _validate_declared_output_paths(request: LLMExecutionRequest, *, prompt_path: Path) -> None:
    for output in request.prompt.outputs:
        _declared_output_path(request, output, prompt_path=prompt_path)


def _declared_output_path(
    request: LLMExecutionRequest,
    output: Mapping[str, Any],
    *,
    prompt_path: Path,
) -> Path:
    raw_path = output.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise LLMExecutionError(
            "LLM declared output path must be a non-empty string",
            prompt_path=prompt_path,
        )
    path = Path(raw_path)
    if path.is_absolute():
        raise LLMExecutionError(
            f"LLM declared output path must be relative to node workdir: {raw_path}",
            prompt_path=prompt_path,
        )
    resolved = (request.workdir / path).resolve(strict=False)
    try:
        resolved.relative_to(request.workdir.resolve(strict=False))
    except ValueError as exc:
        raise LLMExecutionError(
            f"LLM declared output path escapes node workdir: {raw_path}",
            prompt_path=prompt_path,
        ) from exc
    return resolved


def _write_execution_request_manifest(request: LLMExecutionRequest, prompt_path: Path) -> Path:
    path = request.workdir / "llm_execution_request.json"
    _write_json(
        path,
        {
            "schema": "drawai.workflow_llm_execution_request.v1",
            "node_id": request.node_id,
            "node_type": request.node_type,
            "provider_id": request.prompt.provider_id,
            "node_workdir": str(request.workdir),
            "run_root": str(request.run_root),
            "prompt_path": _relative_or_absolute(prompt_path, request.run_root),
            "declared_inputs": [dict(item) for item in request.prompt.inputs],
            "image_input_paths": [
                _relative_or_absolute(path_item, request.run_root)
                for path_item in request.prompt.image_paths
            ],
            "declared_outputs": [dict(item) for item in request.prompt.outputs],
            "options": _redact_sensitive_mapping(request.prompt.options),
        },
    )
    return path


def _write_execution_manifest(
    request: LLMExecutionRequest,
    prompt_path: Path,
    stdout_path: Path,
    trace_path: Path,
) -> Path:
    path = request.workdir / "llm_execution.json"
    _write_json(
        path,
        {
            "schema": "drawai.workflow_llm_execution.v1",
            "node_id": request.node_id,
            "provider_id": request.prompt.provider_id,
            "node_workdir": str(request.workdir),
            "prompt_path": _relative_or_absolute(prompt_path, request.run_root),
            "stdout_path": _relative_or_absolute(stdout_path, request.run_root),
            "trace_path": _relative_or_absolute(trace_path, request.run_root),
            "declared_inputs": [dict(item) for item in request.prompt.inputs],
            "image_input_paths": [
                _relative_or_absolute(path_item, request.run_root)
                for path_item in request.prompt.image_paths
            ],
            "declared_outputs": [dict(item) for item in request.prompt.outputs],
            "actual_outputs": [
                _relative_or_absolute(_declared_output_path(request, output, prompt_path=prompt_path), request.run_root)
                for output in request.prompt.outputs
            ],
            "exit_code": 0,
        },
    )
    return path


def _runtime_config_for_model(request: LLMExecutionRequest) -> dict[str, Any]:
    runtime = dict(request.runtime_config)
    runtime["provider"] = str(runtime.get("provider") or request.prompt.provider_id)
    runtime["connection_id"] = str(runtime.get("connection_id") or request.prompt.provider_id)
    runtime["direct_output"] = True
    model = request.prompt.options.get("model")
    if model:
        runtime["model_name"] = str(model)
    for key in ("timeout_seconds", "wire_api", "extra_body"):
        value = request.prompt.options.get(key)
        if value not in (None, ""):
            runtime[key] = value
    return runtime


def _redact_sensitive_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        normalized = key_text.lower().replace("-", "_")
        redacted[key_text] = "[redacted]" if "api_key" in normalized else item
    return redacted


def _max_output_tokens_for_request(request: LLMExecutionRequest) -> int:
    configured = request.prompt.options.get("max_output_tokens")
    if configured not in (None, ""):
        return int(configured)
    if _has_matching_input_passthrough(request.prompt.inputs, request.prompt.outputs):
        return DEFAULT_LLM_PASSTHROUGH_OUTPUT_TOKENS
    return DEFAULT_LLM_DIRECT_OUTPUT_TOKENS


def _image_paths(
    inputs: Sequence[Mapping[str, Any]],
    runtime_context: Mapping[str, str],
) -> tuple[Path, ...]:
    return tuple(
        _resolve_input_path(str(item.get("path") or ""), runtime_context)
        for item in inputs
        if _is_image_input(item)
    )


def _is_image_input(item: Mapping[str, Any]) -> bool:
    return str(item.get("type") or "") == "image" or str(item.get("format_id") or "") == "drawai.image.v1"


def _resolve_input_path(path_value: str, runtime_context: Mapping[str, str]) -> Path:
    if not path_value:
        raise LLMExecutionError("LLM input path must be a non-empty string")
    path = Path(path_value)
    if path.is_absolute():
        return path.expanduser().resolve(strict=False)
    workflow_run_root = runtime_context.get("workflow_run_root")
    if not workflow_run_root or workflow_run_root.startswith("<"):
        raise LLMExecutionError(f"workflow_run_root is required to embed LLM input content: {path_value}")
    return (Path(workflow_run_root) / path).expanduser().resolve(strict=False)


def _output_kind_label(format_id: str, type_name: str) -> str:
    if format_id in LLM_OUTPUT_JSON_FORMATS or type_name in LLM_OUTPUT_TEXT_TYPES:
        return "JSON"
    if format_id in LLM_OUTPUT_SVG_FORMATS or type_name == "semantic_svg":
        return "SVG"
    return "plain text"


def _source_label(item: Mapping[str, Any]) -> str:
    source_node = str(item.get("source_node_id") or "")
    source_port = str(item.get("source_port_id") or "")
    if source_node and source_port:
        return f"{source_node}.{source_port}"
    if source_node:
        return source_node
    return "connected input"


def _append_trace(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative_or_absolute(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    resolved = path.expanduser().resolve(strict=False)
    try:
        return resolved.relative_to(root.expanduser().resolve(strict=False)).as_posix()
    except ValueError:
        return str(resolved)
