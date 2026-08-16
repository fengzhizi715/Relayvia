"""Workflow Run / Node Run State Machines.

Pure transition tables. No ORM, no service logic here: callers load a row,
call `transition_*`, apply timestamps and persist. Invalid transitions raise
`RelayviaError` with a structured code so the API stays consistent.
"""

from enum import StrEnum

from app.core.errors import RelayviaError


class WorkflowRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeRunStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


WORKFLOW_RUN_TERMINAL = frozenset(
    {WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED}
)

WORKFLOW_RUN_TRANSITIONS: dict[WorkflowRunStatus, frozenset[WorkflowRunStatus]] = {
    WorkflowRunStatus.CREATED: frozenset({WorkflowRunStatus.RUNNING, WorkflowRunStatus.CANCELLED}),
    WorkflowRunStatus.RUNNING: frozenset(
        {WorkflowRunStatus.WAITING, WorkflowRunStatus.PAUSED, WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED}
    ),
    WorkflowRunStatus.WAITING: frozenset(
        {WorkflowRunStatus.RUNNING, WorkflowRunStatus.PAUSED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED}
    ),
    WorkflowRunStatus.PAUSED: frozenset({WorkflowRunStatus.RUNNING, WorkflowRunStatus.CANCELLED}),
    WorkflowRunStatus.COMPLETED: frozenset(),
    WorkflowRunStatus.FAILED: frozenset(),
    WorkflowRunStatus.CANCELLED: frozenset(),
}

NODE_RUN_TERMINAL = frozenset(
    {NodeRunStatus.COMPLETED, NodeRunStatus.FAILED, NodeRunStatus.SKIPPED, NodeRunStatus.CANCELLED}
)

NODE_RUN_TRANSITIONS: dict[NodeRunStatus, frozenset[NodeRunStatus]] = {
    NodeRunStatus.PENDING: frozenset({NodeRunStatus.QUEUED, NodeRunStatus.SKIPPED, NodeRunStatus.CANCELLED}),
    NodeRunStatus.QUEUED: frozenset({NodeRunStatus.RUNNING, NodeRunStatus.CANCELLED}),
    NodeRunStatus.RUNNING: frozenset(
        {NodeRunStatus.COMPLETED, NodeRunStatus.FAILED, NodeRunStatus.WAITING, NodeRunStatus.RETRYING, NodeRunStatus.CANCELLED}
    ),
    NodeRunStatus.WAITING: frozenset({NodeRunStatus.RUNNING, NodeRunStatus.COMPLETED, NodeRunStatus.FAILED, NodeRunStatus.CANCELLED}),
    NodeRunStatus.RETRYING: frozenset({NodeRunStatus.QUEUED, NodeRunStatus.FAILED, NodeRunStatus.CANCELLED}),
    NodeRunStatus.COMPLETED: frozenset(),
    NodeRunStatus.FAILED: frozenset(),
    NodeRunStatus.SKIPPED: frozenset(),
    NodeRunStatus.CANCELLED: frozenset(),
}


def is_workflow_run_terminal(status: WorkflowRunStatus) -> bool:
    return status in WORKFLOW_RUN_TERMINAL


def is_node_run_terminal(status: NodeRunStatus) -> bool:
    return status in NODE_RUN_TERMINAL


def transition_workflow_run(current: WorkflowRunStatus, target: WorkflowRunStatus) -> None:
    if target not in WORKFLOW_RUN_TRANSITIONS.get(current, frozenset()):
        raise RelayviaError(
            "INVALID_WORKFLOW_RUN_TRANSITION",
            f"Workflow Run cannot transition from {current.value!r} to {target.value!r}",
            status_code=409,
            details={"current": current.value, "target": target.value},
        )


def transition_node_run(current: NodeRunStatus, target: NodeRunStatus) -> None:
    if target not in NODE_RUN_TRANSITIONS.get(current, frozenset()):
        raise RelayviaError(
            "INVALID_NODE_RUN_TRANSITION",
            f"Node Run cannot transition from {current.value!r} to {target.value!r}",
            status_code=409,
            details={"current": current.value, "target": target.value},
        )


__all__ = [
    "NODE_RUN_TRANSITIONS",
    "NODE_RUN_TERMINAL",
    "NodeRunStatus",
    "WORKFLOW_RUN_TRANSITIONS",
    "WORKFLOW_RUN_TERMINAL",
    "WorkflowRunStatus",
    "is_node_run_terminal",
    "is_workflow_run_terminal",
    "transition_node_run",
    "transition_workflow_run",
]
