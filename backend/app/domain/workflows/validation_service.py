"""DB-backed helpers that run the Validation Engine.

The engine itself stays pure; this module is the only place that maps ORM
registry rows into the engine's snapshot context, using batched queries to
avoid N+1 lookups.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.agents.model import Agent
from app.domain.services.model import Service, ServiceAction
from app.domain.workflows.graph import NodeType, WorkflowGraph, parse_workflow_graph
from app.domain.workflows.model import Workflow
from app.runtime.validation import (
    RegistryAgent,
    RegistryService,
    RegistryServiceAction,
    ValidationContext,
    ValidationResult,
    validate_graph,
)


def _referenced_ids(graph: WorkflowGraph) -> tuple[set[str], set[str], set[str]]:
    agent_ids: set[str] = set()
    service_ids: set[str] = set()
    action_ids: set[str] = set()
    for node in graph.nodes:
        if node.type is NodeType.AGENT:
            agent_id = node.config.get("agent_id")
            if agent_id:
                agent_ids.add(agent_id)
        elif node.type is NodeType.SERVICE:
            service_id = node.config.get("service_id")
            action_id = node.config.get("service_action_id")
            if service_id:
                service_ids.add(service_id)
            if action_id:
                action_ids.add(action_id)
    return agent_ids, service_ids, action_ids


referenced_registry_ids = _referenced_ids


def build_validation_context(db: Session, graph: WorkflowGraph) -> ValidationContext:
    """Batch-load referenced Registry rows into the engine's snapshot context."""
    agent_ids, service_ids, action_ids = _referenced_ids(graph)

    agents: dict[str, RegistryAgent] = {}
    services: dict[str, RegistryService] = {}
    actions: dict[str, RegistryServiceAction] = {}

    if agent_ids:
        for agent in db.scalars(select(Agent).where(Agent.id.in_(agent_ids))):
            agents[agent.id] = RegistryAgent(
                id=agent.id,
                name=agent.name,
                enabled=agent.enabled,
                connector_type=agent.connector_type,
                status=agent.status,
                timeout_seconds=agent.timeout_seconds,
                input_schema=agent.input_schema_json or {},
                output_schema=agent.output_schema_json or {},
            )

    if service_ids:
        for service in db.scalars(select(Service).where(Service.id.in_(service_ids))):
            services[service.id] = RegistryService(
                id=service.id,
                name=service.name,
                enabled=service.enabled,
                status=service.status,
            )

    if action_ids:
        for action in db.scalars(select(ServiceAction).where(ServiceAction.id.in_(action_ids))):
            actions[action.id] = RegistryServiceAction(
                id=action.id,
                service_id=action.service_id,
                name=action.name,
                enabled=action.enabled,
                timeout_seconds=action.timeout_seconds,
                input_schema=action.input_schema_json or {},
                output_schema=action.output_schema_json or {},
            )

    return ValidationContext(graph=graph, agents=agents, services=services, service_actions=actions)


def validate_graph_with_context(db: Session, graph: WorkflowGraph) -> ValidationResult:
    context = build_validation_context(db, graph)
    return validate_graph(graph, context)


def validate_draft_graph(db: Session, workflow_id: str, raw_graph: object | None = None) -> ValidationResult:
    """Validate the current Draft, or a supplied (unsaved) Graph."""
    if raw_graph is None:
        workflow = db.scalar(select(Workflow).where(Workflow.id == workflow_id))
        if workflow is None:
            raise RelayviaError("WORKFLOW_NOT_FOUND", "Workflow not found", status_code=404)
        graph = parse_workflow_graph(workflow.draft_graph_json)
    else:
        graph = parse_workflow_graph(raw_graph)
    return validate_graph_with_context(db, graph)
