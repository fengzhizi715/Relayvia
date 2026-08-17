"""Workflow Run lifecycle service.

Run creation binds an immutable Workflow Version, snapshots the Definition and
the Registry invocation metadata (no secrets), validates Run input, initializes
variables, and pre-creates one NodeRun per Graph Node. All state changes go
through the State Machine under a `FOR UPDATE` lock.
"""

import copy

from jsonschema import Draft7Validator, SchemaError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.agents.model import Agent
from app.domain.runs.events import RunEventType, record_event
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.runs.repository import get_run as repository_get_run
from app.domain.runs.repository import list_node_runs as repository_list_node_runs
from app.domain.runs.repository import list_runs as repository_list_runs
from app.domain.runs.schemas import NodeRunRead, WorkflowRunCreate, WorkflowRunRead, WorkflowRunSummary
from app.domain.services.model import Service, ServiceAction
from app.domain.workflows.graph import NodeType, WorkflowGraph, parse_workflow_graph
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.domain.workflows.validation_service import referenced_registry_ids
from app.infrastructure.database.base import utc_now
from app.runtime.context import RuntimeContext
from app.runtime.readiness.validator import check_run_readiness
from app.runtime.snapshot.builder import (
    SnapshotAgent,
    SnapshotService,
    SnapshotServiceAction,
    build_execution_snapshot,
)
from app.runtime.state_machine import (
    NodeRunStatus,
    WorkflowRunStatus,
    is_node_run_terminal,
    is_workflow_run_terminal,
    transition_node_run,
    transition_workflow_run,
)
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.validation.context import RegistryAgent, RegistryService, RegistryServiceAction, ValidationContext


def _get_workflow(db: Session, workflow_id: str) -> Workflow:
    workflow = db.scalar(select(Workflow).where(Workflow.id == workflow_id))
    if workflow is None:
        raise RelayviaError("WORKFLOW_NOT_FOUND", "Workflow not found", status_code=404)
    return workflow


def _resolve_version(db: Session, workflow: Workflow, payload: WorkflowRunCreate) -> WorkflowVersion:
    if payload.workflow_version_id:
        version = db.scalar(select(WorkflowVersion).where(WorkflowVersion.id == payload.workflow_version_id))
        if version is None or version.workflow_id != workflow.id:
            raise RelayviaError("WORKFLOW_VERSION_NOT_FOUND", "Workflow Version not found", status_code=404)
        return version
    if payload.version is not None:
        version = db.scalar(
            select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.version == payload.version)
        )
        if version is None:
            raise RelayviaError("WORKFLOW_VERSION_NOT_FOUND", "Workflow Version not found", status_code=404)
        return version
    if not workflow.current_version:
        raise RelayviaError(
            "WORKFLOW_HAS_NO_VERSION",
            "Workflow has no Version yet; create a Version before running",
            status_code=409,
        )
    version = db.scalar(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.version == workflow.current_version)
    )
    if version is None:
        raise RelayviaError("WORKFLOW_VERSION_NOT_FOUND", "Workflow Version not found", status_code=404)
    return version


def _load_registry(db: Session, graph: WorkflowGraph) -> tuple[dict[str, Agent], dict[str, Service], dict[str, ServiceAction]]:
    agent_ids, service_ids, action_ids = referenced_registry_ids(graph)
    agents: dict[str, Agent] = {}
    services: dict[str, Service] = {}
    actions: dict[str, ServiceAction] = {}
    if agent_ids:
        for agent in db.scalars(select(Agent).where(Agent.id.in_(agent_ids))):
            agents[agent.id] = agent
    if service_ids:
        for service in db.scalars(select(Service).where(Service.id.in_(service_ids))):
            services[service.id] = service
    if action_ids:
        for action in db.scalars(select(ServiceAction).where(ServiceAction.id.in_(action_ids))):
            actions[action.id] = action
    return agents, services, actions


def _registry_context(graph: WorkflowGraph, agents: dict[str, Agent], services: dict[str, Service], actions: dict[str, ServiceAction]) -> ValidationContext:
    return ValidationContext(
        graph=graph,
        agents={
            agent_id: RegistryAgent(
                id=agent.id,
                name=agent.name,
                enabled=agent.enabled,
                status=agent.status,
                timeout_seconds=agent.timeout_seconds,
                input_schema=agent.input_schema_json or {},
                output_schema=agent.output_schema_json or {},
            )
            for agent_id, agent in agents.items()
        },
        services={
            service_id: RegistryService(id=service.id, name=service.name, enabled=service.enabled, status=service.status)
            for service_id, service in services.items()
        },
        service_actions={
            action_id: RegistryServiceAction(
                id=action.id,
                service_id=action.service_id,
                name=action.name,
                enabled=action.enabled,
                timeout_seconds=action.timeout_seconds,
                query_schema=action.query_schema_json or {},
                path_schema=action.path_schema_json or {},
                input_schema=action.input_schema_json or {},
                output_schema=action.output_schema_json or {},
            )
            for action_id, action in actions.items()
        },
    )


