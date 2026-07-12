from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from ..prompt_plan import DEFAULT_SAM3_PROMPTS
from .agent_prompt_defaults import (
    CUSTOM_AGENT_CONSTRAINTS,
    CUSTOM_AGENT_TASK,
    DEFAULT_PAGE_SPEC_REFINE_PROCESSING_TYPES,
    PAGE_SPEC_REFINE_CONSTRAINTS,
    PAGE_SPEC_REFINE_TASK,
    PAGE_SPEC_REFINE_TASK_ZH,
    RUN0_ELEMENT_REFINE_CONSTRAINTS,
    RUN0_ELEMENT_REFINE_TASK,
    SVG_GENERATION_CONSTRAINTS,
    SVG_GENERATION_TASK_ZH,
    normalize_page_spec_processing_types,
)
from .schema import (
    WORKFLOW_TEMPLATE_SCHEMA,
    WorkflowEdge,
    WorkflowNode,
    WorkflowPort,
    WorkflowTemplate,
)
from .validation import validate_workflow_template

DEFAULT_WORKFLOW_TEMPLATE_ID = "default_drawai_dag"
IMAGE_TO_PPTX_ZH_WORKFLOW_TEMPLATE_ID = "image_to_pptx_zh"
PROCESSOR_TEST_WORKFLOW_TEMPLATE_ID = "processor_test_page_spec_assets"
PROCESSOR_TEST_PAGE_SPEC_PROCESSING_TYPES = (
    "no_process",
    "crop",
    "crop_nobg",
    "image_generate",
    "image_edit",
)
_BUILTIN_TEMPLATE_IDS = (
    DEFAULT_WORKFLOW_TEMPLATE_ID,
    IMAGE_TO_PPTX_ZH_WORKFLOW_TEMPLATE_ID,
    PROCESSOR_TEST_WORKFLOW_TEMPLATE_ID,
)


