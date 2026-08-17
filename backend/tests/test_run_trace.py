"""Phase 13: Run Trace events + SSE delivery tests."""

import asyncio
import json
import uuid

from sqlalchemy import select

from app.domain.runs.events import RunEvent
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.base import NodeExecutionContext, NodeExecutionResult, NodeExecutor
from app.runtime.executor.default import DefaultNodeExecutor
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.workers.workflow_worker import _process_task


def registry_snapshot(server: str) -> dict:
    return {
        "schema_version": "2",
        "agents": {
            "agent-1": {"connector_type": "http", "endpoint": f"{server}/agent", "http_method": "POST", "headers": {}, "timeout_seconds": 10, "credential_id": None, "input_schema": {}, "output_schema": {}},
        },
        "services": {},
        "service_actions": {},
    }


def make_run(db, graph: dict, snapshot: dict):
    workflow = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
    db.add(workflow)
    db.flush()
    version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json=graph)
    db.add(version)
    db.flush()
    run = WorkflowRun(
        workflow_id=workflow.id, workflow_version_id=version.id, version_number=1,
        status=WorkflowRunStatus.RUNNING.value, graph_schema_version="1.0", graph_snapshot_json=graph,
        execution_snapshot_json=snapshot, input_json={}, variables_json={},
    )
    db.add(run)
    db.flush()
    for node in graph["nodes"]:
        is_input = node["type"] == "data" and node["subtype"] == "input"
        db.add(
            NodeRun(workflow_run_id=run.id, node_id=node["id"], node_type=node["type"], node_subtype=node["subtype"],
                    node_name_snapshot=node["name"], status=NodeRunStatus.COMPLETED.value if is_input else NodeRunStatus.PENDING.value,
                    output_json={} if is_input else None, attempt=0)
        )
    db.commit()
    db.refresh(run)
    return run


def drive(factory, scheduler, executor=None):
    backend = MySQLExecutionBackend(factory)
    executor = executor or DefaultNodeExecutor(factory)

    async def _drive():
        while True:
            await backend.promote_due_retries()
            task = await backend.claim("trace-worker")
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="trace-worker", renew_interval=60.0)

    asyncio.run(_drive())


def events_of(factory, run_id):
    with factory() as db:
        rows = db.scalars(select(RunEvent).where(RunEvent.workflow_run_id == run_id).order_by(RunEvent.id)).all()
        return [(row.id, row.event_type, row.node_run_id, row.payload_json) for row in rows]


def linear_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "agent", "type": "agent", "subtype": "agent", "name": "Agent", "position": {"x": 100, "y": 0}, "config": {"agent_id": "agent-1", "retry": {"max_retries": 1}}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 200, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "agent", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "agent", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def condition_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "condition", "type": "logic", "subtype": "condition", "name": "Condition", "position": {"x": 100, "y": 0}, "config": {"expression": {"left": True, "operator": "==", "right": True}}, "input_mapping": {}, "metadata": {}},
            {"id": "true_agent", "type": "agent", "subtype": "agent", "name": "True", "position": {"x": 200, "y": -80}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "false_agent", "type": "agent", "subtype": "agent", "name": "False", "position": {"x": 200, "y": 80}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 300, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "condition", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "condition", "target": "true_agent", "source_handle": "true", "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "condition", "target": "false_agent", "source_handle": "false", "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e4", "source": "true_agent", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e5", "source": "false_agent", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def approval_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "agent", "type": "agent", "subtype": "agent", "name": "Agent", "position": {"x": 100, "y": 0}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "approval", "type": "human", "subtype": "approval", "name": "Approval", "position": {"x": 200, "y": 0}, "config": {"title": "Approve?"}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 300, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "agent", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "agent", "target": "approval", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "approval", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


class FakeExecutor(NodeExecutor):
    def __init__(self, *, fail_once=None) -> None:
        self.fail_once = fail_once or set()
        self.calls = {}

    async def execute(self, ctx: NodeExecutionContext) -> NodeExecutionResult:
        self.calls[ctx.node_id] = self.calls.get(ctx.node_id, 0) + 1
        if ctx.node_id in self.fail_once and self.calls[ctx.node_id] == 1:
            from app.runtime.executor.result import ExecutionError

            return NodeExecutionResult(ok=False, retryable=True, error=ExecutionError("FAILED", "boom", retryable=True))
        return NodeExecutionResult(ok=True, output={"node": ctx.node_id})


def test_linear_run_emits_lifecycle_events(memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, linear_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_backoff_seconds=0)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    events = events_of(factory, run_id)
    types = [event_type for _, event_type, _, _ in events]
    for expected in ("node_queued", "node_started", "node_completed", "workflow_completed"):
        assert expected in types
    ids = [event_id for event_id, _, _, _ in events]
    assert ids == sorted(ids)  # stable total order


def test_retry_events(memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, linear_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_backoff_seconds=0)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler, executor=FakeExecutor(fail_once={"agent"}))
    events = events_of(factory, run_id)
    types = [event_type for _, event_type, _, _ in events]
    assert "node_retrying" in types
    agent_started = [payload for _, et, _, payload in events if et == "node_started" and payload.get("node_id") == "agent"]
    assert len(agent_started) == 2  # attempt 1 + retry
    assert "node_completed" in types


