"""Tool nodes require a Relayvia Runner; the server never runs commands."""

import asyncio
import uuid

from sqlalchemy import select

from app.connectors.tools.base import ToolInvocationConfig
from app.connectors.tools.shell import ShellToolConnector
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.default import DefaultNodeExecutor
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.workers.workflow_worker import _process_task


def test_tool_connector_requires_runner():
    result = asyncio.run(ShellToolConnector().execute(ToolInvocationConfig(command="echo hello", timeout_seconds=10)))
    assert result.status == "failed"
    assert result.retryable is False
    assert result.error is not None
    assert result.error.code == "RUNNER_REQUIRED"


def tool_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "t", "type": "tool", "subtype": "shell", "name": "Shell", "position": {"x": 100, "y": 0}, "config": {"command": "echo hello", "working_directory": None, "timeout_seconds": 30}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 200, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "t", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "t", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def make_tool_run(db, graph: dict):
    workflow = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
    db.add(workflow)
    db.flush()
    version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json=graph)
    db.add(version)
    db.flush()
    run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        version_number=1,
        status=WorkflowRunStatus.RUNNING.value,
        graph_schema_version="1.0",
        graph_snapshot_json=graph,
        execution_snapshot_json={"schema_version": "2"},
        input_json={},
        variables_json={},
    )
    db.add(run)
    db.flush()
    for node in graph["nodes"]:
        is_input = node["type"] == "data" and node["subtype"] == "input"
        db.add(
            NodeRun(
                workflow_run_id=run.id,
                node_id=node["id"],
                node_type=node["type"],
                node_subtype=node["subtype"],
                node_name_snapshot=node["name"],
                status=NodeRunStatus.COMPLETED.value if is_input else NodeRunStatus.PENDING.value,
                output_json={} if is_input else None,
                attempt=0,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def test_tool_node_fails_without_runner(memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_tool_run(db, tool_graph())
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    backend = MySQLExecutionBackend(factory)
    executor = DefaultNodeExecutor(factory)

    async def drive():
        while True:
            task = await backend.claim("tool-worker")
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="tool-worker", renew_interval=60.0)

    asyncio.run(drive())

    with factory() as db:
        refreshed = db.get(WorkflowRun, run_id)
        assert refreshed.status == WorkflowRunStatus.FAILED.value
        tool_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "t"))
        assert tool_run.status == NodeRunStatus.FAILED.value
        assert tool_run.error_json["code"] == "RUNNER_REQUIRED"
