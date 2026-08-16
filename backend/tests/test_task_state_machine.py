import pytest

from app.core.errors import RelayviaError
from app.domain.execution.state_machine import ExecutionTaskStatus, is_execution_task_terminal, transition_execution_task


def test_valid_transitions():
    transitions = [
        (ExecutionTaskStatus.PENDING, ExecutionTaskStatus.CLAIMED),
        (ExecutionTaskStatus.PENDING, ExecutionTaskStatus.CANCELLED),
        (ExecutionTaskStatus.CLAIMED, ExecutionTaskStatus.RUNNING),
        (ExecutionTaskStatus.CLAIMED, ExecutionTaskStatus.PENDING),
        (ExecutionTaskStatus.CLAIMED, ExecutionTaskStatus.CANCELLED),
        (ExecutionTaskStatus.RUNNING, ExecutionTaskStatus.COMPLETED),
        (ExecutionTaskStatus.RUNNING, ExecutionTaskStatus.RETRY_WAIT),
        (ExecutionTaskStatus.RUNNING, ExecutionTaskStatus.FAILED),
        (ExecutionTaskStatus.RUNNING, ExecutionTaskStatus.CANCELLED),
        (ExecutionTaskStatus.RUNNING, ExecutionTaskStatus.PENDING),
        (ExecutionTaskStatus.RETRY_WAIT, ExecutionTaskStatus.PENDING),
        (ExecutionTaskStatus.RETRY_WAIT, ExecutionTaskStatus.FAILED),
        (ExecutionTaskStatus.RETRY_WAIT, ExecutionTaskStatus.CANCELLED),
    ]
    for current, target in transitions:
        transition_execution_task(current, target)


def test_terminal_transitions_rejected():
    for terminal in (ExecutionTaskStatus.COMPLETED, ExecutionTaskStatus.FAILED, ExecutionTaskStatus.CANCELLED):
        assert is_execution_task_terminal(terminal)
        with pytest.raises(RelayviaError) as exc:
            transition_execution_task(terminal, ExecutionTaskStatus.RUNNING)
        assert exc.value.code == "INVALID_EXECUTION_TASK_TRANSITION"
        assert exc.value.status_code == 409


def test_invalid_transition_rejected():
    with pytest.raises(RelayviaError):
        transition_execution_task(ExecutionTaskStatus.PENDING, ExecutionTaskStatus.RUNNING)