def default_drawai_workflow_template() -> WorkflowTemplate:
    return WorkflowTemplate(
        template_id=DEFAULT_WORKFLOW_TEMPLATE_ID,
        name="Image-to-PPTX",
        description="Built-in PageSpec-first workflow that turns one or more images into editable SVG/PPTX outputs.",
        nodes=(
            WorkflowNode(
                node_id="input",
                node_type="input",
                title="Input",
                outputs=(
                    _output(
                        "image",
                        "Image",
                        ("image",),
                        formats=("drawai.image.v1",),
                        description="Original one-page raster image. Treat this as the visual source of truth.",
                    ),
                ),
                position={"x": 0, "y": 160},
            ),
            WorkflowNode(
                node_id="sam_parse",
                node_type="processor",
                title="SAM Parse",
                inputs=(
                    _input(
                        "image",
                        "Image",
                        ("image",),
                        description="Original page image for SAM segmentation proposals.",
                    ),
                ),
                outputs=(
                    _output(
                        "sam_page_spec",
                        "SAM Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="PageSpec evidence produced from SAM regions for this page.",
                    ),
                ),
                config={
                    "processor_id": "sam_parse",
                    "stage": "sam_parse",
                    "prompts": _sam3_prompt_configs(),
                },
                position={"x": 280, "y": 80},
            ),
            WorkflowNode(
                node_id="ocr_parse",
                node_type="processor",
                title="OCR Parse",
                inputs=(
                    _input(
                        "image",
                        "Image",
                        ("image",),
                        description="Original page image for OCR text box detection.",
                    ),
                ),
                outputs=(
                    _output(
                        "ocr_page_spec",
                        "OCR Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="PageSpec evidence produced from OCR text boxes for this page.",
                    ),
                ),
                config={"processor_id": "ocr_parse", "stage": "ocr_parse"},
                position={"x": 280, "y": 240},
            ),
            WorkflowNode(
                node_id="page_spec_fuse",
                node_type="processor",
                title="PageSpec Fuse",
                inputs=(
                    _input(
                        "sam_page_spec",
                        "SAM Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="SAM-derived PageSpec evidence to fuse with OCR evidence.",
                    ),
                    _input(
                        "ocr_page_spec",
                        "OCR Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="OCR-derived PageSpec evidence to fuse with SAM evidence.",
                    ),
                ),
                outputs=(
                    _output(
                        "page_spec",
                        "Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="Fused PageSpec evidence from connected parser nodes. This is still evidence, not final refined truth.",
                    ),
                ),
                config={"processor_id": "page_spec_fuse", "stage": "fuse_elements"},
                position={"x": 560, "y": 160},
            ),
            WorkflowNode(
                node_id="page_spec_refine",
                node_type="agent",
                title="PageSpec Refine",
                inputs=(
                    _input(
                        "image",
                        "Image",
                        ("image",),
                        formats=("drawai.image.v1",),
                        description="Original page image. Use as visual truth for bbox, text, object boundaries, and crop/crop_nobg decisions.",
                    ),
                    _input(
                        "page_spec",
                        "Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="Upstream PageSpec evidence to refine directly. Keep decisions in PageSpec elements and metadata.",
                    ),
                ),
                outputs=(
                    _output(
                        "page_spec",
                        "Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="Refined one-page PageSpec JSON. Elements are the source of truth for downstream asset preparation.",
                    ),
                ),
                config={
                    "preset_id": "page_spec_refine",
                    "provider_id": "default",
                    "page_spec_processing_types": list(DEFAULT_PAGE_SPEC_REFINE_PROCESSING_TYPES),
                    "task": PAGE_SPEC_REFINE_TASK,
                    "constraints": list(PAGE_SPEC_REFINE_CONSTRAINTS),
                    "drawai_tools": ["format"],
                    "outputs": [
                        {
                            "port_id": "page_spec",
                            "path": "output/page_spec.json",
                            "format_id": "drawai.page_spec.v1",
                            "type": "page_spec",
                            "description": "Refined one-page PageSpec JSON.",
                        }
                    ],
                },
                position={"x": 840, "y": 160},
            ),
            WorkflowNode(
                node_id="asset_prepare",
                node_type="processor",
                title="Asset Prepare",
                inputs=(
                    _input(
                        "image",
                        "Image",
                        ("image",),
                        formats=("drawai.image.v1",),
                        description="Original page image used to crop and remove backgrounds for PageSpec raster elements.",
                    ),
                    _input(
                        "page_spec",
                        "Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="Refined PageSpec whose element build.processing_type controls asset materialization.",
                    ),
                ),
                outputs=(
                    _output(
                        "page_spec",
                        "Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="Materialized PageSpec. crop/crop_nobg elements contain element.materialization paths relative to this bundle.",
                    ),
                ),
                config={"processor_id": "asset_prepare", "stage": "process_assets"},
                position={"x": 1120, "y": 160},
            ),
            WorkflowNode(
                node_id="svg_compose",
                node_type="agent",
                title="SVG Compose",
                inputs=(
                    _input(
                        "image",
                        "Image",
                        ("image",),
                        formats=("drawai.image.v1",),
                        description="Original page image. Use as visual truth while composing and comparing the SVG.",
                    ),
                    _input(
                        "page_spec",
                        "Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        description="Materialized PageSpec from asset_prepare. Use element ids, bbox/style/text/build fields, and materialization paths for allowed crop/crop_nobg raster hrefs.",
                    ),
                ),
                outputs=(
                    _output(
                        "semantic_svg",
                        "Semantic SVG",
                        ("semantic_svg",),
                        formats=("drawai.semantic_svg.v1",),
                        deliverable=True,
                        description="Editable semantic SVG final for preview, PPT export, and final outputs.",
                    ),
                ),
                config={
                    "preset_id": "svg_generation",
                    "provider_id": "default",
                    "task": SVG_GENERATION_TASK_ZH,
                    "constraints": list(SVG_GENERATION_CONSTRAINTS),
                    "drawai_tools": ["format", "page-spec-assets", "svg-validate"],
                    "outputs": [
                        {
                            "port_id": "semantic_svg",
                            "path": "output/semantic.svg",
                            "format_id": "drawai.semantic_svg.v1",
                            "type": "semantic_svg",
                            "description": "Editable semantic SVG rooted at an svg element.",
                        }
                    ],
                },
                position={"x": 1400, "y": 160},
            ),
            WorkflowNode(
                node_id="svg_to_ppt",
                node_type="export",
                title="SVG to PPT",
                inputs=(
                    _input(
                        "semantic_svg",
                        "Semantic SVG",
                        ("semantic_svg",),
                        description="Final semantic SVG produced by svg_compose.",
                    ),
                    _input(
                        "page_spec",
                        "Page Spec",
                        ("page_spec",),
                        formats=("drawai.page_spec.v1",),
                        required=False,
                        description="Optional materialized PageSpec for SVG-to-PPT export context.",
                    ),
                ),
                outputs=(
                    _output(
                        "pptx",
                        "PPTX",
                        ("pptx",),
                        formats=("drawai.pptx.v1",),
                        deliverable=True,
                        description="Editable PPTX export generated from the semantic SVG.",
                    ),
                ),
                config={"exporter_id": "svg_to_ppt"},
                position={"x": 1680, "y": 160},
            ),
            WorkflowNode(
                node_id="output",
                node_type="output",
                title="Output",
                inputs=(
                    _input(
                        "deliverables",
                        "Deliverables",
                        ("semantic_svg", "pptx"),
                        cardinality="many",
                        description="Collect final deliverable artifacts from upstream nodes.",
                    ),
                ),
                outputs=(
                    _output(
                        "final_outputs",
                        "Final Outputs",
                        ("final_outputs",),
                        formats=("drawai.final_outputs.v1",),
                    ),
                ),
                config={"auto_collect_deliverables": True},
                position={"x": 1960, "y": 160},
            ),
        ),
        edges=(
            _edge("input", "image", "sam_parse", "image"),
            _edge("input", "image", "ocr_parse", "image"),
            _edge("input", "image", "page_spec_refine", "image"),
            _edge("input", "image", "asset_prepare", "image"),
            _edge("input", "image", "svg_compose", "image"),
            _edge("sam_parse", "sam_page_spec", "page_spec_fuse", "sam_page_spec"),
            _edge("ocr_parse", "ocr_page_spec", "page_spec_fuse", "ocr_page_spec"),
            _edge("page_spec_fuse", "page_spec", "page_spec_refine", "page_spec"),
            _edge("page_spec_refine", "page_spec", "asset_prepare", "page_spec"),
            _edge("asset_prepare", "page_spec", "svg_compose", "page_spec"),
            _edge("svg_compose", "semantic_svg", "svg_to_ppt", "semantic_svg"),
            _edge("asset_prepare", "page_spec", "svg_to_ppt", "page_spec"),
            _edge("svg_compose", "semantic_svg", "output", "deliverables"),
            _edge("svg_to_ppt", "pptx", "output", "deliverables"),
        ),
        defaults={
            "builtin": True,
            "read_only": True,
            "agent_provider_id": "default",
        },
    )


