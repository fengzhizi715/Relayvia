import pytest

from app.core.errors import RelayviaError
from app.runtime.state_machine import (
    NodeRunStatus,
    WorkflowRunStatus,
    is_node_run_terminal,
    is_workflow_run_terminal,
    transition_node_run,
    transition_workflow_run,
)


def test_workflow_transitions_valid():
    transitions = [
        (WorkflowRunStatus.CREATED, WorkflowRunStatus.RUNNING),
        (WorkflowRunStatus.CREATED, WorkflowRunStatus.CANCELLED),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.WAITING),
        (WorkflowRunStatus.WAITING, WorkflowRunStatus.RUNNING),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.PAUSED),
        (WorkflowRunStatus.PAUSED, WorkflowRunStatus.RUNNING),
        (WorkflowRunStatus.WAITING, WorkflowRunStatus.PAUSED),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.COMPLETED),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.FAILED),
        (WorkflowRunStatus.RUNNING, WorkflowRunStatus.CANCELLED),
        (WorkflowRunStatus.WAITING, WorkflowRunStatus.FAILED),
    ]
    for current, target in transitions:
        transition_workflow_run(current, target)


def test_workflow_terminal_transitions_rejected():
    for terminal in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED):
        assert is_workflow_run_terminal(terminal)
        with pytest.raises(RelayviaError) as exc:
            transition_workflow_run(terminal, WorkflowRunStatus.RUNNING)
        assert exc.value.code == "INVALID_WORKFLOW_RUN_TRANSITION"
        assert exc.value.status_code == 409


def test_workflow_invalid_transition_rejected():
    with pytest.raises(RelayviaError) as exc:
        transition_workflow_run(WorkflowRunStatus.CREATED, WorkflowRunStatus.PAUSED)
    assert exc.value.code == "INVALID_WORKFLOW_RUN_TRANSITION"


def test_node_transitions_valid():
    transitions = [
        (NodeRunStatus.PENDING, NodeRunStatus.QUEUED),
        (NodeRunStatus.PENDING, NodeRunStatus.SKIPPED),
        (NodeRunStatus.PENDING, NodeRunStatus.CANCELLED),
        (NodeRunStatus.QUEUED, NodeRunStatus.RUNNING),
        (NodeRunStatus.QUEUED, NodeRunStatus.CANCELLED),
        (NodeRunStatus.RUNNING, NodeRunStatus.COMPLETED),
        (NodeRunStatus.RUNNING, NodeRunStatus.FAILED),
        (NodeRunStatus.RUNNING, NodeRunStatus.WAITING),
        (NodeRunStatus.RUNNING, NodeRunStatus.RETRYING),
        (NodeRunStatus.WAITING, NodeRunStatus.RUNNING),
        (NodeRunStatus.WAITING, NodeRunStatus.COMPLETED),
        (NodeRunStatus.RETRYING, NodeRunStatus.QUEUED),
        (NodeRunStatus.RETRYING, NodeRunStatus.FAILED),
    ]
    for current, target in transitions:
        transition_node_run(current, target)


def test_node_terminal_transitions_rejected():
    for terminal in (NodeRunStatus.COMPLETED, NodeRunStatus.FAILED, NodeRunStatus.SKIPPED, NodeRunStatus.CANCELLED):
        assert is_node_run_terminal(terminal)
        with pytest.raises(RelayviaError) as exc:
            transition_node_run(terminal, NodeRunStatus.RUNNING)
        assert exc.value.code == "INVALID_NODE_RUN_TRANSITION"


def test_node_invalid_transition_rejected():
    with pytest.raises(RelayviaError) as exc:
        transition_node_run(NodeRunStatus.PENDING, NodeRunStatus.RUNNING)
    assert exc.value.code == "INVALID_NODE_RUN_TRANSITION"
