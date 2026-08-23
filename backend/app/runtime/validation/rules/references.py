"""Pass 3 - Registry reference validation (agents / services / actions)."""

from app.domain.workflows.graph import NodeType, WorkflowGraph

from ..result import ValidationIssue
from ..codes import ValidationCode
from ..context import ValidationContext
from ..graph_index import GraphIndex


def validate_references(graph: WorkflowGraph, index: GraphIndex, context: ValidationContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for node in graph.nodes:
        if node.type == NodeType.AGENT:
            _validate_agent(node, context, issues)
        elif node.type == NodeType.SERVICE:
            _validate_service(node, context, issues)

    return issues


def _validate_agent(node, context: ValidationContext, issues: list[ValidationIssue]) -> None:
    agent_id = node.config.get("agent_id")
    if not agent_id:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_AGENT_REFERENCE,
                severity="error",
                message="Agent node does not reference an existing agent",
                node_id=node.id,
                field="config.agent_id",
            )
        )
        return
    agent = context.agents.get(agent_id)
    if agent is None:
        issues.append(
            ValidationIssue(
                code=ValidationCode.AGENT_NOT_FOUND,
                severity="error",
                message=f"Agent {agent_id!r} is not registered",
                node_id=node.id,
                field="config.agent_id",
            )
        )
        return
    if not agent.enabled:
        issues.append(
            ValidationIssue(
                code=ValidationCode.AGENT_DISABLED,
                severity="error",
                message=f"Agent {agent.name!r} is disabled",
                node_id=node.id,
                field="config.agent_id",
            )
        )
    if agent.connector_type not in {"http", "codex"}:
        issues.append(
            ValidationIssue(
                code=ValidationCode.UNSUPPORTED_AGENT_CONNECTOR,
                severity="error",
                message=(
                    f"Agent connector {agent.connector_type!r} cannot be published because no Execution Unit is installed"
                ),
                node_id=node.id,
                field="config.agent_id",
                details={"connector_type": agent.connector_type, "supported": ["http", "codex"]},
            )
        )
    elif agent.status == "unhealthy":
        issues.append(
            ValidationIssue(
                code=ValidationCode.AGENT_UNHEALTHY,
                severity="warning",
                message=f"Agent {agent.name!r} is currently unhealthy",
                node_id=node.id,
                field="config.agent_id",
            )
        )


def _validate_service(node, context: ValidationContext, issues: list[ValidationIssue]) -> None:
    service_id = node.config.get("service_id")
    action_id = node.config.get("service_action_id")

    if not service_id:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_SERVICE_REFERENCE,
                severity="error",
                message="Service node does not reference a service",
                node_id=node.id,
                field="config.service_id",
            )
        )
    else:
        service = context.services.get(service_id)
        if service is None:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.SERVICE_NOT_FOUND,
                    severity="error",
                    message=f"Service {service_id!r} is not registered",
                    node_id=node.id,
                    field="config.service_id",
                )
            )
        elif not service.enabled:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.SERVICE_DISABLED,
                    severity="error",
                    message=f"Service {service.name!r} is disabled",
                    node_id=node.id,
                    field="config.service_id",
                )
            )
        elif service.status == "unhealthy":
            issues.append(
                ValidationIssue(
                    code=ValidationCode.SERVICE_UNHEALTHY,
                    severity="warning",
                    message=f"Service {service.name!r} is currently unhealthy",
                    node_id=node.id,
                    field="config.service_id",
                )
            )

    if not action_id:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_SERVICE_ACTION_REFERENCE,
                severity="error",
                message="Service node does not reference a service action",
                node_id=node.id,
                field="config.service_action_id",
            )
        )
        return

    action = context.service_actions.get(action_id)
    if action is None:
        issues.append(
            ValidationIssue(
                code=ValidationCode.SERVICE_ACTION_NOT_FOUND,
                severity="error",
                message=f"Service action {action_id!r} is not registered",
                node_id=node.id,
                field="config.service_action_id",
            )
        )
        return
    if service_id and action.service_id != service_id:
        issues.append(
            ValidationIssue(
                code=ValidationCode.SERVICE_ACTION_MISMATCH,
                severity="error",
                message="Service action does not belong to the referenced service",
                node_id=node.id,
                field="config.service_action_id",
            )
        )
    elif not action.enabled:
        issues.append(
            ValidationIssue(
                code=ValidationCode.SERVICE_ACTION_DISABLED,
                severity="error",
                message=f"Service action {action.name!r} is disabled",
                node_id=node.id,
                field="config.service_action_id",
            )
        )
