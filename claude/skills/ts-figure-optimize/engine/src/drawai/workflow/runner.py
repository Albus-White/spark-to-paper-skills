from __future__ import annotations

import json
import shutil
from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .formats import FormatSpec, default_format_registry, validate_format_file
from .node_runs import (
    NodeRunRecord,
    begin_node_run,
    finish_node_run_blocked,
    finish_node_run_failed,
    finish_node_run_ok,
)
from .schema import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowPort,
    WorkflowTemplate,
)
from .validation import validate_workflow_template

NodeHandler = Callable[
    ["NodeRunContext", tuple[Mapping[str, Any], ...]],
    Sequence[Mapping[str, Any]],
]
ResourceAcquirer = Callable[[WorkflowNode], str]


@dataclass(frozen=True)
class NodeRunContext:
    template: WorkflowTemplate
    node: WorkflowNode
    run_root: Path
    record: NodeRunRecord

    @property
    def output_dir(self) -> Path:
        return self.record.workdir / "output"

    def relative_path(self, path: str | Path) -> str:
        return _run_relative(self.run_root, Path(path))


@dataclass(frozen=True)
class NodeRunSummary:
    node_id: str
    status: str
    workdir: str
    outputs: tuple[Mapping[str, Any], ...] = ()
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "workdir": self.workdir,
            "outputs": [dict(output) for output in self.outputs],
            "error": self.error,
        }


@dataclass(frozen=True)
class WorkflowRunResult:
    ok: bool
    template_id: str
    run_root: str
    node_runs: tuple[NodeRunSummary, ...]
    final_outputs: tuple[Mapping[str, Any], ...] = ()
    failed_node_ids: tuple[str, ...] = ()
    blocked_node_ids: tuple[str, ...] = ()
    paused_node_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "template_id": self.template_id,
            "run_root": self.run_root,
            "node_runs": [run.to_dict() for run in self.node_runs],
            "final_outputs": [dict(output) for output in self.final_outputs],
            "failed_node_ids": list(self.failed_node_ids),
            "blocked_node_ids": list(self.blocked_node_ids),
            "paused_node_ids": list(self.paused_node_ids),
        }


@dataclass(frozen=True)
class _NodeExecutionResult:
    summary: NodeRunSummary
    outputs: tuple[Mapping[str, Any], ...] = ()
    final_outputs: tuple[Mapping[str, Any], ...] = ()


