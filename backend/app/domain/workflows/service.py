"""Workflow CRUD, Draft persistence, and immutable Version creation."""

import copy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.agents.model import Agent
from app.domain.services.model import Service, ServiceAction
from app.domain.workflows.graph import GRAPH_SCHEMA_VERSION, WorkflowGraph, empty_workflow_graph, parse_workflow_graph
from app.domain.workflows.model import Workflow, WorkflowStatus, WorkflowVersion
from app.domain.workflows.schemas import (
    GraphWarning,
    WorkflowCreate,
    WorkflowGraphRead,
    WorkflowRead,
    WorkflowUpdate,
    WorkflowVersionRead,
)


def _get_workflow(db: Session, workflow_id: str, *, lock: bool = False) -> Workflow:
    query = select(Workflow).where(Workflow.id == workflow_id)
    if lock:
        query = query.with_for_update()
    workflow = db.scalar(query)
    if workflow is None:
        raise RelayviaError("WORKFLOW_NOT_FOUND", "Workflow not found", status_code=404)
    return workflow


def _ensure_name_available(db: Session, name: str, current_id: str | None = None) -> None:
    query = select(Workflow).where(func.lower(Workflow.name) == name.lower())
    if current_id:
        query = query.where(Workflow.id != current_id)
    if db.scalar(query) is not None:
        raise RelayviaError("DUPLICATE_NAME", "Workflow name is already in use", details={"name": name})


def _graph_json(graph: WorkflowGraph) -> dict[str, Any]:
    return copy.deepcopy(graph.model_dump(mode="json"))


def _graph_from_json(raw: Any) -> WorkflowGraph:
    return parse_workflow_graph(copy.deepcopy(raw))


def _validate_registry_references(db: Session, graph: WorkflowGraph) -> list[GraphWarning]:
    warnings: list[GraphWarning] = []
    for node in graph.nodes:
        if node.type.value == "agent":
            agent_id = node.config.get("agent_id")
            agent = db.get(Agent, agent_id)
            if agent is None:
                raise RelayviaError(
                    "INVALID_AGENT_REFERENCE",
                    "Agent Node references an Agent that does not exist",
                    details={"node_id": node.id, "agent_id": agent_id},
                )
            if not agent.enabled:
                warnings.append(GraphWarning(code="DISABLED_AGENT_REFERENCE", message="Referenced Agent is disabled", details={"node_id": node.id, "agent_id": agent_id}))
        elif node.type.value == "service":
            service_id = node.config.get("service_id")
            action_id = node.config.get("service_action_id")
            service = db.get(Service, service_id)
            if service is None:
                raise RelayviaError(
                    "INVALID_SERVICE_REFERENCE",
                    "Service Node references a Service that does not exist",
                    details={"node_id": node.id, "service_id": service_id},
                )
            action = db.get(ServiceAction, action_id)
            if action is None:
                raise RelayviaError(
                    "INVALID_SERVICE_ACTION_REFERENCE",
                    "Service Node references a Service Action that does not exist",
                    details={"node_id": node.id, "service_action_id": action_id},
                )
            if action.service_id != service_id:
                raise RelayviaError(
                    "INVALID_SERVICE_ACTION_REFERENCE",
                    "Service Action does not belong to the referenced Service",
                    details={"node_id": node.id, "service_id": service_id, "service_action_id": action_id},
                )
            if not service.enabled:
                warnings.append(GraphWarning(code="DISABLED_SERVICE_REFERENCE", message="Referenced Service is disabled", details={"node_id": node.id, "service_id": service_id}))
            if not action.enabled:
                warnings.append(GraphWarning(code="DISABLED_SERVICE_ACTION_REFERENCE", message="Referenced Service Action is disabled", details={"node_id": node.id, "service_action_id": action_id}))
    return warnings