def processor_test_page_spec_assets_workflow_template() -> WorkflowTemplate:
    base = default_drawai_workflow_template()
    keep_node_ids = {
        "input",
        "sam_parse",
        "ocr_parse",
        "page_spec_fuse",
        "page_spec_refine",
        "asset_prepare",
        "output",
    }
    nodes: list[WorkflowNode] = []
    for node in base.nodes:
        if node.node_id not in keep_node_ids:
            continue
        if node.node_id == "page_spec_refine":
            nodes.append(
                replace(
                    node,
                    config={
                        **dict(node.config),
                        "page_spec_processing_types": list(PROCESSOR_TEST_PAGE_SPEC_PROCESSING_TYPES),
                    },
                )
            )
            continue
        if node.node_id == "asset_prepare":
            outputs = (
                replace(
                    node.outputs[0],
                    description=(
                        "Materialized PageSpec plus processor placement preview. "
                        "crop/crop_nobg/image_generate/image_edit elements contain active materialization paths."
                    ),
                ),
                _output(
                    "processor_preview",
                    "Processor Preview",
                    ("semantic_svg",),
                    formats=("drawai.semantic_svg.v1",),
                    deliverable=True,
                    description="Deterministic SVG preview that places processed active assets back into PageSpec boxes.",
                ),
            )
            nodes.append(replace(node, outputs=outputs, position={"x": 1120, "y": 160}))
            continue
        if node.node_id == "output":
            nodes.append(
                replace(
                    node,
                    inputs=(
                        _input(
                            "deliverables",
                            "Deliverables",
                            ("page_spec", "semantic_svg"),
                            cardinality="many",
                            description="Collect processor-test PageSpec outputs from asset_prepare.",
                        ),
                    ),
                    position={"x": 1400, "y": 160},
                )
            )
            continue
        nodes.append(node)

    edges = tuple(
        edge
        for edge in base.edges
        if edge.source_node_id in keep_node_ids
        and edge.target_node_id in keep_node_ids
        and edge.source_node_id not in {"svg_compose", "svg_to_ppt"}
        and edge.target_node_id not in {"svg_compose", "svg_to_ppt"}
    )
    edges = (
        *edges,
        _edge("asset_prepare", "page_spec", "output", "deliverables"),
        _edge("asset_prepare", "processor_preview", "output", "deliverables"),
    )
    defaults = dict(base.defaults)
    defaults["builtin"] = True
    defaults["read_only"] = True
    return replace(
        base,
        template_id=PROCESSOR_TEST_WORKFLOW_TEMPLATE_ID,
        name="Processor Test: PageSpec Assets",
        description=(
            "Built-in PageSpec workflow for testing asset_prepare processor choices and placement "
            "without SVG Compose or PPT export."
        ),
        nodes=tuple(nodes),
        edges=edges,
        defaults=defaults,
    )