def test_waiting_and_resume_events(client, memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, approval_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    types = [event_type for _, event_type, _, _ in events_of(factory, run_id)]
    assert "node_waiting" in types
    assert "workflow_waiting" in types

    with factory() as db:
        approval_run_id = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "approval")).id
    approved = client.post(f"/api/node-runs/{approval_run_id}/approve")
    assert approved.status_code == 200

    drive(factory, scheduler)
    types = [event_type for _, event_type, _, _ in events_of(factory, run_id)]
    assert "node_resumed" in types
    assert "workflow_resumed" in types
    assert "workflow_completed" in types


def test_condition_and_skipped_events(memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, condition_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    types = [event_type for _, event_type, _, _ in events_of(factory, run_id)]
    assert "node_skipped" in types
    completed = [payload for _, et, _, payload in events_of(factory, run_id) if et == "node_completed"]
    assert any(payload.get("selected_branch") == "true" for payload in completed)


def test_event_payloads_do_not_contain_secrets(memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, linear_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    for _, _, _, payload in events_of(factory, run_id):
        serialized = json.dumps(payload)
        assert "authorization" not in serialized
        assert "token" not in serialized
        assert "secret" not in serialized
        assert "password" not in serialized


def test_events_api_after_id_pagination(client, memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, linear_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    first = client.get(f"/api/workflow-runs/{run_id}/events", params={"limit": 1})
    assert first.status_code == 200
    first_batch = first.json()
    assert len(first_batch) == 1
    after = client.get(f"/api/workflow-runs/{run_id}/events", params={"after_id": first_batch[0]["id"]})
    second_batch = after.json()
    assert all(event["id"] > first_batch[0]["id"] for event in second_batch)
    assert first_batch[0]["id"] + len(second_batch) == len(events_of(factory, run_id))


def test_sse_streams_all_events_and_terminates(client, memory_db, http_test_server, monkeypatch):
    _, factory = memory_db
    monkeypatch.setattr("app.api.routes.trace.get_session_factory", lambda: factory)
    with factory() as db:
        run = make_run(db, linear_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)

    with client.stream("GET", f"/api/workflow-runs/{run_id}/events/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.read().decode()
    assert "event: node_started" in body
    assert "event: workflow_completed" in body
    ids_in_stream = [line for line in body.splitlines() if line.startswith("id: ")]
    assert len(ids_in_stream) == len(events_of(factory, run_id))


def test_sse_reconnect_resumes_from_after_id(client, memory_db, http_test_server, monkeypatch):
    _, factory = memory_db
    monkeypatch.setattr("app.api.routes.trace.get_session_factory", lambda: factory)
    with factory() as db:
        run = make_run(db, linear_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    all_events = events_of(factory, run_id)
    last_seen = all_events[len(all_events) // 2][0]

    with client.stream("GET", f"/api/workflow-runs/{run_id}/events/stream", params={"after_id": last_seen}) as response:
        body = response.read().decode()
    ids_in_stream = [int(line.split(": ")[1]) for line in body.splitlines() if line.startswith("id: ")]
    assert ids_in_stream and all(event_id > last_seen for event_id in ids_in_stream)
    assert ids_in_stream == [event_id for event_id, _, _, _ in all_events if event_id > last_seen]


def test_sse_reconnect_resumes_from_last_event_id_header(client, memory_db, http_test_server, monkeypatch):
    _, factory = memory_db
    monkeypatch.setattr("app.api.routes.trace.get_session_factory", lambda: factory)
    with factory() as db:
        run = make_run(db, linear_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    all_events = events_of(factory, run_id)
    last_seen = all_events[len(all_events) // 2][0]
    with client.stream(
        "GET",
        f"/api/workflow-runs/{run_id}/events/stream",
        headers={"Last-Event-ID": str(last_seen)},
    ) as response:
        body = response.read().decode()
    ids_in_stream = [int(line.split(": ")[1]) for line in body.splitlines() if line.startswith("id: ")]
    assert ids_in_stream == [event_id for event_id, _, _, _ in all_events if event_id > last_seen]
