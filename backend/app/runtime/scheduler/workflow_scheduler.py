"""WorkflowScheduler: turns Ready Nodes into ExecutionTasks.

The Scheduler decides what should execute; it never executes. It is idempotent
(`UNIQUE(node_run_id)` + an existence pre-check) and refuses to schedule for
non-RUNNING WorkflowRuns. All methods are synchronous and operate inside the
caller's transaction.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.execution.models import ExecutionTask
from app.domain.execution.state_machine import ExecutionTaskStatus, is_execution_task_terminal, transition_execution_task
from app.domain.runs.events import RunEventType, record_event
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.runs.repository import list_node_runs
from app.domain.workflows.graph import WorkflowGraph, parse_workflow_graph
from app.infrastructure.database.base import utc_now
from app.runtime.context import ContextResolver, UnresolvedContextReference
from app.runtime.state_machine import (
    NodeRunStatus,
    WorkflowRunStatus,
    is_node_run_terminal,
    transition_node_run,
    transition_workflow_run,
)
from app.runtime.validation.graph_index import GraphIndex


def find_ready_nodes(graph: WorkflowGraph, node_runs: list[NodeRun]) -> list[str]:
    """Return PENDING nodes whose *active* control-flow inputs completed.

    A Condition activates exactly one output handle.  Inactive Condition edges
    and descendants already marked SKIPPED do not participate in a join. This
    permits true/false branches to converge without accidentally waiting for,
    or executing, the unselected path.
    """
    index = GraphIndex.build(graph)
    status_by_id = {node_run.node_id: NodeRunStatus(node_run.status) for node_run in node_runs}
    runs_by_node_id = {node_run.node_id: node_run for node_run in node_runs}
    ready: list[str] = []
    for node in graph.nodes:
        if status_by_id.get(node.id) is not NodeRunStatus.PENDING:
            continue
        active_edges = [
            edge for edge in index.incoming_edges(node.id) if _edge_is_active(edge, index, status_by_id, runs_by_node_id)
        ]
        if active_edges and all(status_by_id.get(edge.source) is NodeRunStatus.COMPLETED for edge in active_edges):
            ready.append(node.id)
    return ready


def _edge_is_active(edge, index: GraphIndex, status_by_id: dict[str, NodeRunStatus], runs_by_node_id: dict[str, NodeRun]) -> bool:
    source_status = status_by_id.get(edge.source)
    if source_status is NodeRunStatus.SKIPPED:
        return False
    source_node = index.node(edge.source)
    if source_node is None or source_node.type.value != "logic" or source_node.subtype != "condition":
        return True
    if source_status is not NodeRunStatus.COMPLETED:
        return True
    output = runs_by_node_id[edge.source].output_json
    selected = output.get("selected_branch") if isinstance(output, dict) else None
    return selected not in {"true", "false"} or edge.source_handle == selected


def mark_unreachable_condition_nodes(graph: WorkflowGraph, node_runs: list[NodeRun]) -> list[str]:
    """Mark the unselected Condition path (including descendants) as SKIPPED.

    The fixed-point loop also handles a false branch that later converges into
    a shared output: once the selected input is active, that output remains
    eligible rather than being skipped.
    """
    index = GraphIndex.build(graph)
    skipped: list[str] = []
    changed = True
    while changed:
        changed = False
        status_by_id = {node_run.node_id: NodeRunStatus(node_run.status) for node_run in node_runs}
        runs_by_node_id = {node_run.node_id: node_run for node_run in node_runs}
        for node in graph.nodes:
            node_run = runs_by_node_id.get(node.id)
            incoming = index.incoming_edges(node.id)
            if node_run is None or NodeRunStatus(node_run.status) is not NodeRunStatus.PENDING or not incoming:
                continue
            if any(_edge_is_active(edge, index, status_by_id, runs_by_node_id) for edge in incoming):
                continue
            transition_node_run(NodeRunStatus.PENDING, NodeRunStatus.SKIPPED)
            node_run.status = NodeRunStatus.SKIPPED.value
            node_run.finished_at = utc_now()
            skipped.append(node.id)
            changed = True
    return skipped


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
        nodes_by_id = {node.id: node for node in graph.nodes}
        node_runs = list_node_runs(db, run_id)
        before_pending = {node_run.node_id for node_run in node_runs if NodeRunStatus(node_run.status) is NodeRunStatus.PENDING}
        mark_unreachable_condition_nodes(graph, node_runs)
        for node_run in node_runs:
            if node_run.node_id in before_pending and NodeRunStatus(node_run.status) is NodeRunStatus.SKIPPED:
                record_event(
                    db,
                    workflow_run_id=run_id,
                    node_run_id=node_run.id,
                    event_type=RunEventType.NODE_SKIPPED,
                    message=f"Node {node_run.node_id} skipped (inactive branch)",
                    payload={"node_id": node_run.node_id},
                )
        submitted: list[str] = []
        for node_id in find_ready_nodes(graph, node_runs):
            node_run = next((node_run for node_run in node_runs if node_run.node_id == node_id), None)
            if node_run is None:
                continue
            node = nodes_by_id.get(node_id)
            if node is None:
                continue
            existing = db.scalar(select(ExecutionTask).where(ExecutionTask.node_run_id == node_run.id))
            if existing is not None:
                continue
            transition_node_run(NodeRunStatus(node_run.status), NodeRunStatus.QUEUED)
            node_run.status = NodeRunStatus.QUEUED.value
            record_event(
                db,
                workflow_run_id=run_id,
                node_run_id=node_run.id,
                event_type=RunEventType.NODE_QUEUED,
                message=f"Node {node_id} queued",
                payload={"node_id": node_id, "node_type": node.type.value},
            )
            max_attempts, retry_backoff_seconds = _retry_settings_for_node(
                run,
                node.model_dump(mode="json"),
                default_backoff_seconds=self.default_backoff_seconds,
            )
            payload: dict = {
                "workflow_run_id": run_id,
                "node_run_id": node_run.id,
                "node_id": node_id,
                "retry_backoff_seconds": retry_backoff_seconds,
            }
            required_capability: str | None = None
            target_runner_id: str | None = None
            if node.type.value == "tool":
                # Tool nodes execute on a Runner. Backend resolves the config
                # (Context) here so the Runner never needs the Graph/Context.
                tool_config = _resolve_tool_config(run, node_runs, node)
                if tool_config is None:
                    continue
                payload["config"] = tool_config
                payload["execution_type"] = "shell"
                required_capability = "shell"
                target_runner_id = tool_config.pop("runner_id", None)
                _attach_workspace(db, run_id, node_run, node_id, node, payload, runner_id=target_runner_id)
            elif node.type.value == "agent":
                coding = _coding_agent_payload(run, node_runs, node)
                if coding is not None:
                    payload["config"] = coding["config"]
                    payload["execution_type"] = "coding_agent"
                    required_capability = coding["capability"]
                    target_runner_id = coding["runner_id"]
                    _attach_workspace(db, run_id, node_run, node_id, node, payload, runner_id=target_runner_id)

            db.add(
                ExecutionTask(
                    workflow_run_id=run_id,
                    node_run_id=node_run.id,
                    task_type="node_execution",
                    status=ExecutionTaskStatus.PENDING.value,
                    payload_json=payload,
                    priority=self.default_priority,
                    attempt=0,
                    max_attempts=max_attempts,
                    available_at=utc_now(),
                    runner_id=target_runner_id,
                    required_capability=required_capability,
                    execution_key=f"{run_id}:{node_run.id}",
                )
            )
            submitted.append(node_id)
        return submitted

    def reconcile_run(self, db: Session, run_id: str) -> WorkflowRunStatus | None:
        """Idempotent reconciliation: promote due waits, fill missed
        scheduling, cancel leftover work for cancelled runs, and derive /
        persist the WorkflowRun status. Supports RUNNING, WAITING and PAUSED
        runs (PAUSED is frozen; WAITING resumes via promote_due_waits)."""
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
        if run is None:
            return None
        current = WorkflowRunStatus(run.status)

        if current is WorkflowRunStatus.CANCELLED:
            self.cancel_run_tasks(db, run_id)
            return current
        if current in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED):
            return current

        if current is WorkflowRunStatus.PAUSED:
            return current
        self.promote_due_waits(db, run_id)

        self.schedule_ready_nodes(db, run_id)

        graph = parse_workflow_graph(run.graph_snapshot_json)
        node_runs = list_node_runs(db, run_id)
        derived = derive_workflow_state(graph, node_runs)
        if derived is not current:
            transition_workflow_run(current, derived)
            run.status = derived.value
            if derived in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED):
                run.finished_at = utc_now()
            if derived is WorkflowRunStatus.FAILED:
                # Fail-fast: prevent queued parallel siblings from starting.
                self.cancel_run_tasks(db, run_id)
            self._workflow_event(db, run, derived, reason=self._waiting_reason(node_runs))
        if derived is WorkflowRunStatus.RUNNING:
            # schedule_ready_nodes only submits for RUNNING runs, so a run that
            # just left WAITING needs its newly ready nodes submitted here.
            self.schedule_ready_nodes(db, run_id)
        run.waiting_reason = self._waiting_reason(node_runs) if derived is WorkflowRunStatus.WAITING else None
        return derived

    @staticmethod
    def _workflow_event(db: Session, run: WorkflowRun, derived: WorkflowRunStatus, reason: str | None) -> None:
        mapping = {
            WorkflowRunStatus.WAITING: RunEventType.WORKFLOW_WAITING,
            WorkflowRunStatus.RUNNING: RunEventType.WORKFLOW_RESUMED,
            WorkflowRunStatus.COMPLETED: RunEventType.WORKFLOW_COMPLETED,
            WorkflowRunStatus.FAILED: RunEventType.WORKFLOW_FAILED,
            WorkflowRunStatus.CANCELLED: RunEventType.WORKFLOW_CANCELLED,
        }
        event_type = mapping.get(derived)
        if event_type is None:
            return
        payload = {"reason": reason} if reason else {}
        record_event(db, workflow_run_id=run.id, event_type=event_type, message=f"Workflow {derived.value}", payload=payload)

    @staticmethod
    def _waiting_reason(node_runs: list[NodeRun]) -> str | None:
        for node_run in node_runs:
            if NodeRunStatus(node_run.status) is NodeRunStatus.WAITING and node_run.waiting_reason:
                return node_run.waiting_reason
        return None

    def promote_due_waits(self, db: Session, run_id: str) -> bool:
        """Complete WAIT_TIMER NodeRuns whose resume_at has passed."""
        changed = False
        for node_run in list_node_runs(db, run_id):
            if NodeRunStatus(node_run.status) is not NodeRunStatus.WAITING:
                continue
            if node_run.waiting_reason != "WAIT_TIMER":
                continue
            metadata = node_run.waiting_metadata_json or {}
            resume_at = metadata.get("resume_at")
            if not isinstance(resume_at, str):
                continue
            try:
                due = datetime.fromisoformat(resume_at)
            except ValueError:
                continue
            if due > utc_now():
                continue
            transition_node_run(NodeRunStatus.WAITING, NodeRunStatus.COMPLETED)
            node_run.status = NodeRunStatus.COMPLETED.value
            node_run.output_json = dict(metadata)
            node_run.finished_at = utc_now()
            record_event(
                db,
                workflow_run_id=run_id,
                node_run_id=node_run.id,
                event_type=RunEventType.NODE_RESUMED,
                message="Wait timer elapsed",
                payload={"node_id": node_run.node_id, "action": "wait"},
            )
            record_event(
                db,
                workflow_run_id=run_id,
                node_run_id=node_run.id,
                event_type=RunEventType.NODE_COMPLETED,
                message="Node completed after wait",
                payload={"node_id": node_run.node_id},
            )
            changed = True
        return changed

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
            record_event(
                db,
                workflow_run_id=run_id,
                node_run_id=task.node_run_id,
                event_type=RunEventType.NODE_CANCELLED,
                message="Node cancelled",
                payload={"node_id": task.payload_json.get("node_id") if isinstance(task.payload_json, dict) else None},
            )
        # Cancel PENDING node runs that never received a task.
        for node_run in list_node_runs(db, run_id):
            status = NodeRunStatus(node_run.status)
            if status is NodeRunStatus.PENDING and not is_node_run_terminal(status):
                transition_node_run(status, NodeRunStatus.CANCELLED)
                node_run.status = NodeRunStatus.CANCELLED.value
                node_run.finished_at = utc_now()


def _retry_settings_for_node(
    run: WorkflowRun,
    node: dict[str, Any],
    *,
    default_backoff_seconds: int,
) -> tuple[int, int]:
    """Derive durable retry settings from the immutable Run snapshot.

    Graph retry is explicit and takes precedence.  A Service node without an
    explicit graph override inherits its ServiceAction retry policy.  All
    other nodes perform one attempt by default, preventing accidental replay
    of non-idempotent work.
    """
    config = node.get("config") if isinstance(node.get("config"), dict) else {}
    retry = config.get("retry")
    if isinstance(retry, dict) and "max_retries" in retry:
        max_retries = _bounded_int(retry.get("max_retries"), default=0, maximum=10)
        return max_retries + 1, _service_backoff_seconds(run, node, default=default_backoff_seconds)

    if node.get("type") == "service" and node.get("subtype") == "http":
        action_id = config.get("service_action_id")
        actions = run.execution_snapshot_json.get("service_actions", {})
        action = actions.get(action_id) if isinstance(actions, dict) and isinstance(action_id, str) else None
        policy = action.get("retry_policy") if isinstance(action, dict) else None
        if isinstance(policy, dict):
            return _bounded_int(policy.get("max_retries"), default=0, maximum=10) + 1, _bounded_int(
                policy.get("backoff_seconds"), default=5, maximum=86_400
            )
    return 1, 0


def _service_backoff_seconds(run: WorkflowRun, node: dict[str, Any], *, default: int) -> int:
    config = node.get("config") if isinstance(node.get("config"), dict) else {}
    if node.get("type") != "service" or node.get("subtype") != "http":
        return default
    actions = run.execution_snapshot_json.get("service_actions", {})
    action_id = config.get("service_action_id")
    action = actions.get(action_id) if isinstance(actions, dict) and isinstance(action_id, str) else None
    policy = action.get("retry_policy") if isinstance(action, dict) else None
    return _bounded_int(policy.get("backoff_seconds") if isinstance(policy, dict) else None, default=default, maximum=86_400)


def _bounded_int(value: Any, *, default: int, maximum: int) -> int:
    try:
        return max(0, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _attach_workspace(db: Session, run_id: str, node_run: NodeRun, node_id: str, node, payload: dict, *, runner_id: str | None) -> None:
    """Create a Workspace record when the node declares one, and put its
    preparation configuration into the task payload (Runner prepares it)."""
    workspace_config = node.config.get("workspace") if isinstance(node.config, dict) else None
    if not (isinstance(workspace_config, dict) and workspace_config.get("repository")):
        return
    from app.domain.workspaces.service import create_workspace

    workspace = create_workspace(
        db,
        workflow_run_id=run_id,
        node_run_id=node_run.id,
        node_id=node_id,
        name=f"{run_id[:8]}-{node_id}",
        repository=str(workspace_config.get("repository")),
        strategy=str(workspace_config.get("strategy") or "worktree"),
        base_branch=workspace_config.get("base_branch"),
        runner_id=runner_id,
    )
    payload["workspace"] = {
        "id": workspace.id,
        "repository": workspace.repository,
        "strategy": workspace.workspace_type,
        "base_branch": workspace.base_branch,
        "branch": workspace.branch,
    }


def _coding_agent_payload(run: WorkflowRun, node_runs: list[NodeRun], node) -> dict | None:
    """Build a Runner-executable payload for a coding-agent (Codex) node."""
    config = node.config if isinstance(node.config, dict) else {}
    agents_snapshot = run.execution_snapshot_json.get("agents", {})
    agent_snapshot = agents_snapshot.get(config.get("agent_id")) if isinstance(agents_snapshot, dict) else None
    if not isinstance(agent_snapshot, dict):
        return None
    connector_type = agent_snapshot.get("connector_type")
    if connector_type == "codex":
        from app.connectors.agents.coding import CodexConnector

        resolved = _resolve_agent_task(run, node_runs, node)
        if resolved is None:
            return None
        command = CodexConnector().build_command(
            task=resolved["task"],
            timeout_seconds=resolved["timeout_seconds"],
            executable=agent_snapshot.get("executable"),
        )
        return {
            "capability": "codex",
            "runner_id": agent_snapshot.get("runner_id"),
            "config": {"command": command, "working_directory": None, "timeout_seconds": resolved["timeout_seconds"]},
        }
    return None


def _resolve_agent_task(run: WorkflowRun, node_runs: list[NodeRun], node) -> dict | None:
    completed = {node_run.node_id: node_run.output_json for node_run in node_runs if node_run.output_json is not None}
    resolver = ContextResolver(
        workflow_input=run.input_json,
        variables=run.variables_json,
        node_outputs=completed,
        run={"id": run.id, "status": run.status},
    )
    try:
        resolved = resolver.resolve(node.config)
    except UnresolvedContextReference:
        return None
    task = resolved.get("task_template")
    if not isinstance(task, str) or not task.strip():
        return None
    timeout_value = resolved.get("timeout_seconds")
    try:
        timeout_seconds = max(int(timeout_value), 1) if timeout_value else 600
    except (TypeError, ValueError):
        timeout_seconds = 600
    return {"task": task, "timeout_seconds": timeout_seconds}


def _resolve_tool_config(run: WorkflowRun, node_runs: list[NodeRun], node) -> dict | None:
    """Resolve a Tool node's config into a Runner-executable payload. Returns
    None while an upstream dependency is not yet available (re-check later)."""
    completed = {node_run.node_id: node_run.output_json for node_run in node_runs if node_run.output_json is not None}
    resolver = ContextResolver(
        workflow_input=run.input_json,
        variables=run.variables_json,
        node_outputs=completed,
        run={"id": run.id, "status": run.status},
    )
    try:
        resolved = resolver.resolve(node.config)
    except UnresolvedContextReference:
        return None
    command = resolved.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    working_directory = resolved.get("working_directory")
    timeout_value = resolved.get("timeout_seconds")
    try:
        timeout_seconds = max(int(timeout_value), 1) if timeout_value else 60
    except (TypeError, ValueError):
        timeout_seconds = 60
    return {
        "command": command,
        "working_directory": working_directory if isinstance(working_directory, str) else None,
        "runner_id": resolved.get("runner_id") if isinstance(resolved.get("runner_id"), str) else None,
        "timeout_seconds": timeout_seconds,
    }