def image_to_pptx_zh_workflow_template() -> WorkflowTemplate:
    base = default_drawai_workflow_template()
    nodes: list[WorkflowNode] = []
    for node in base.nodes:
        if node.node_id == "page_spec_refine":
            nodes.append(
                replace(
                    node,
                    config={
                        **dict(node.config),
                        "task": PAGE_SPEC_REFINE_TASK_ZH,
                    },
                )
            )
            continue
        if node.node_id == "svg_compose":
            nodes.append(
                replace(
                    node,
                    config={
                        **dict(node.config),
                        "task": SVG_GENERATION_TASK_ZH,
                    },
                )
            )
            continue
        nodes.append(node)

    return replace(
        base,
        template_id=IMAGE_TO_PPTX_ZH_WORKFLOW_TEMPLATE_ID,
        name="Image-to-PPTX-zh",
        description=(
            "Built-in PageSpec-first Image-to-PPTX workflow with Chinese task prompts "
            "for the PageSpec Refine and SVG Compose Agent nodes."
        ),
        nodes=tuple(nodes),
    )


def workflow_templates_dir(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve(strict=False) / ".drawai" / "workflows"


def user_workflow_template_path(workspace: str | Path, template_id: str) -> Path:
    return workflow_templates_dir(workspace) / f"{_safe_template_id(template_id)}.json"


def builtin_workflow_templates() -> tuple[WorkflowTemplate, ...]:
    return (
        default_drawai_workflow_template(),
        image_to_pptx_zh_workflow_template(),
        processor_test_page_spec_assets_workflow_template(),
    )


def load_workflow_template_by_id(workspace: str | Path, template_id: str) -> WorkflowTemplate:
    if template_id in _BUILTIN_TEMPLATE_IDS:
        return _builtin_workflow_template(template_id)
    return load_workflow_template(user_workflow_template_path(workspace, template_id))


def list_workflow_templates(
    workspace: str | Path,
    *,
    include_builtin: bool = True,
) -> tuple[WorkflowTemplate, ...]:
    templates: list[WorkflowTemplate] = []
    if include_builtin:
        templates.extend(builtin_workflow_templates())

    directory = workflow_templates_dir(workspace)
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            template = load_workflow_template(path)
            if template.template_id not in {item.template_id for item in templates}:
                templates.append(template)
    return tuple(templates)


def load_workflow_template(path: str | Path) -> WorkflowTemplate:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"workflow template must be a JSON object: {path}")
    template = workflow_template_from_dict(payload)
    _raise_if_invalid(template)
    return template


