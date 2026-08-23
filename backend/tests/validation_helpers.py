"""Shared builders for Validation Engine tests.

`model_construct` bypasses Pydantic validators so rules can be exercised
directly (including configurations the Contract layer would already reject).
"""

from app.domain.workflows.graph import (
    Position,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
)
from app.runtime.validation import (
    RegistryAgent,
    RegistryService,
    RegistryServiceAction,
    ValidationContext,
    ValidationResult,
    validate_graph,
)


def raw_node(
    nid: str,
    ntype: str,
    subtype: str,
    *,
    name: str | None = None,
    config: dict | None = None,
    input_mapping: dict | None = None,
    position: tuple[float, float] = (0, 0),
) -> WorkflowNode:
    return WorkflowNode.model_construct(
        id=nid,
        type=ntype,
        subtype=subtype,
        name=name or nid,
        position=Position(x=position[0], y=position[1]),
        config=config or {},
        input_mapping=input_mapping or {},
        metadata={},
    )


def raw_edge(
    eid: str,
    source: str,
    target: str,
    *,
    source_handle: str | None = None,
    target_handle: str | None = None,
    label: str | None = None,
) -> WorkflowEdge:
    return WorkflowEdge.model_construct(
        id=eid,
        source=source,
        target=target,
        source_handle=source_handle,
        target_handle=target_handle,
        label=label,
        condition=None,
        metadata={},
    )


def raw_graph(nodes: list[WorkflowNode], edges: list[WorkflowEdge], variables: dict | None = None) -> WorkflowGraph:
    return WorkflowGraph.model_construct(
        schema_version="1.0",
        nodes=nodes,
        edges=edges,
        variables=variables or {},
        metadata={},
    )


def input_node(nid: str = "input", schema: dict | None = None) -> WorkflowNode:
    return raw_node(nid, "data", "input", config={"schema": schema or {"type": "object", "properties": {}}})


def output_node(nid: str = "output", output_mapping: dict | None = None) -> WorkflowNode:
    return raw_node(nid, "data", "output", config={"output_mapping": output_mapping or {}})


def agent_node(nid: str, agent_id: str = "agent-1", input_mapping: dict | None = None, name: str | None = None) -> WorkflowNode:
    return raw_node(
        nid,
        "agent",
        "agent",
        name=name,
        config={"agent_id": agent_id, "task_template": "", "timeout_seconds": 600, "retry": {"max_retries": 0}},
        input_mapping=input_mapping,
    )


def agent(agent_id: str = "agent-1", *, enabled: bool = True, status: str = "unknown", connector_type: str = "http", input_schema: dict | None = None, output_schema: dict | None = None) -> RegistryAgent:
    return RegistryAgent(
        id=agent_id,
        name=f"Agent {agent_id}",
        enabled=enabled,
        connector_type=connector_type,
        status=status,
        timeout_seconds=600,
        input_schema=input_schema or {},
        output_schema=output_schema or {},
    )


def service_node(nid: str, service_id: str = "service-1", action_id: str = "action-1", input_mapping: dict | None = None) -> WorkflowNode:
    return raw_node(
        nid,
        "service",
        "http",
        config={"service_id": service_id, "service_action_id": action_id, "timeout_seconds": 60, "retry": {"max_retries": 0}},
        input_mapping=input_mapping,
    )


def service(service_id: str = "service-1", *, enabled: bool = True, status: str = "unknown") -> RegistryService:
    return RegistryService(id=service_id, name=f"Service {service_id}", enabled=enabled, status=status)


def action(action_id: str = "action-1", *, service_id: str = "service-1", enabled: bool = True, input_schema: dict | None = None, output_schema: dict | None = None) -> RegistryServiceAction:
    return RegistryServiceAction(
        id=action_id,
        service_id=service_id,
        name=f"Action {action_id}",
        enabled=enabled,
        timeout_seconds=60,
        input_schema=input_schema or {},
        output_schema=output_schema or {},
    )


def run(
    nodes: list[WorkflowNode],
    edges: list[WorkflowEdge],
    *,
    agents: dict | None = None,
    services: dict | None = None,
    actions: dict | None = None,
    variables: dict | None = None,
) -> ValidationResult:
    graph = raw_graph(nodes, edges, variables)
    context = ValidationContext(graph=graph, agents=agents or {}, services=services or {}, service_actions=actions or {})
    return validate_graph(graph, context)


def codes_of(result: ValidationResult, severity: str | None = None) -> set[str]:
    issues = result.errors if severity == "error" else result.warnings if severity == "warning" else [*result.errors, *result.warnings]
    return {issue.code for issue in issues}