def _build_execution_snapshot(agents: dict[str, Agent], services: dict[str, Service], actions: dict[str, ServiceAction]) -> dict:
    return build_execution_snapshot(
        agents=[
            SnapshotAgent(
                id=agent.id,
                name=agent.name,
                connector_type=agent.connector_type,
                endpoint=agent.endpoint,
                http_method=agent.http_method,
                headers=agent.headers_json or {},
                health_check_url=agent.health_check_url,
                timeout_seconds=agent.timeout_seconds,
                input_schema=agent.input_schema_json or {},
                output_schema=agent.output_schema_json or {},
                credential_id=agent.credential_id,
            )
            for agent in agents.values()
        ],
        services=[
            SnapshotService(
                id=service.id,
                name=service.name,
                base_url=service.base_url,
                health_check_url=service.health_check_url,
                credential_id=service.credential_id,
            )
            for service in services.values()
        ],
        service_actions=[
            SnapshotServiceAction(
                id=action.id,
                service_id=action.service_id,
                name=action.name,
                method=action.method,
                path=action.path,
                headers=action.headers_json or {},
                query_schema=action.query_schema_json or {},
                path_schema=action.path_schema_json or {},
                timeout_seconds=action.timeout_seconds,
                retry_policy=action.retry_policy_json or {},
                input_schema=action.input_schema_json or {},
                output_schema=action.output_schema_json or {},
            )
            for action in actions.values()
        ],
    )


def _validate_run_input(graph: WorkflowGraph, run_input: dict) -> None:
    entry = [node for node in graph.nodes if node.type == NodeType.DATA and node.subtype == "input"]
    if not entry:
        return
    schema = entry[0].config.get("schema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError:
        return
    errors = list(Draft7Validator(schema).iter_errors(run_input))
    if errors:
        raise RelayviaError(
            "INVALID_WORKFLOW_INPUT",
            "Workflow input does not match the Data Input schema",
            status_code=422,
            details={"errors": [error.message for error in errors]},
        )


def _initialize_variables(graph: WorkflowGraph) -> dict:
    return {name: variable.default for name, variable in graph.variables.items()}


def _create_node_runs(run_id: str, graph: WorkflowGraph, input_data: dict) -> list[NodeRun]:
    node_runs: list[NodeRun] = []
    for node in graph.nodes:
        is_input = node.type == NodeType.DATA and node.subtype == "input"
        node_runs.append(
            NodeRun(
                workflow_run_id=run_id,
                node_id=node.id,
                node_type=node.type.value,
                node_subtype=node.subtype,
                node_name_snapshot=node.name,
                status=NodeRunStatus.COMPLETED.value if is_input else NodeRunStatus.PENDING.value,
                output_json=dict(input_data) if is_input else None,
                attempt=0,
            )
        )
    return node_runs


def _to_node_read(node_run: NodeRun) -> NodeRunRead:
    return NodeRunRead(
        id=node_run.id,
        workflow_run_id=node_run.workflow_run_id,
        node_id=node_run.node_id,
        node_type=node_run.node_type,
        node_subtype=node_run.node_subtype,
        node_name_snapshot=node_run.node_name_snapshot,
        status=NodeRunStatus(node_run.status),
        input=node_run.input_json,
        output=node_run.output_json,
        error=node_run.error_json,
        execution_metadata=node_run.execution_metadata_json,
        artifacts=node_run.artifact_refs_json,
        attempt=node_run.attempt,
        waiting_reason=node_run.waiting_reason,
        waiting_metadata=node_run.waiting_metadata_json,
        started_at=node_run.started_at,
        finished_at=node_run.finished_at,
        created_at=node_run.created_at,
        updated_at=node_run.updated_at,
    )


def _workflow_name(db: Session, workflow_id: str) -> str | None:
    workflow = db.get(Workflow, workflow_id)
    return workflow.name if workflow else None


def _to_read(db: Session, run: WorkflowRun, node_runs: list[NodeRun] | None = None) -> WorkflowRunRead:
    node_runs = node_runs if node_runs is not None else repository_list_node_runs(db, run.id)
    return WorkflowRunRead(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=_workflow_name(db, run.workflow_id),
        workflow_version_id=run.workflow_version_id,
        version=run.version_number,
        status=WorkflowRunStatus(run.status),
        graph_schema_version=run.graph_schema_version,
        graph_snapshot=parse_workflow_graph(run.graph_snapshot_json),
        execution_snapshot=run.execution_snapshot_json,
        input=run.input_json,
        variables=run.variables_json,
        error=run.error_json,
        waiting_reason=run.waiting_reason,
        waiting_metadata=run.waiting_metadata_json,
        started_at=run.started_at,
        finished_at=run.finished_at,
        paused_at=run.paused_at,
        cancelled_at=run.cancelled_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
        node_runs=[_to_node_read(node_run) for node_run in node_runs],
    )


def create_run(db: Session, workflow_id: str, payload: WorkflowRunCreate) -> WorkflowRunRead:
    workflow = _get_workflow(db, workflow_id)
    version = _resolve_version(db, workflow, payload)
    graph = parse_workflow_graph(version.graph_json)

    agents, services, actions = _load_registry(db, graph)
    readiness = check_run_readiness(graph, _registry_context(graph, agents, services, actions))
    if not readiness.valid:
        raise RelayviaError(
            "RUN_READINESS_FAILED",
            "Referenced capabilities are not ready to run",
            status_code=409,
            details={"errors": readiness.errors, "warnings": readiness.warnings},
        )

    _validate_run_input(graph, payload.input)

    run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        version_number=version.version,
        status=WorkflowRunStatus.CREATED.value,
        graph_schema_version=version.graph_schema_version,
        graph_snapshot_json=copy.deepcopy(version.graph_json),
        execution_snapshot_json=_build_execution_snapshot(agents, services, actions),
        input_json=payload.input,
        variables_json=_initialize_variables(graph),
    )
    db.add(run)
    db.flush()
    node_runs = _create_node_runs(run.id, graph, payload.input)
    db.add_all(node_runs)
    db.commit()
    return _to_read(db, run, node_runs=node_runs)