def save_workflow_template(
    workspace: str | Path,
    template: WorkflowTemplate,
    *,
    overwrite: bool = True,
    validate: bool = True,
) -> Path:
    if validate:
        _raise_if_invalid(template)
    path = user_workflow_template_path(workspace, template.template_id)
    if path.exists() and not overwrite:
        raise FileExistsError(f"workflow template already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(template.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def copy_builtin_template_to_workspace(
    workspace: str | Path,
    template_id: str,
    *,
    name: str,
    overwrite: bool = True,
) -> WorkflowTemplate:
    template = copy_builtin_template(template_id, name=name)
    save_workflow_template(workspace, template, overwrite=overwrite)
    return template


def copy_builtin_template(template_id: str, *, name: str) -> WorkflowTemplate:
    if template_id not in _BUILTIN_TEMPLATE_IDS:
        raise ValueError(f"unknown built-in workflow template: {template_id}")
    copied_id = f"custom_{_safe_template_id(name).replace('-', '_')}"
    source_template = _builtin_workflow_template(template_id)
    defaults = dict(source_template.defaults)
    defaults["builtin"] = False
    defaults["read_only"] = False
    defaults["source_template_id"] = template_id
    return replace(
        source_template,
        template_id=copied_id,
        name=name,
        defaults=defaults,
    )


def workflow_template_from_dict(payload: Mapping[str, Any]) -> WorkflowTemplate:
    schema = _string(payload.get("schema", WORKFLOW_TEMPLATE_SCHEMA), "schema")
    if schema != WORKFLOW_TEMPLATE_SCHEMA:
        raise ValueError(f"unsupported workflow template schema: {schema}")
    return WorkflowTemplate(
        schema=schema,
        template_id=_string(payload.get("template_id"), "template_id"),
        name=_string(payload.get("name"), "name"),
        description=_string(payload.get("description", ""), "description"),
        version=_integer(payload.get("version", 1), "version"),
        nodes=tuple(_node_from_dict(item, f"nodes[{index}]") for index, item in enumerate(_sequence(payload.get("nodes"), "nodes"))),
        edges=tuple(_edge_from_dict(item, f"edges[{index}]") for index, item in enumerate(_sequence(payload.get("edges"), "edges"))),
        defaults=dict(_mapping(payload.get("defaults", {}), "defaults")),
    )


def _builtin_workflow_template(template_id: str) -> WorkflowTemplate:
    if template_id == DEFAULT_WORKFLOW_TEMPLATE_ID:
        return default_drawai_workflow_template()
    if template_id == IMAGE_TO_PPTX_ZH_WORKFLOW_TEMPLATE_ID:
        return image_to_pptx_zh_workflow_template()
    if template_id == PROCESSOR_TEST_WORKFLOW_TEMPLATE_ID:
        return processor_test_page_spec_assets_workflow_template()
    raise ValueError(f"unknown built-in workflow template: {template_id}")


def _sam3_prompt_configs() -> list[dict[str, Any]]:
    return [
        {
            "id": prompt.id,
            "text": prompt.text,
            "confidence_threshold": prompt.confidence_threshold,
        }
        for prompt in DEFAULT_SAM3_PROMPTS
    ]


