from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .agents import agent_preset_by_id
from .schema import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowPort,
    WorkflowTemplate,
    WorkflowValidationError,
    WorkflowValidationResult,
)


def validate_workflow_template(template: WorkflowTemplate) -> WorkflowValidationResult:
    errors: list[WorkflowValidationError] = []
    nodes = {node.node_id: node for node in template.nodes}
    if len(nodes) != len(template.nodes):
        errors.append(
            WorkflowValidationError(
                "duplicate_node_id",
                "Workflow node ids must be unique.",
            )
        )

    incoming_by_target_port: dict[
        tuple[str, str],
        list[tuple[WorkflowEdge, tuple[str, ...]]],
    ] = defaultdict(list)
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in template.edges:
        source_node = nodes.get(edge.source_node_id)
        target_node = nodes.get(edge.target_node_id)
        if source_node is None or target_node is None:
            errors.append(
                WorkflowValidationError(
                    "edge_unknown_node",
                    "Workflow edge references an unknown node.",
                    edge_id=edge.edge_id,
                    details={
                        "source_node_id": edge.source_node_id,
                        "target_node_id": edge.target_node_id,
                    },
                )
            )
            continue
        source_port = _find_port(source_node.outputs, edge.source_port_id)
        target_port = _find_port(target_node.inputs, edge.target_port_id)
        if source_port is None or target_port is None:
            errors.append(
                WorkflowValidationError(
                    "edge_unknown_port",
                    "Workflow edge references an unknown port.",
                    edge_id=edge.edge_id,
                    details={
                        "source_port_id": edge.source_port_id,
                        "target_port_id": edge.target_port_id,
                    },
                )
            )
            continue
        overlap = _edge_type_overlap(edge, source_port, target_port)
        if not overlap:
            errors.append(
                WorkflowValidationError(
                    "incompatible_edge_types",
                    "Workflow edge has no compatible output/input type overlap.",
                    edge_id=edge.edge_id,
                    details={
                        "source_types": source_port.types,
                        "target_types": target_port.types,
                    },
                )
            )
            continue
        incoming_by_target_port[(target_node.node_id, target_port.port_id)].append(
            (edge, overlap)
        )
        adjacency[source_node.node_id].append(target_node.node_id)

    for node in template.nodes:
        if node.node_type in {"agent", "llm"}:
            errors.extend(_validate_agent_outputs(node))
        for input_port in node.inputs:
            incoming = incoming_by_target_port.get((node.node_id, input_port.port_id), [])
            if input_port.required and not incoming:
                errors.append(
                    WorkflowValidationError(
                        "required_input_unconnected",
                        "Required workflow input is not connected.",
                        node_id=node.node_id,
                        details={"port_id": input_port.port_id},
                    )
                )
            if input_port.cardinality == "single" and len(incoming) > 1:
                seen_types: dict[str, int] = defaultdict(int)
                for _edge, overlap in incoming:
                    for type_name in overlap:
                        seen_types[type_name] += 1
                duplicated_types = sorted(
                    type_name for type_name, count in seen_types.items() if count > 1
                )
                if duplicated_types:
                    errors.append(
                        WorkflowValidationError(
                            "single_input_multiple_sources",
                            "Single-cardinality input receives multiple sources with the same type.",
                            node_id=node.node_id,
                            details={
                                "port_id": input_port.port_id,
                                "types": duplicated_types,
                            },
                        )
                    )

    cycle_node = _first_cycle_node(tuple(nodes), adjacency)
    if cycle_node:
        errors.append(
            WorkflowValidationError(
                "workflow_cycle",
                "Workflow graph contains a cycle.",
                node_id=cycle_node,
            )
        )

    return WorkflowValidationResult(ok=not errors, errors=tuple(errors))


def _validate_agent_outputs(node: WorkflowNode) -> list[WorkflowValidationError]:
    errors: list[WorkflowValidationError] = []
    output_ports = {port.port_id: port for port in node.outputs}
    try:
        declarations = _agent_output_declarations(node)
    except ValueError as exc:
        return [
            WorkflowValidationError(
                "agent_output_invalid",
                str(exc),
                node_id=node.node_id,
            )
        ]
    for index, declaration in enumerate(declarations):
        port_id = str(declaration.get("port_id") or "")
        output_type = str(declaration.get("type") or "")
        format_id = str(declaration.get("format_id") or "")
        port = output_ports.get(port_id)
        if port is None:
            errors.append(
                WorkflowValidationError(
                    "agent_output_unknown_port",
                    "Agent declared output references an unknown node output port.",
                    node_id=node.node_id,
                    details={"index": index, "port_id": port_id},
                )
            )
            continue
        if output_type not in port.types:
            errors.append(
                WorkflowValidationError(
                    "agent_output_incompatible_type",
                    "Agent declared output type is not allowed by the node output port.",
                    node_id=node.node_id,
                    details={
                        "index": index,
                        "port_id": port_id,
                        "type": output_type,
                        "allowed_types": port.types,
                    },
                )
            )
        if port.formats and format_id not in port.formats:
            errors.append(
                WorkflowValidationError(
                    "agent_output_incompatible_format",
                    "Agent declared output format is not allowed by the node output port.",
                    node_id=node.node_id,
                    details={
                        "index": index,
                        "port_id": port_id,
                        "format_id": format_id,
                        "allowed_formats": port.formats,
                    },
                )
            )
    return errors


def _agent_output_declarations(node: WorkflowNode) -> tuple[Mapping[str, Any], ...]:
    raw_outputs = node.config.get("outputs", node.config.get("output_declarations"))
    if raw_outputs is None:
        preset_id = str(node.config.get("preset_id") or "custom_agent")
        return tuple(output.to_dict() for output in agent_preset_by_id(preset_id).outputs)
    if not isinstance(raw_outputs, list | tuple):
        raise ValueError("Agent outputs must be an array")
    declarations: list[Mapping[str, Any]] = []
    for index, raw_output in enumerate(raw_outputs):
        if not isinstance(raw_output, Mapping):
            raise ValueError(f"Agent outputs[{index}] must be an object")
        declarations.append(raw_output)
    return tuple(declarations)


def _find_port(ports: tuple[WorkflowPort, ...], port_id: str) -> WorkflowPort | None:
    return next((port for port in ports if port.port_id == port_id), None)


def _edge_type_overlap(
    edge: WorkflowEdge,
    source_port: WorkflowPort,
    target_port: WorkflowPort,
) -> tuple[str, ...]:
    source_types = set(source_port.types)
    if edge.enabled_types:
        source_types &= set(edge.enabled_types)
    return tuple(sorted(source_types & set(target_port.types)))


def _first_cycle_node(node_ids: tuple[str, ...], adjacency: dict[str, list[str]]) -> str:
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(node_id: str) -> str:
        if node_id in permanent:
            return ""
        if node_id in temporary:
            return node_id
        temporary.add(node_id)
        for next_node_id in adjacency.get(node_id, []):
            cycle = visit(next_node_id)
            if cycle:
                return cycle
        temporary.remove(node_id)
        permanent.add(node_id)
        return ""

    for node_id in node_ids:
        cycle = visit(node_id)
        if cycle:
            return cycle
    return ""