def list_runs(db: Session, *, workflow_id: str | None = None, status: WorkflowRunStatus | None = None, limit: int = 50, offset: int = 0) -> list[WorkflowRunSummary]:
    runs = repository_list_runs(db, workflow_id=workflow_id, status=status, limit=limit, offset=offset)
    workflow_ids = {run.workflow_id for run in runs}
    names: dict[str, str] = {}
    if workflow_ids:
        for workflow in db.scalars(select(Workflow).where(Workflow.id.in_(workflow_ids))):
            names[workflow.id] = workflow.name
    return [
        WorkflowRunSummary(
            id=run.id,
            workflow_id=run.workflow_id,
            workflow_name=names.get(run.workflow_id),
            workflow_version_id=run.workflow_version_id,
            version=run.version_number,
            status=WorkflowRunStatus(run.status),
            started_at=run.started_at,
            finished_at=run.finished_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
        for run in runs
    ]


def get_run(db: Session, run_id: str) -> WorkflowRunRead:
    run = repository_get_run(db, run_id)
    if run is None:
        raise RelayviaError("WORKFLOW_RUN_NOT_FOUND", "Workflow Run not found", status_code=404)
    return _to_read(db, run)


def _get_locked(db: Session, run_id: str) -> WorkflowRun:
    run = repository_get_run(db, run_id, lock=True)
    if run is None:
        raise RelayviaError("WORKFLOW_RUN_NOT_FOUND", "Workflow Run not found", status_code=404)
    return run


def start_run(db: Session, run_id: str) -> WorkflowRunRead:
    run = _get_locked(db, run_id)
    transition_workflow_run(WorkflowRunStatus(run.status), WorkflowRunStatus.RUNNING)
    run.status = WorkflowRunStatus.RUNNING.value
    if run.started_at is None:
        run.started_at = utc_now()
    record_event(db, workflow_run_id=run.id, event_type=RunEventType.WORKFLOW_STARTED, message="Workflow started")
    db.commit()
    # Phase 7: submit ExecutionTasks for the initial Ready Nodes.
    WorkflowScheduler().schedule_ready_nodes(db, run.id)
    db.commit()
    db.refresh(run)
    return _to_read(db, run)


def pause_run(db: Session, run_id: str) -> WorkflowRunRead:
    run = _get_locked(db, run_id)
    transition_workflow_run(WorkflowRunStatus(run.status), WorkflowRunStatus.PAUSED)
    run.status = WorkflowRunStatus.PAUSED.value
    run.paused_at = utc_now()
    db.commit()
    db.refresh(run)
    return _to_read(db, run)


def resume_run(db: Session, run_id: str) -> WorkflowRunRead:
    run = _get_locked(db, run_id)
    transition_workflow_run(WorkflowRunStatus(run.status), WorkflowRunStatus.RUNNING)
    run.status = WorkflowRunStatus.RUNNING.value
    run.paused_at = None
    db.commit()
    # Reconcile rather than only schedule: a Wait timer may have become due
    # while the Run was paused, but PAUSED deliberately freezes its progress.
    WorkflowScheduler().reconcile_run(db, run.id)
    db.commit()
    db.refresh(run)
    return _to_read(db, run)


def cancel_run(db: Session, run_id: str) -> WorkflowRunRead:
    run = _get_locked(db, run_id)
    current = WorkflowRunStatus(run.status)
    if is_workflow_run_terminal(current):
        raise RelayviaError(
            "RUN_ALREADY_TERMINAL",
            "Workflow Run is already in a terminal state",
            status_code=409,
            details={"status": current.value},
        )
    transition_workflow_run(current, WorkflowRunStatus.CANCELLED)
    run.status = WorkflowRunStatus.CANCELLED.value
    run.cancelled_at = utc_now()
    run.finished_at = utc_now()
    record_event(db, workflow_run_id=run.id, event_type=RunEventType.WORKFLOW_CANCELLED, message="Workflow cancelled")

    for node_run in repository_list_node_runs(db, run_id):
        node_status = NodeRunStatus(node_run.status)
        if is_node_run_terminal(node_status):
            continue
        transition_node_run(node_status, NodeRunStatus.CANCELLED)
        node_run.status = NodeRunStatus.CANCELLED.value
        if node_run.finished_at is None:
            node_run.finished_at = utc_now()

    # Phase 7: cancel outstanding ExecutionTasks for this run.
    WorkflowScheduler().cancel_run_tasks(db, run_id)

    db.commit()
    db.refresh(run)
    return _to_read(db, run)


def list_node_runs(db: Session, run_id: str) -> list[NodeRunRead]:
    if repository_get_run(db, run_id) is None:
        raise RelayviaError("WORKFLOW_RUN_NOT_FOUND", "Workflow Run not found", status_code=404)
    return [_to_node_read(node_run) for node_run in repository_list_node_runs(db, run_id)]


def get_node_run(db: Session, run_id: str, node_run_id: str) -> NodeRunRead:
    node_run = db.scalar(
        select(NodeRun).where(NodeRun.id == node_run_id, NodeRun.workflow_run_id == run_id)
    )
    if node_run is None:
        raise RelayviaError("NODE_RUN_NOT_FOUND", "Node Run not found", status_code=404)
    return _to_node_read(node_run)


def runtime_context_for_run(db: Session, run: WorkflowRun) -> RuntimeContext:
    """Rebuild the RuntimeContext for a Run (node outputs are NOT included;
    resolvers read them from NodeRun.output_json)."""
    return RuntimeContext(input_data=run.input_json, variables=run.variables_json)


def _lock_node_run(db: Session, node_run_id: str) -> tuple[NodeRun, WorkflowRun]:
    node_run = db.scalar(select(NodeRun).where(NodeRun.id == node_run_id).with_for_update())
    if node_run is None:
        raise RelayviaError("NODE_RUN_NOT_FOUND", "Node Run not found", status_code=404)
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == node_run.workflow_run_id).with_for_update())
    if run is None:  # pragma: no cover - FK invariant
        raise RelayviaError("WORKFLOW_RUN_NOT_FOUND", "Workflow Run not found", status_code=404)
    return node_run, run