def _node_from_dict(payload: object, field_name: str) -> WorkflowNode:
    data = _mapping(payload, field_name)
    node_type = _string(data.get("node_type"), f"{field_name}.node_type")
    config = dict(_mapping(data.get("config", {}), f"{field_name}.config"))
    config = _normalized_node_config(node_type, config)
    title = _normalized_node_title(
        node_type,
        _string(data.get("title"), f"{field_name}.title"),
        config,
    )
    return WorkflowNode(
        node_id=_string(data.get("node_id"), f"{field_name}.node_id"),
        node_type=node_type,
        title=title,
        inputs=tuple(
            _port_from_dict(item, f"{field_name}.inputs[{index}]")
            for index, item in enumerate(_sequence(data.get("inputs", ()), f"{field_name}.inputs"))
        ),
        outputs=tuple(
            _port_from_dict(item, f"{field_name}.outputs[{index}]")
            for index, item in enumerate(_sequence(data.get("outputs", ()), f"{field_name}.outputs"))
        ),
        config=config,
        position=_number_mapping(data.get("position", {}), f"{field_name}.position"),
        description=_string(data.get("description", ""), f"{field_name}.description"),
    )


_LEGACY_AGENT_TASK_TEXTS: dict[str, set[str]] = {
    "run0_element_refine": {
        "Refine element bbox, size, and type. Preserve IDs unless merge/delete is declared.",
        "Refine element positions, types, and processing intent.",
        "Refine element positions, sizes, and object types from connected parser or fusion outputs. Preserve the DrawAI element plan format.",
    },
    "svg_generation": {
        "Generate an editable SVG using connected element plans and confirmed assets.",
        "Generate editable semantic SVG from element plans and asset packages.",
        "Generate an editable semantic SVG from connected element plans and asset packages. Preserve raster assets only through declared package references.",
    },
    "custom_agent": {
        "Use the connected files as context and write the declared outputs exactly.",
        "Use the connected input files as context and produce exactly the output files declared by this node configuration.",
    },
}

_AGENT_TASK_DEFAULTS = {
    "run0_element_refine": RUN0_ELEMENT_REFINE_TASK,
    "page_spec_refine": PAGE_SPEC_REFINE_TASK,
    "svg_generation": SVG_GENERATION_TASK_ZH,
    "custom_agent": CUSTOM_AGENT_TASK,
}

_AGENT_CONSTRAINT_DEFAULTS = {
    "run0_element_refine": RUN0_ELEMENT_REFINE_CONSTRAINTS,
    "page_spec_refine": PAGE_SPEC_REFINE_CONSTRAINTS,
    "svg_generation": SVG_GENERATION_CONSTRAINTS,
    "custom_agent": CUSTOM_AGENT_CONSTRAINTS,
}


def _normalized_node_config(node_type: str, config: dict[str, Any]) -> dict[str, Any]:
    if node_type != "agent":
        return config
    preset_id = str(config.get("preset_id") or "")
    default_task = _AGENT_TASK_DEFAULTS.get(preset_id)
    if default_task is None:
        return config
    normalized = dict(config)
    raw_task = _config_text(
        normalized.get("task")
        or normalized.get("prompt_role")
        or normalized.get("prompt_fragments")
        or normalized.get("user_prompt")
    )
    if not raw_task or raw_task in _LEGACY_AGENT_TASK_TEXTS.get(preset_id, set()):
        normalized["task"] = default_task
        normalized.pop("prompt_role", None)
        normalized.pop("prompt_fragments", None)
    raw_constraints = normalized.get("constraints")
    if raw_constraints in (None, "", []):
        normalized["constraints"] = list(_AGENT_CONSTRAINT_DEFAULTS[preset_id])
    if preset_id == "page_spec_refine":
        normalized["page_spec_processing_types"] = list(
            normalize_page_spec_processing_types(
                normalized.get("page_spec_processing_types")
            )
        )
    return normalized


def _config_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list | tuple):
        return "\n\n".join(item.strip() for item in value if isinstance(item, str)).strip()
    return ""


def _normalized_node_title(
    node_type: str,
    title: str,
    config: Mapping[str, Any],
) -> str:
    if (
        node_type == "agent"
        and config.get("preset_id") == "run0_element_refine"
        and title in {"Run0 Agent", "Run0 元素校正"}
    ):
        return "Asset Refine Agent"
    return title


