from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

WORKFLOW_TEMPLATE_SCHEMA = "drawai.workflow_template.v1"
NODE_RUN_SCHEMA = "drawai.workflow_node_run.v1"

PortCardinality = Literal["single", "many"]
NodeRunStatus = Literal["queued", "running", "ok", "failed", "blocked", "stale"]


@dataclass(frozen=True)
class WorkflowPort:
    port_id: str
    label: str
    types: tuple[str, ...]
    required: bool = True
    cardinality: PortCardinality = "single"
    formats: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "port_id": self.port_id,
            "label": self.label,
            "types": list(self.types),
            "required": self.required,
            "cardinality": self.cardinality,
            "formats": list(self.formats),
            "description": self.description,
        }


@dataclass(frozen=True)
class WorkflowNode:
    node_id: str
    node_type: str
    title: str
    inputs: tuple[WorkflowPort, ...] = ()
    outputs: tuple[WorkflowPort, ...] = ()
    config: Mapping[str, Any] = field(default_factory=dict)
    position: Mapping[str, float] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "title": self.title,
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
            "config": _jsonable(self.config),
            "position": _jsonable(self.position),
            "description": self.description,
        }


@dataclass(frozen=True)
class WorkflowEdge:
    edge_id: str
    source_node_id: str
    source_port_id: str
    target_node_id: str
    target_port_id: str
    enabled_types: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "source_port_id": self.source_port_id,
            "target_node_id": self.target_node_id,
            "target_port_id": self.target_port_id,
            "enabled_types": list(self.enabled_types),
        }


@dataclass(frozen=True)
class WorkflowTemplate:
    template_id: str
    name: str
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    description: str = ""
    version: int = 1
    schema: str = WORKFLOW_TEMPLATE_SCHEMA
    defaults: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "defaults": _jsonable(self.defaults),
        }


@dataclass(frozen=True)
class WorkflowValidationError:
    code: str
    message: str
    node_id: str = ""
    edge_id: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "node_id": self.node_id,
            "edge_id": self.edge_id,
            "details": _jsonable(self.details),
        }


@dataclass(frozen=True)
class WorkflowValidationResult:
    ok: bool
    errors: tuple[WorkflowValidationError, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [error.to_dict() for error in self.errors],
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value