def _require_waiting(node_run: NodeRun) -> None:
    if NodeRunStatus(node_run.status) is not NodeRunStatus.WAITING:
        raise RelayviaError(
            "NODE_RUN_NOT_WAITING",
            "Node Run is not in a waiting state",
            status_code=409,
            details={"status": node_run.status},
        )


def _waiting_node(run: WorkflowRun, node_run: NodeRun, *, subtype: str, reason: str):
    if WorkflowRunStatus(run.status) is not WorkflowRunStatus.WAITING:
        raise RelayviaError(
            "WORKFLOW_RUN_NOT_WAITING",
            "Workflow Run must be waiting before this action can be applied",
            status_code=409,
            details={"status": run.status},
        )
    if node_run.node_type != "human" or node_run.node_subtype != subtype or node_run.waiting_reason != reason:
        raise RelayviaError(
            "NODE_RUN_ACTION_NOT_ALLOWED",
            "This action is not allowed for the waiting Node Run",
            status_code=409,
            details={"node_type": node_run.node_type, "node_subtype": node_run.node_subtype, "waiting_reason": node_run.waiting_reason},
        )
    graph = parse_workflow_graph(run.graph_snapshot_json)
    node = next((item for item in graph.nodes if item.id == node_run.node_id), None)
    if node is None:  # pragma: no cover - immutable snapshot invariant
        raise RelayviaError("NODE_SNAPSHOT_MISSING", "Node is missing from the Workflow Run snapshot", status_code=409)
    return node