class WorkflowRunner:
    def __init__(
        self,
        template: WorkflowTemplate,
        *,
        handlers: Mapping[str, NodeHandler],
        acquire_resource: ResourceAcquirer | None = None,
        format_registry: Mapping[str, FormatSpec] | None = None,
        max_workers: int | None = None,
    ) -> None:
        self.template = template
        self.handlers = dict(handlers)
        self.acquire_resource = acquire_resource
        self.format_registry = format_registry or default_format_registry()
        self.max_workers = max_workers

    def run(
        self,
        run_root: str | Path,
        *,
        break_after_node_ids: Sequence[str] = (),
        should_pause_after_node: Callable[[str], bool] | None = None,
        rerun_from_node_id: str = "",
    ) -> WorkflowRunResult:
        validation = validate_workflow_template(self.template)
        if not validation.ok:
            codes = ", ".join(error.code for error in validation.errors)
            raise ValueError(f"workflow template is invalid: {codes}")

        root = Path(run_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        order = _topological_nodes(self.template)
        node_by_id = {node.node_id: node for node in order}
        node_order = {node.node_id: index for index, node in enumerate(order)}
        incoming_edges = _incoming_edges_by_node(self.template)
        outgoing_edges = _outgoing_edges_by_node(self.template)
        rerun_node_ids = _rerun_node_ids(
            self.template,
            rerun_from_node_id,
            outgoing_edges,
        )
        remaining_dependencies = {
            node.node_id: len(incoming_edges.get(node.node_id, ()))
            for node in order
        }
        node_status: dict[str, str] = {}
        outputs_by_port: dict[tuple[str, str], tuple[Mapping[str, Any], ...]] = {}
        summaries_by_node: dict[str, NodeRunSummary] = {}
        final_outputs: tuple[Mapping[str, Any], ...] = ()
        paused_node_ids: set[str] = set()
        static_breakpoints = frozenset(str(node_id) for node_id in break_after_node_ids if str(node_id))

        if rerun_node_ids:
            _seed_previous_node_outputs(
                root,
                order,
                rerun_node_ids,
                outgoing_edges,
                node_status,
                outputs_by_port,
                summaries_by_node,
                remaining_dependencies,
            )

        ready = deque(
            node
            for node in order
            if node.node_id in rerun_node_ids and remaining_dependencies[node.node_id] == 0
        ) if rerun_node_ids else deque(
            node
            for node in order
            if remaining_dependencies[node.node_id] == 0
        )

        with ThreadPoolExecutor(
            max_workers=_runner_worker_count(order, self.max_workers)
        ) as executor:
            running: dict[Future[_NodeExecutionResult], WorkflowNode] = {}
            while ready or running:
                while ready:
                    node = ready.popleft()
                    blocked_sources = tuple(
                        edge.source_node_id
                        for edge in incoming_edges.get(node.node_id, ())
                        if node_status.get(edge.source_node_id) in {"failed", "blocked"}
                    )
                    inputs = _collect_node_inputs(
                        self.template,
                        node,
                        incoming_edges,
                        outputs_by_port,
                    )
                    future = executor.submit(
                        self._execute_node_once,
                        root,
                        node,
                        inputs,
                        blocked_sources,
                    )
                    running[future] = node
                completed, _pending = wait(running, return_when=FIRST_COMPLETED)
                for future in sorted(
                    completed,
                    key=lambda item: node_order[running[item].node_id],
                ):
                    node = running.pop(future)
                    node_result = future.result()
                    summaries_by_node[node.node_id] = node_result.summary
                    node_status[node.node_id] = node_result.summary.status

                    if node_result.summary.status == "ok":
                        for port_id, port_outputs in _outputs_by_port(
                            node_result.outputs
                        ).items():
                            outputs_by_port[(node.node_id, port_id)] = port_outputs
                        if node.node_type == "output":
                            final_outputs = node_result.final_outputs
                        if node.node_id in static_breakpoints or (should_pause_after_node is not None and should_pause_after_node(node.node_id)):
                            paused_node_ids.add(node.node_id)
                            continue

                    for edge in sorted(
                        outgoing_edges.get(node.node_id, ()),
                        key=lambda item: node_order[item.target_node_id],
                    ):
                        remaining_dependencies[edge.target_node_id] -= 1
                        if remaining_dependencies[edge.target_node_id] == 0:
                            ready.append(node_by_id[edge.target_node_id])
                ready = deque(
                    sorted(ready, key=lambda item: node_order[item.node_id])
                )

        failed_node_ids = tuple(
            node.node_id for node in order if node_status.get(node.node_id) == "failed"
        )
        blocked_node_ids = tuple(
            node.node_id for node in order if node_status.get(node.node_id) == "blocked"
        )
        summaries = tuple(summaries_by_node[node.node_id] for node in order if node.node_id in summaries_by_node)

        return WorkflowRunResult(
            ok=not failed_node_ids and not blocked_node_ids,
            template_id=self.template.template_id,
            run_root=str(root),
            node_runs=summaries,
            final_outputs=final_outputs,
            failed_node_ids=failed_node_ids,
            blocked_node_ids=blocked_node_ids,
            paused_node_ids=tuple(node.node_id for node in order if node.node_id in paused_node_ids),
        )

    def _execute_node_once(
        self,
        root: Path,
        node: WorkflowNode,
        inputs: tuple[Mapping[str, Any], ...],
        blocked_sources: tuple[str, ...],
    ) -> _NodeExecutionResult:
        provider_id = _node_provider_id(node)
        resource_id = ""
        if not blocked_sources and self.acquire_resource and _node_needs_resource(node):
            resource_id = str(self.acquire_resource(node) or "")
        record = begin_node_run(
            root,
            node.node_id,
            node_type=node.node_type,
            provider_id=provider_id,
            resource_id=resource_id,
        )

        if blocked_sources:
            error = "blocked by upstream node failure"
            finish_node_run_blocked(record, inputs=inputs, error=error)
            return _NodeExecutionResult(_summary(record, "blocked", error=error))

        missing_input = _missing_required_input(node, inputs)
        if missing_input:
            error = f"required input not produced: {missing_input}"
            finish_node_run_blocked(record, inputs=inputs, error=error)
            return _NodeExecutionResult(_summary(record, "blocked", error=error))

        context = NodeRunContext(
            template=self.template,
            node=node,
            run_root=root,
            record=record,
        )
        try:
            raw_outputs = self._run_node(context, inputs)
            outputs = _normalize_outputs(
                context,
                raw_outputs,
                format_registry=self.format_registry,
            )
        except Exception as exc:  # Node boundary: persist failure and keep downstream state explicit.
            error = f"{type(exc).__name__}: {exc}"
            finish_node_run_failed(
                record,
                inputs=inputs,
                error=error,
                prompt_path=_exception_metadata_path(exc, "prompt_path", root),
                stdout_path=_exception_metadata_path(exc, "stdout_path", root),
                stderr_path=_exception_metadata_path(exc, "stderr_path", root),
                trace_path=_exception_metadata_path(exc, "trace_path", root),
                session_log_path=_exception_metadata_path(exc, "session_log_path", root),
                execution_manifest_path=_exception_metadata_path(exc, "execution_manifest_path", root),
                exit_code=_exception_exit_code(exc),
            )
            return _NodeExecutionResult(_summary(record, "failed", error=error))

        run_metadata = _node_run_metadata(outputs)
        finish_node_run_ok(
            record,
            inputs=inputs,
            outputs=outputs,
            prompt_path=run_metadata["prompt_path"],
            stdout_path=run_metadata["stdout_path"],
            stderr_path=run_metadata["stderr_path"],
            trace_path=run_metadata["trace_path"],
            session_log_path=run_metadata["session_log_path"],
            execution_manifest_path=run_metadata["execution_manifest_path"],
            exit_code=run_metadata["exit_code"],
        )
        final_outputs: tuple[Mapping[str, Any], ...] = ()
        if node.node_type == "output":
            final_outputs = tuple(
                output
                for output in _read_final_outputs(root, outputs)
                if isinstance(output, Mapping)
            )
        return _NodeExecutionResult(
            _summary(record, "ok", outputs=outputs),
            outputs=outputs,
            final_outputs=final_outputs,
        )

    def _run_node(
        self,
        context: NodeRunContext,
        inputs: tuple[Mapping[str, Any], ...],
    ) -> Sequence[Mapping[str, Any]]:
        if context.node.node_type == "output":
            return _run_output_node(context, inputs)
        handler = self.handlers.get(context.node.node_id) or self.handlers.get(
            context.node.node_type
        )
        if handler is None:
            raise ValueError(f"no workflow handler registered for node: {context.node.node_id}")
        return handler(context, inputs)


def _run_output_node(
    context: NodeRunContext,
    inputs: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    outputs: list[dict[str, Any]] = []
    for item in inputs:
        artifact = dict(item)
        if not artifact.get("deliverable"):
            continue
        mirror_path = _mirror_deliverable(context.run_root, artifact)
        if mirror_path:
            artifact["mirror_path"] = mirror_path
        outputs.append(artifact)

    final_outputs_path = context.output_dir / "final_outputs.json"
    _write_json(
        final_outputs_path,
        {
            "schema": "drawai.final_outputs.v1",
            "template_id": context.template.template_id,
            "outputs": outputs,
        },
    )
    return (
        {
            "port_id": _single_output_port_id(context.node),
            "path": context.relative_path(final_outputs_path),
            "format_id": "drawai.final_outputs.v1",
            "type": "final_outputs",
        },
    )


def _normalize_outputs(
    context: NodeRunContext,
    outputs: Sequence[Mapping[str, Any]],
    *,
    format_registry: Mapping[str, FormatSpec],
) -> tuple[Mapping[str, Any], ...]:
    normalized: list[Mapping[str, Any]] = []
    output_ports = {port.port_id: port for port in context.node.outputs}
    for index, raw_output in enumerate(outputs):
        output = dict(raw_output)
        port = _output_port_for_payload(output_ports, output, context.node, index)
        artifact_path = _required_output_path(context.run_root, output, context.node, index)
        output["path"] = _run_relative(context.run_root, artifact_path)
        output["port_id"] = port.port_id
        output["source_node_id"] = context.node.node_id
        output["source_port_id"] = port.port_id
        output["type"] = str(output.get("type") or port.types[0])
        if output["type"] not in port.types:
            raise ValueError(
                f"node {context.node.node_id} output {index} type {output['type']!r} "
                f"is not allowed by port {port.port_id}"
            )
        if not output.get("format_id") and port.formats:
            output["format_id"] = port.formats[0]
        if _port_is_deliverable(port):
            output["deliverable"] = True
        if output.get("format_id"):
            validation = validate_format_file(
                str(output["format_id"]),
                artifact_path,
                registry=format_registry,
            )
            if not validation.ok:
                raise ValueError(
                    "output format validation failed for "
                    f"{context.node.node_id}.{port.port_id}: "
                    + "; ".join(validation.errors)
                )
        normalized.append(output)
    return tuple(normalized)


def _collect_node_inputs(
    template: WorkflowTemplate,
    node: WorkflowNode,
    incoming_edges: Mapping[str, tuple[WorkflowEdge, ...]],
    outputs_by_port: Mapping[tuple[str, str], tuple[Mapping[str, Any], ...]],
) -> tuple[Mapping[str, Any], ...]:
    node_by_id = {item.node_id: item for item in template.nodes}
    inputs_by_id = {port.port_id: port for port in node.inputs}
    collected: list[Mapping[str, Any]] = []
    for edge in incoming_edges.get(node.node_id, ()):
        target_port = inputs_by_id[edge.target_port_id]
        source_node = node_by_id[edge.source_node_id]
        source_port = _find_port(source_node.outputs, edge.source_port_id)
        for output in outputs_by_port.get((edge.source_node_id, edge.source_port_id), ()):
            if _artifact_matches_edge(output, edge, source_port, target_port):
                item = dict(output)
                item["target_node_id"] = node.node_id
                item["target_port_id"] = target_port.port_id
                if not item.get("description"):
                    item["description"] = target_port.description or source_port.description
                item.setdefault("source_port_label", source_port.label)
                item.setdefault("target_port_label", target_port.label)
                collected.append(item)
    return tuple(collected)


def _artifact_matches_edge(
    artifact: Mapping[str, Any],
    edge: WorkflowEdge,
    source_port: WorkflowPort,
    target_port: WorkflowPort,
) -> bool:
    artifact_type = str(artifact.get("type") or "")
    if edge.enabled_types and artifact_type not in edge.enabled_types:
        return False
    return artifact_type in source_port.types and artifact_type in target_port.types


def _missing_required_input(
    node: WorkflowNode,
    inputs: tuple[Mapping[str, Any], ...],
) -> str:
    for port in node.inputs:
        if not port.required:
            continue
        if not any(input_item.get("target_port_id") == port.port_id for input_item in inputs):
            return port.port_id
    return ""


def _topological_nodes(template: WorkflowTemplate) -> tuple[WorkflowNode, ...]:
    node_by_id = {node.node_id: node for node in template.nodes}
    child_ids: dict[str, list[str]] = defaultdict(list)
    in_degree = {node.node_id: 0 for node in template.nodes}
    for edge in template.edges:
        child_ids[edge.source_node_id].append(edge.target_node_id)
        in_degree[edge.target_node_id] += 1

    node_order = {node.node_id: index for index, node in enumerate(template.nodes)}
    ready = deque(
        sorted(
            (node_id for node_id, count in in_degree.items() if count == 0),
            key=node_order.__getitem__,
        )
    )
    ordered: list[WorkflowNode] = []
    while ready:
        node_id = ready.popleft()
        ordered.append(node_by_id[node_id])
        for child_id in sorted(child_ids.get(node_id, ()), key=node_order.__getitem__):
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                ready.append(child_id)
    if len(ordered) != len(template.nodes):
        raise ValueError("workflow graph contains a cycle")
    return tuple(ordered)


def _incoming_edges_by_node(template: WorkflowTemplate) -> dict[str, tuple[WorkflowEdge, ...]]:
    grouped: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in template.edges:
        grouped[edge.target_node_id].append(edge)
    return {node_id: tuple(edges) for node_id, edges in grouped.items()}


def _outgoing_edges_by_node(template: WorkflowTemplate) -> dict[str, tuple[WorkflowEdge, ...]]:
    grouped: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in template.edges:
        grouped[edge.source_node_id].append(edge)
    return {node_id: tuple(edges) for node_id, edges in grouped.items()}


def _rerun_node_ids(
    template: WorkflowTemplate,
    node_id: str,
    outgoing_edges: Mapping[str, tuple[WorkflowEdge, ...]],
) -> frozenset[str]:
    clean_node_id = str(node_id or "").strip()
    if not clean_node_id:
        return frozenset(node.node_id for node in template.nodes)
    node_ids = {node.node_id for node in template.nodes}
    if clean_node_id not in node_ids:
        raise ValueError(f"unknown workflow node_id: {clean_node_id}")
    selected: set[str] = set()
    queue: deque[str] = deque([clean_node_id])
    while queue:
        current = queue.popleft()
        if current in selected:
            continue
        selected.add(current)
        for edge in outgoing_edges.get(current, ()):
            queue.append(edge.target_node_id)
    return frozenset(selected)


def _seed_previous_node_outputs(
    root: Path,
    order: tuple[WorkflowNode, ...],
    rerun_node_ids: frozenset[str],
    outgoing_edges: Mapping[str, tuple[WorkflowEdge, ...]],
    node_status: dict[str, str],
    outputs_by_port: dict[tuple[str, str], tuple[Mapping[str, Any], ...]],
    summaries_by_node: dict[str, NodeRunSummary],
    remaining_dependencies: dict[str, int],
) -> None:
    for node in order:
        if node.node_id in rerun_node_ids:
            continue
        if not any(edge.target_node_id in rerun_node_ids for edge in outgoing_edges.get(node.node_id, ())):
            continue
        payload = _latest_ok_node_run_payload(root, node.node_id)
        if payload is None:
            raise ValueError(f"cannot rerun from selected node because upstream node has no ok run: {node.node_id}")
        outputs = tuple(item for item in payload.get("outputs", ()) if isinstance(item, Mapping))
        node_status[node.node_id] = "ok"
        summaries_by_node[node.node_id] = NodeRunSummary(
            node_id=node.node_id,
            status="ok",
            workdir=str(payload.get("workdir") or ""),
            outputs=outputs,
        )
        for port_id, port_outputs in _outputs_by_port(outputs).items():
            outputs_by_port[(node.node_id, port_id)] = port_outputs
        for edge in outgoing_edges.get(node.node_id, ()):
            remaining_dependencies[edge.target_node_id] -= 1


def _latest_ok_node_run_payload(root: Path, node_id: str) -> Mapping[str, Any] | None:
    runs_root = root / "nodes" / node_id / "runs"
    if not runs_root.is_dir():
        return None
    ok_runs: list[Mapping[str, Any]] = []
    for node_run_path in sorted(runs_root.glob("*/node_run.json")):
        payload = json.loads(node_run_path.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping) and payload.get("status") == "ok":
            ok_runs.append(payload)
    return ok_runs[-1] if ok_runs else None


def _runner_worker_count(
    order: tuple[WorkflowNode, ...],
    configured_max_workers: int | None,
) -> int:
    if configured_max_workers is not None:
        return max(1, configured_max_workers)
    return max(1, len(order))


def _outputs_by_port(
    outputs: tuple[Mapping[str, Any], ...],
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for output in outputs:
        grouped[str(output["port_id"])].append(output)
    return {port_id: tuple(items) for port_id, items in grouped.items()}


def _node_run_metadata(outputs: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "prompt_path": "",
        "stdout_path": "",
        "stderr_path": "",
        "trace_path": "",
        "session_log_path": "",
        "execution_manifest_path": "",
        "exit_code": 0,
    }
    for output in outputs:
        for field_name in (
            "prompt_path",
            "stdout_path",
            "stderr_path",
            "trace_path",
            "session_log_path",
            "execution_manifest_path",
        ):
            value = output.get(field_name)
            if isinstance(value, str) and value and not metadata[field_name]:
                metadata[field_name] = value
        exit_code = output.get("exit_code")
        if isinstance(exit_code, int):
            metadata["exit_code"] = exit_code
    return metadata


def _exception_metadata_path(exc: Exception, field_name: str, root: Path) -> str:
    value = getattr(exc, field_name, None)
    if value is None:
        return ""
    path = Path(value).expanduser().resolve(strict=False)
    try:
        return path.relative_to(root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def _exception_exit_code(exc: Exception) -> int | None:
    value = getattr(exc, "exit_code", None)
    return value if isinstance(value, int) else None


def _read_final_outputs(
    root: Path,
    outputs: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    manifest_outputs: list[Mapping[str, Any]] = []
    for output in outputs:
        if output.get("format_id") != "drawai.final_outputs.v1":
            continue
        manifest_path = _resolve_inside(root, output["path"])
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping) and isinstance(payload.get("outputs"), list):
            manifest_outputs.extend(
                item for item in payload["outputs"] if isinstance(item, Mapping)
            )
    return tuple(manifest_outputs)


def _output_port_for_payload(
    ports: Mapping[str, WorkflowPort],
    output: Mapping[str, Any],
    node: WorkflowNode,
    index: int,
) -> WorkflowPort:
    port_id = str(output.get("port_id") or "")
    if port_id:
        port = ports.get(port_id)
        if port is None:
            raise ValueError(f"node {node.node_id} output {index} uses unknown port {port_id}")
        return port
    if len(node.outputs) != 1:
        raise ValueError(f"node {node.node_id} output {index} must declare port_id")
    return node.outputs[0]


def _required_output_path(
    root: Path,
    output: Mapping[str, Any],
    node: WorkflowNode,
    index: int,
) -> Path:
    path_value = output.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"node {node.node_id} output {index} path is required")
    path = _resolve_inside(root, path_value)
    if not path.is_file():
        raise ValueError(f"node {node.node_id} output {index} file does not exist: {path}")
    return path


def _mirror_deliverable(root: Path, artifact: Mapping[str, Any]) -> str:
    source = _resolve_inside(root, artifact["path"])
    destination = _compatibility_destination(root, artifact, source)
    if destination is None:
        return ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return _run_relative(root, destination)


def _compatibility_destination(
    root: Path,
    artifact: Mapping[str, Any],
    source: Path,
) -> Path | None:
    artifact_type = str(artifact.get("type") or "")
    format_id = str(artifact.get("format_id") or "")
    if artifact_type == "semantic_svg" or format_id == "drawai.semantic_svg.v1":
        return root / "svg" / "semantic.svg"
    if artifact_type == "pptx" or format_id == "drawai.pptx.v1":
        return root / "exports" / "semantic.svg_to_ppt.pptx"
    return root / "outputs" / source.name


def _find_port(ports: tuple[WorkflowPort, ...], port_id: str) -> WorkflowPort:
    for port in ports:
        if port.port_id == port_id:
            return port
    raise ValueError(f"unknown workflow port: {port_id}")


def _single_output_port_id(node: WorkflowNode) -> str:
    if len(node.outputs) != 1:
        raise ValueError(f"output node {node.node_id} must declare one output port")
    return node.outputs[0].port_id


def _node_provider_id(node: WorkflowNode) -> str:
    value = node.config.get("provider_id")
    return str(value) if value is not None else ""


def _node_needs_resource(node: WorkflowNode) -> bool:
    return bool(node.config.get("resource") or node.config.get("provider_id"))


def _port_is_deliverable(port: WorkflowPort) -> bool:
    return "deliverable" in port.description.lower()


def _summary(
    record: NodeRunRecord,
    status: str,
    *,
    outputs: tuple[Mapping[str, Any], ...] = (),
    error: str = "",
) -> NodeRunSummary:
    return NodeRunSummary(
        node_id=record.node_id,
        status=status,
        workdir=_run_relative(record.root, record.workdir),
        outputs=outputs,
        error=error,
    )


def _resolve_inside(root: Path, path_value: object) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("workflow artifact path must be a non-empty string")
    path = Path(path_value)
    resolved = path.expanduser().resolve(strict=False) if path.is_absolute() else (root / path).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"workflow artifact path escapes run root: {path_value}") from exc
    return resolved


def _run_relative(root: Path, path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    return resolved.relative_to(root.resolve(strict=False)).as_posix()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
