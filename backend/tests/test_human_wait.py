"""Phase 11: Human Approval + Human Input + Wait / Resume tests."""

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.database.base import utc_now
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.default import DefaultNodeExecutor
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.workers.workflow_worker import _process_task


def registry_snapshot(server: str) -> dict:
    return {
        "schema_version": "2",
        "agents": {
            "agent-1": {
                "connector_type": "http",
                "endpoint": f"{server}/agent",
                "http_method": "POST",
                "headers": {},
                "timeout_seconds": 10,
                "credential_id": None,
                "input_schema": {},
                "output_schema": {},
            }
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
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        version_number=1,
        status=WorkflowRunStatus.RUNNING.value,
        graph_schema_version="1.0",
        graph_snapshot_json=graph,
        execution_snapshot_json=snapshot,
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


def drive(factory, scheduler):
    backend = MySQLExecutionBackend(factory)
    executor = DefaultNodeExecutor(factory)

    async def _drive():
        while True:
            task = await backend.claim("phase11-worker")
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="phase11-worker", renew_interval=60.0)

    asyncio.run(_drive())


def run_status(factory, run_id) -> WorkflowRunStatus:
    with factory() as db:
        return WorkflowRunStatus(db.get(WorkflowRun, run_id).status)


def node_runs(factory, run_id) -> dict:
    with factory() as db:
        return {row.node_id: row for row in db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run_id)).all()}


# --- Graph builders ---


def approval_graph(extra_nodes=None, extra_edges=None) -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "agent", "type": "agent", "subtype": "agent", "name": "Agent", "position": {"x": 100, "y": 0}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "approval", "type": "human", "subtype": "approval", "name": "Approval", "position": {"x": 200, "y": 0}, "config": {"title": "Approve?"}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 300, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
            *(extra_nodes or []),
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "agent", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "agent", "target": "approval", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "approval", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            *(extra_edges or []),
        ],
        "variables": {},
        "metadata": {},
    }