def _port_from_dict(payload: object, field_name: str) -> WorkflowPort:
    data = _mapping(payload, field_name)
    cardinality = _string(data.get("cardinality", "single"), f"{field_name}.cardinality")
    if cardinality not in {"single", "many"}:
        raise ValueError(f"{field_name}.cardinality must be single or many")
    return WorkflowPort(
        port_id=_string(data.get("port_id"), f"{field_name}.port_id"),
        label=_string(data.get("label"), f"{field_name}.label"),
        types=_string_tuple(data.get("types"), f"{field_name}.types"),
        required=_boolean(data.get("required", True), f"{field_name}.required"),
        cardinality=cardinality,  # type: ignore[arg-type]
        formats=_string_tuple(data.get("formats", ()), f"{field_name}.formats"),
        description=_string(data.get("description", ""), f"{field_name}.description"),
    )


def _edge_from_dict(payload: object, field_name: str) -> WorkflowEdge:
    data = _mapping(payload, field_name)
    return WorkflowEdge(
        edge_id=_string(data.get("edge_id"), f"{field_name}.edge_id"),
        source_node_id=_string(data.get("source_node_id"), f"{field_name}.source_node_id"),
        source_port_id=_string(data.get("source_port_id"), f"{field_name}.source_port_id"),
        target_node_id=_string(data.get("target_node_id"), f"{field_name}.target_node_id"),
        target_port_id=_string(data.get("target_port_id"), f"{field_name}.target_port_id"),
        enabled_types=_string_tuple(data.get("enabled_types", ()), f"{field_name}.enabled_types"),
    )


def _raise_if_invalid(template: WorkflowTemplate) -> None:
    result = validate_workflow_template(template)
    if not result.ok:
        codes = ", ".join(error.code for error in result.errors)
        raise ValueError(f"workflow template is invalid: {codes}")


def _input(
    port_id: str,
    label: str,
    types: tuple[str, ...],
    *,
    required: bool = True,
    cardinality: str = "single",
    formats: tuple[str, ...] = (),
    description: str = "",
) -> WorkflowPort:
    return WorkflowPort(
        port_id=port_id,
        label=label,
        types=types,
        required=required,
        cardinality=cardinality,  # type: ignore[arg-type]
        formats=formats,
        description=description,
    )


def _output(
    port_id: str,
    label: str,
    types: tuple[str, ...],
    *,
    formats: tuple[str, ...] = (),
    deliverable: bool = False,
    description: str = "",
) -> WorkflowPort:
    port_description = description
    if deliverable:
        port_description = f"deliverable; {description}" if description else "deliverable"
    return WorkflowPort(
        port_id=port_id,
        label=label,
        types=types,
        required=False,
        formats=formats,
        description=port_description,
    )


def _edge(
    source_node_id: str,
    source_port_id: str,
    target_node_id: str,
    target_port_id: str,
) -> WorkflowEdge:
    return WorkflowEdge(
        edge_id=f"{source_node_id}:{source_port_id}->{target_node_id}:{target_port_id}",
        source_node_id=source_node_id,
        source_port_id=source_port_id,
        target_node_id=target_node_id,
        target_port_id=target_port_id,
    )


def _safe_template_id(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_").lower()
    if not slug:
        raise ValueError("template id must contain at least one safe character")
    return slug


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _sequence(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be an array")
    return tuple(value)


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    items = _sequence(value, field_name)
    strings: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise ValueError(f"{field_name}[{index}] must be a string")
        strings.append(item)
    return tuple(strings)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _number_mapping(value: object, field_name: str) -> Mapping[str, float]:
    data = _mapping(value, field_name)
    result: dict[str, float] = {}
    for key, item in data.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
        if not isinstance(item, int | float) or isinstance(item, bool):
            raise ValueError(f"{field_name}.{key} must be numeric")
        result[key] = float(item)
    return result
