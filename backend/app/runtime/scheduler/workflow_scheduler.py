"""WorkflowScheduler: turns Ready Nodes into ExecutionTasks.

The Scheduler decides what should execute; it never executes. It is idempotent
(`UNIQUE(node_run_id)` + an existence pre-check) and refuses to schedule for
non-RUNNING WorkflowRuns. All methods are synchronous and operate inside the
caller's transaction.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.execution.models import ExecutionTask
from app.domain.execution.state_machine import ExecutionTaskStatus, is_execution_task_terminal, transition_execution_task
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.runs.repository import list_node_runs
from app.domain.workflows.graph import WorkflowGraph, parse_workflow_graph
from app.infrastructure.database.base import utc_now
from app.runtime.state_machine import (
    NodeRunStatus,
    WorkflowRunStatus,
    is_node_run_terminal,
    transition_node_run,
    transition_workflow_run,
)
from app.runtime.validation.graph_index import GraphIndex


def find_ready_nodes(graph: WorkflowGraph, node_runs: list[NodeRun]) -> list[str]:
    """Pure function: PENDING nodes whose control-flow predecessors are all
    COMPLETED. Used by the Scheduler today and by later phases unchanged."""
    index = GraphIndex.build(graph)
    status_by_id = {node_run.node_id: NodeRunStatus(node_run.status) for node_run in node_runs}
    completed = {node_id for node_id, status in status_by_id.items() if status is NodeRunStatus.COMPLETED}
    ready: list[str] = []
    for node in graph.nodes:
        if status_by_id.get(node.id) is not NodeRunStatus.PENDING:
            continue
        if all(edge.source in completed for edge in index.incoming_edges(node.id)):
            ready.append(node.id)
    return ready


def derive_workflow_state(graph: WorkflowGraph, node_runs: list[NodeRun]) -> WorkflowRunStatus:
    """Pure function: derive the WorkflowRun status from NodeRun states.

    - any FAILED node -> FAILED
    - all nodes terminal (and graph non-empty) -> COMPLETED
    - any WAITING node -> WAITING
    - otherwise -> RUNNING
    """
    statuses = [NodeRunStatus(node_run.status) for node_run in node_runs]
    if any(status is NodeRunStatus.FAILED for status in statuses):
        return WorkflowRunStatus.FAILED
    if statuses and all(is_node_run_terminal(status) for status in statuses):
        return WorkflowRunStatus.COMPLETED
    if any(status is NodeRunStatus.WAITING for status in statuses):
        return WorkflowRunStatus.WAITING
    return WorkflowRunStatus.RUNNING


class WorkflowScheduler:
    def __init__(self, *, default_priority: int = 0, default_max_attempts: int = 3, default_backoff_seconds: int = 5) -> None:
        self.default_priority = default_priority
        self.default_max_attempts = default_max_attempts
        self.default_backoff_seconds = default_backoff_seconds

    def schedule_ready_nodes(self, db: Session, run_id: str) -> list[str]:
        """Submit ExecutionTasks for every Ready (PENDING) node of a RUNNING
        run. Returns submitted node ids. Idempotent per node_run_id."""
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
        if run is None or WorkflowRunStatus(run.status) is not WorkflowRunStatus.RUNNING:
            return []

        graph = parse_workflow_graph(run.graph_snapshot_json)
        node_runs = list_node_runs(db, run_id)
        submitted: list[str] = []
        for node_id in find_ready_nodes(graph, node_runs):
            node_run = next((node_run for node_run in node_runs if node_run.node_id == node_id), None)
            if node_run is None:
                continue
            existing = db.scalar(select(ExecutionTask).where(ExecutionTask.node_run_id == node_run.id))
            if existing is not None:
                continue
            transition_node_run(NodeRunStatus(node_run.status), NodeRunStatus.QUEUED)
            node_run.status = NodeRunStatus.QUEUED.value
            db.add(
                ExecutionTask(
                    workflow_run_id=run_id,
                    node_run_id=node_run.id,
                    task_type="node_execution",
                    status=ExecutionTaskStatus.PENDING.value,
                    payload_json={"workflow_run_id": run_id, "node_run_id": node_run.id, "node_id": node_id},
                    priority=self.default_priority,
                    attempt=0,
                    max_attempts=self.default_max_attempts,
                    available_at=utc_now(),
                    execution_key=f"{run_id}:{node_run.id}",
                )
            )
            submitted.append(node_id)
        return submitted

    def reconcile_run(self, db: Session, run_id: str) -> WorkflowRunStatus | None:
        """Idempotent reconciliation: fill missed scheduling, cancel leftover
        work for cancelled runs, and derive/persist the WorkflowRun status."""
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
        if run is None:
            return None
        current = WorkflowRunStatus(run.status)

        if current is WorkflowRunStatus.CANCELLED:
            self.cancel_run_tasks(db, run_id)
            return current
        if current is not WorkflowRunStatus.RUNNING:
            return current

        self.schedule_ready_nodes(db, run_id)

        graph = parse_workflow_graph(run.graph_snapshot_json)
        node_runs = list_node_runs(db, run_id)
        derived = derive_workflow_state(graph, node_runs)
        if derived is not current:
            transition_workflow_run(current, derived)
            run.status = derived.value
            if derived in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED):
                run.finished_at = utc_now()
        return derived

    def cancel_run_tasks(self, db: Session, run_id: str) -> None:
        """Cancel every non-terminal ExecutionTask and its NodeRun."""
        tasks = db.scalars(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run_id).with_for_update()).all()
        for task in tasks:
            status = ExecutionTaskStatus(task.status)
            if is_execution_task_terminal(status):
                continue
            transition_execution_task(status, ExecutionTaskStatus.CANCELLED)
            task.status = ExecutionTaskStatus.CANCELLED.value
            task.finished_at = utc_now()
            node_run = db.get(NodeRun, task.node_run_id)
            if node_run is not None and not is_node_run_terminal(NodeRunStatus(node_run.status)):
                transition_node_run(NodeRunStatus(node_run.status), NodeRunStatus.CANCELLED)
                node_run.status = NodeRunStatus.CANCELLED.value
                node_run.finished_at = utc_now()
        # Cancel PENDING node runs that never received a task.
        for node_run in list_node_runs(db, run_id):
            status = NodeRunStatus(node_run.status)
            if status is NodeRunStatus.PENDING and not is_node_run_terminal(status):
                transition_node_run(status, NodeRunStatus.CANCELLED)
                node_run.status = NodeRunStatus.CANCELLED.value
                node_run.finished_at = utc_now()