def approve_node_run(db: Session, node_run_id: str) -> NodeRunRead:
    node_run, run = _lock_node_run(db, node_run_id)
    _require_waiting(node_run)
    _waiting_node(run, node_run, subtype="approval", reason="HUMAN_APPROVAL")
    transition_node_run(NodeRunStatus.WAITING, NodeRunStatus.COMPLETED)
    node_run.status = NodeRunStatus.COMPLETED.value
    node_run.output_json = {"approved": True}
    node_run.finished_at = utc_now()
    record_event(db, workflow_run_id=run.id, node_run_id=node_run.id, event_type=RunEventType.NODE_RESUMED, message="Approval approved", payload={"node_id": node_run.node_id, "action": "approve"})
    record_event(db, workflow_run_id=run.id, node_run_id=node_run.id, event_type=RunEventType.NODE_COMPLETED, message="Node completed after approval", payload={"node_id": node_run.node_id})
    db.commit()
    WorkflowScheduler().reconcile_run(db, run.id)
    db.commit()
    db.refresh(node_run)
    return _to_node_read(node_run)


def reject_node_run(db: Session, node_run_id: str) -> NodeRunRead:
    node_run, run = _lock_node_run(db, node_run_id)
    _require_waiting(node_run)
    node = _waiting_node(run, node_run, subtype="approval", reason="HUMAN_APPROVAL")
    if not bool(node.config.get("allow_reject", True)):
        raise RelayviaError("HUMAN_REJECTION_DISABLED", "This approval does not allow rejection", status_code=409)
    transition_node_run(NodeRunStatus.WAITING, NodeRunStatus.FAILED)
    node_run.status = NodeRunStatus.FAILED.value
    node_run.error_json = {"code": "REJECTED", "message": "Approval was rejected", "retryable": False, "details": {}}
    node_run.finished_at = utc_now()
    record_event(db, workflow_run_id=run.id, node_run_id=node_run.id, event_type=RunEventType.NODE_RESUMED, message="Approval rejected", payload={"node_id": node_run.node_id, "action": "reject"})
    record_event(db, workflow_run_id=run.id, node_run_id=node_run.id, event_type=RunEventType.NODE_FAILED, message="Node failed after rejection", payload={"node_id": node_run.node_id, "error_code": "REJECTED"})
    db.commit()
    WorkflowScheduler().reconcile_run(db, run.id)
    db.commit()
    db.refresh(node_run)
    return _to_node_read(node_run)


def submit_node_run(db: Session, node_run_id: str, input_data: dict) -> NodeRunRead:
    node_run, run = _lock_node_run(db, node_run_id)
    _require_waiting(node_run)
    node = _waiting_node(run, node_run, subtype="input", reason="HUMAN_INPUT")
    schema = node.config.get("form_schema")
    if isinstance(schema, dict) and schema:
        try:
            Draft7Validator.check_schema(schema)
        except SchemaError as exc:
            raise RelayviaError("INVALID_HUMAN_INPUT_SCHEMA", "Human Input schema is invalid", status_code=409) from exc
        errors = list(Draft7Validator(schema).iter_errors(input_data))
        if errors:
            raise RelayviaError(
                "INVALID_HUMAN_INPUT",
                "Submitted input does not match the Human Input schema",
                status_code=422,
                details={"errors": [error.message for error in errors]},
            )
    transition_node_run(NodeRunStatus.WAITING, NodeRunStatus.COMPLETED)
    node_run.status = NodeRunStatus.COMPLETED.value
    node_run.output_json = dict(input_data)
    node_run.finished_at = utc_now()
    record_event(db, workflow_run_id=run.id, node_run_id=node_run.id, event_type=RunEventType.NODE_RESUMED, message="Human input submitted", payload={"node_id": node_run.node_id, "action": "submit"})
    record_event(db, workflow_run_id=run.id, node_run_id=node_run.id, event_type=RunEventType.NODE_COMPLETED, message="Node completed after human input", payload={"node_id": node_run.node_id})
    db.commit()
    WorkflowScheduler().reconcile_run(db, run.id)
    db.commit()
    db.refresh(node_run)
    return _to_node_read(node_run)