def human_input_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "human_input", "type": "human", "subtype": "input", "name": "Human Input", "position": {"x": 100, "y": 0}, "config": {"form_schema": {"type": "object", "properties": {"comment": {"type": "string"}}}}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 200, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "human_input", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "human_input", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def wait_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "wait", "type": "logic", "subtype": "wait", "name": "Wait", "position": {"x": 100, "y": 0}, "config": {"mode": "duration", "duration_seconds": 3600}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 200, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "wait", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "wait", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def parallel_approval_merge_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "parallel", "type": "logic", "subtype": "parallel", "name": "Parallel", "position": {"x": 100, "y": 0}, "config": {}, "input_mapping": {}, "metadata": {}},
            {"id": "a", "type": "agent", "subtype": "agent", "name": "Agent A", "position": {"x": 200, "y": -80}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "approval", "type": "human", "subtype": "approval", "name": "Approval", "position": {"x": 200, "y": 80}, "config": {"title": "Approve?"}, "input_mapping": {}, "metadata": {}},
            {"id": "merge", "type": "logic", "subtype": "merge", "name": "Merge", "position": {"x": 300, "y": 0}, "config": {"strategy": "all"}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 400, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "parallel", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "parallel", "target": "a", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "parallel", "target": "approval", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e4", "source": "a", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e5", "source": "approval", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e6", "source": "merge", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def condition_approval_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "condition", "type": "logic", "subtype": "condition", "name": "Condition", "position": {"x": 100, "y": 0}, "config": {"expression": {"left": True, "operator": "==", "right": True}}, "input_mapping": {}, "metadata": {}},
            {"id": "true_agent", "type": "agent", "subtype": "agent", "name": "True Agent", "position": {"x": 200, "y": -80}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "false_approval", "type": "human", "subtype": "approval", "name": "False Approval", "position": {"x": 200, "y": 80}, "config": {"title": "Approve?"}, "input_mapping": {}, "metadata": {}},
            {"id": "merge", "type": "logic", "subtype": "merge", "name": "Merge", "position": {"x": 300, "y": 0}, "config": {"strategy": "all"}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 400, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "condition", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "condition", "target": "true_agent", "source_handle": "true", "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "condition", "target": "false_approval", "source_handle": "false", "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e4", "source": "true_agent", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e5", "source": "false_approval", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e6", "source": "merge", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


# --- Tests ---


def test_human_approval_wait_and_resume(client, memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, approval_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.WAITING
    nodes = node_runs(factory, run_id)
    assert NodeRunStatus(nodes["approval"].status) is NodeRunStatus.WAITING
    assert nodes["approval"].waiting_reason == "HUMAN_APPROVAL"
    assert run_status(factory, run_id).value  # run waiting_reason set
    with factory() as db:
        assert db.get(WorkflowRun, run_id).waiting_reason == "HUMAN_APPROVAL"

    approval_run_id = nodes["approval"].id
    approved = client.post(f"/api/node-runs/{approval_run_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.COMPLETED
    assert NodeRunStatus(node_runs(factory, run_id)["output"].status) is NodeRunStatus.COMPLETED


def test_human_approval_reject_fails_workflow(client, memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, approval_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    approval_run_id = node_runs(factory, run_id)["approval"].id
    rejected = client.post(f"/api/node-runs/{approval_run_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "failed"

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.FAILED
    assert node_runs(factory, run_id)["approval"].error_json["code"] == "REJECTED"


def test_duplicate_approve_returns_conflict(client, memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, approval_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    approval_run_id = node_runs(factory, run_id)["approval"].id
    assert client.post(f"/api/node-runs/{approval_run_id}/approve").status_code == 200
    second = client.post(f"/api/node-runs/{approval_run_id}/approve")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "NODE_RUN_NOT_WAITING"


def test_human_input_submit(client, memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, human_input_graph(), registry_snapshot("http://127.0.0.1:1"))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.WAITING
    input_run_id = node_runs(factory, run_id)["human_input"].id

    submitted = client.post(f"/api/node-runs/{input_run_id}/submit", json={"input": {"comment": "approved"}})
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "completed"
    assert submitted.json()["output"] == {"comment": "approved"}

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.COMPLETED


def test_wait_timer_promotes_and_continues(memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, wait_graph(), registry_snapshot("http://127.0.0.1:1"))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.WAITING
    wait_run = node_runs(factory, run_id)["wait"]
    assert wait_run.waiting_reason == "WAIT_TIMER"
    assert "resume_at" in wait_run.waiting_metadata_json

    # Force the resume deadline into the past, then reconcile.
    with factory() as db:
        node_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "wait"))
        node_run.waiting_metadata_json = {"resume_at": (utc_now() - timedelta(seconds=1)).isoformat(), "duration_seconds": 1}
        db.commit()
    with factory() as db:
        scheduler.reconcile_run(db, run_id)
        db.commit()

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.COMPLETED
    assert NodeRunStatus(node_runs(factory, run_id)["wait"].status) is NodeRunStatus.COMPLETED


def test_parallel_approval_merge(memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, parallel_approval_merge_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    # Agent A completed; approval waiting -> run WAITING, merge must not schedule.
    nodes = node_runs(factory, run_id)
    assert NodeRunStatus(nodes["a"].status) is NodeRunStatus.COMPLETED
    assert NodeRunStatus(nodes["approval"].status) is NodeRunStatus.WAITING
    assert NodeRunStatus(nodes["merge"].status) is NodeRunStatus.PENDING
    assert run_status(factory, run_id) is WorkflowRunStatus.WAITING

    client = None  # not using client here; call service directly
    from app.domain.runs.service import approve_node_run

    with factory() as db:
        approve_node_run(db, nodes["approval"].id)
        db.commit()

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.COMPLETED
    assert NodeRunStatus(node_runs(factory, run_id)["merge"].status) is NodeRunStatus.COMPLETED


def test_condition_skipped_approval_does_not_wait(memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, condition_approval_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.COMPLETED
    nodes = node_runs(factory, run_id)
    assert NodeRunStatus(nodes["false_approval"].status) is NodeRunStatus.SKIPPED
    assert NodeRunStatus(nodes["true_agent"].status) is NodeRunStatus.COMPLETED


def test_waiting_run_survives_worker_restart(memory_db, http_test_server):
    """A waiting run stays WAITING; a fresh worker (new session) can resume it."""
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, approval_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.WAITING

    # Simulate Worker restart: a brand-new scheduler + drive (new sessions).
    fresh_scheduler = WorkflowScheduler(default_max_attempts=1)
    approval_run_id = node_runs(factory, run_id)["approval"].id
    from app.domain.runs.service import approve_node_run

    with factory() as db:
        approve_node_run(db, approval_run_id)
        db.commit()

    drive(factory, fresh_scheduler)
    assert run_status(factory, run_id) is WorkflowRunStatus.COMPLETED
