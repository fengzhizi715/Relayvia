"""Execution Task State Machine.

Pure transition table for ExecutionTask. `RUNNING -> PENDING` exists for lease
recovery (an expired RUNNING task returns to the queue). All transitions go
through `transition_execution_task`; callers never assign `status` directly.
"""

from enum import StrEnum

from app.core.errors import RelayviaError


class ExecutionTaskStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


EXECUTION_TASK_TERMINAL = frozenset(
    {ExecutionTaskStatus.COMPLETED, ExecutionTaskStatus.FAILED, ExecutionTaskStatus.CANCELLED}
)

EXECUTION_TASK_TRANSITIONS: dict[ExecutionTaskStatus, frozenset[ExecutionTaskStatus]] = {
    ExecutionTaskStatus.PENDING: frozenset({ExecutionTaskStatus.CLAIMED, ExecutionTaskStatus.CANCELLED}),
    ExecutionTaskStatus.CLAIMED: frozenset({ExecutionTaskStatus.RUNNING, ExecutionTaskStatus.PENDING, ExecutionTaskStatus.CANCELLED}),
    ExecutionTaskStatus.RUNNING: frozenset(
        {ExecutionTaskStatus.COMPLETED, ExecutionTaskStatus.RETRY_WAIT, ExecutionTaskStatus.FAILED, ExecutionTaskStatus.CANCELLED, ExecutionTaskStatus.PENDING}
    ),
    ExecutionTaskStatus.RETRY_WAIT: frozenset({ExecutionTaskStatus.PENDING, ExecutionTaskStatus.FAILED, ExecutionTaskStatus.CANCELLED}),
    ExecutionTaskStatus.COMPLETED: frozenset(),
    ExecutionTaskStatus.FAILED: frozenset(),
    ExecutionTaskStatus.CANCELLED: frozenset(),
}


def is_execution_task_terminal(status: ExecutionTaskStatus) -> bool:
    return status in EXECUTION_TASK_TERMINAL


def transition_execution_task(current: ExecutionTaskStatus, target: ExecutionTaskStatus) -> None:
    if target not in EXECUTION_TASK_TRANSITIONS.get(current, frozenset()):
        raise RelayviaError(
            "INVALID_EXECUTION_TASK_TRANSITION",
            f"Execution Task cannot transition from {current.value!r} to {target.value!r}",
            status_code=409,
            details={"current": current.value, "target": target.value},
        )


__all__ = [
    "EXECUTION_TASK_TRANSITIONS",
    "EXECUTION_TASK_TERMINAL",
    "ExecutionTaskStatus",
    "is_execution_task_terminal",
    "transition_execution_task",
]