def _to_read(workflow: Workflow) -> WorkflowRead:
    return WorkflowRead(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        status=WorkflowStatus(workflow.status),
        draft_graph=_graph_from_json(workflow.draft_graph_json),
        graph_schema_version=workflow.graph_schema_version,
        current_version=workflow.current_version,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


def _to_version_read(version: WorkflowVersion) -> WorkflowVersionRead:
    return WorkflowVersionRead(
        id=version.id,
        workflow_id=version.workflow_id,
        version=version.version,
        graph_schema_version=version.graph_schema_version,
        graph=_graph_from_json(version.graph_json),
        change_note=version.change_note,
        created_at=version.created_at,
    )


def list_workflows(db: Session, *, include_archived: bool = False) -> list[WorkflowRead]:
    query = select(Workflow).order_by(Workflow.updated_at.desc(), Workflow.name)
    if not include_archived:
        query = query.where(Workflow.status != WorkflowStatus.ARCHIVED.value)
    return [_to_read(workflow) for workflow in db.scalars(query).all()]


def get_workflow(db: Session, workflow_id: str) -> WorkflowRead:
    return _to_read(_get_workflow(db, workflow_id))


def create_workflow(db: Session, payload: WorkflowCreate) -> WorkflowRead:
    _ensure_name_available(db, payload.name)
    graph = parse_workflow_graph(payload.graph) if payload.graph is not None else empty_workflow_graph()
    _validate_registry_references(db, graph)
    workflow = Workflow(
        name=payload.name,
        description=payload.description,
        status=WorkflowStatus.DRAFT.value,
        draft_graph_json=_graph_json(graph),
        graph_schema_version=GRAPH_SCHEMA_VERSION,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return _to_read(workflow)


def update_workflow(db: Session, workflow_id: str, payload: WorkflowUpdate) -> WorkflowRead:
    workflow = _get_workflow(db, workflow_id)
    changes = payload.model_dump(exclude_unset=True)
    if payload.name is not None:
        _ensure_name_available(db, payload.name, current_id=workflow.id)
        workflow.name = payload.name
    if "description" in changes:
        workflow.description = payload.description
    if payload.status is not None:
        workflow.status = payload.status.value
    db.commit()
    db.refresh(workflow)
    return _to_read(workflow)


def delete_workflow(db: Session, workflow_id: str) -> None:
    workflow = _get_workflow(db, workflow_id)
    version_count = db.scalar(select(func.count()).select_from(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id)) or 0
    if version_count:
        workflow.status = WorkflowStatus.ARCHIVED.value
        db.commit()
        return
    db.delete(workflow)
    db.commit()


def get_draft_graph(db: Session, workflow_id: str) -> WorkflowGraphRead:
    workflow = _get_workflow(db, workflow_id)
    graph = _graph_from_json(workflow.draft_graph_json)
    warnings = _validate_registry_references(db, graph)
    return WorkflowGraphRead(workflow_id=workflow.id, graph=graph, warnings=warnings, updated_at=workflow.updated_at)


def update_draft_graph(db: Session, workflow_id: str, raw_graph: Any) -> WorkflowGraphRead:
    workflow = _get_workflow(db, workflow_id)
    graph = parse_workflow_graph(raw_graph)
    warnings = _validate_registry_references(db, graph)
    workflow.draft_graph_json = _graph_json(graph)
    workflow.graph_schema_version = GRAPH_SCHEMA_VERSION
    if workflow.status == WorkflowStatus.ARCHIVED.value:
        workflow.status = WorkflowStatus.DRAFT.value
    db.commit()
    db.refresh(workflow)
    return WorkflowGraphRead(workflow_id=workflow.id, graph=graph, warnings=warnings, updated_at=workflow.updated_at)


def create_version(db: Session, workflow_id: str, change_note: str | None = None) -> WorkflowVersionRead:
    workflow = _get_workflow(db, workflow_id, lock=True)
    graph = _graph_from_json(workflow.draft_graph_json)
    _validate_registry_references(db, graph)
    current_max = db.scalar(select(func.max(WorkflowVersion.version)).where(WorkflowVersion.workflow_id == workflow.id)) or 0
    version_number = max(current_max, workflow.current_version or 0) + 1
    snapshot = _graph_json(graph)
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=version_number,
        graph_schema_version=GRAPH_SCHEMA_VERSION,
        graph_json=snapshot,
        change_note=change_note,
        created_at=datetime.now(timezone.utc),
    )
    workflow.current_version = version_number
    workflow.status = WorkflowStatus.ACTIVE.value
    db.add(version)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise RelayviaError(
            "VERSION_CONFLICT",
            "A Workflow Version was created concurrently; retry the request",
            status_code=409,
        ) from exc
    db.refresh(version)
    return _to_version_read(version)


def list_versions(db: Session, workflow_id: str) -> list[WorkflowVersionRead]:
    _get_workflow(db, workflow_id)
    versions = db.scalars(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id).order_by(WorkflowVersion.version.desc())
    ).all()
    return [_to_version_read(version) for version in versions]


def get_version(db: Session, workflow_id: str, version_number: int) -> WorkflowVersionRead:
    _get_workflow(db, workflow_id)
    version = db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id, WorkflowVersion.version == version_number))
    if version is None:
        raise RelayviaError("WORKFLOW_VERSION_NOT_FOUND", "Workflow Version not found", status_code=404)
    return _to_version_read(version)

