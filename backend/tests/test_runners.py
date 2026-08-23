"""Phase 14: Relayvia Runner tests."""

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.config import Settings
from app.domain.execution.models import ExecutionTask
from app.domain.execution.state_machine import ExecutionTaskStatus
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.database.base import utc_now
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.default import DefaultNodeExecutor
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.runners.runner import execute_task
from app.workers.workflow_worker import _process_task


def tool_graph(command: str = "echo hello") -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "t", "type": "tool", "subtype": "shell", "name": "Shell", "position": {"x": 100, "y": 0}, "config": {"command": command, "working_directory": None, "timeout_seconds": 30}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 200, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "t", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "t", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def make_run(db, graph: dict):
    workflow = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
    db.add(workflow)
    db.flush()
    version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json=graph)
    db.add(version)
    db.flush()
    run = WorkflowRun(
        workflow_id=workflow.id, workflow_version_id=version.id, version_number=1,
        status=WorkflowRunStatus.RUNNING.value, graph_schema_version="1.0", graph_snapshot_json=graph,
        execution_snapshot_json={"schema_version": "2"}, input_json={}, variables_json={},
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


def drive_worker(factory, scheduler):
    backend = MySQLExecutionBackend(factory)
    executor = DefaultNodeExecutor(factory)

    async def _drive():
        while True:
            task = await backend.claim("worker")
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="worker", renew_interval=60.0)

    asyncio.run(_drive())


def register_runner(client, name="local", capabilities=None):
    response = client.post(
        "/api/runners/register",
        json={"name": name, "hostname": "test-host", "platform": "test", "capabilities": capabilities or ["shell"], "metadata": {}},
    )
    assert response.status_code == 201
    return response.json()


def runner_headers(runner):
    return {"X-Relayvia-Runner-Token": runner["enrollment_token"]}


def test_register_heartbeat_and_offline_detection(client, memory_db):
    runner = register_runner(client)
    assert runner["status"] == "online"
    assert runner["capabilities"] == ["shell"]

    # Simulate offline: backdate last_seen beyond the threshold.
    with memory_db[1]() as db:
        row = db.get(__import__("app.domain.runners.models", fromlist=["Runner"]).Runner, runner["id"])
        row.last_seen_at = utc_now() - timedelta(seconds=3600)
        db.commit()
    listed = client.get("/api/runners").json()
    row_status = next(item for item in listed if item["id"] == runner["id"])["status"]
    assert row_status == "offline"

    hb = client.post(
        f"/api/runners/{runner['id']}/heartbeat",
        json={"hostname": "test-host", "platform": "test", "capabilities": ["shell"], "metadata": {}},
        headers=runner_headers(runner),
    )
    assert hb.status_code == 200
    assert hb.json()["status"] == "online"


def test_stable_runner_identity(client):
    first = register_runner(client, name="stable")
    second = client.post(
        "/api/runners/register",
        json={"name": "stable", "hostname": "test-host", "platform": "test", "capabilities": ["shell"], "metadata": {}, "runner_id": first["id"], "runner_token": first["enrollment_token"]},
    )
    assert second.status_code == 201
    assert second.json()["id"] == first["id"]
    assert len(client.get("/api/runners").json()) == 1


def test_runner_mutations_require_its_enrollment_token(client):
    runner = register_runner(client)
    assert "enrollment_token" not in client.get("/api/runners").json()[0]
    assert client.post(
        f"/api/runners/{runner['id']}/heartbeat",
        json={"hostname": "attacker", "platform": "test", "capabilities": ["shell"], "metadata": {}},
    ).status_code == 401
    assert client.post(
        "/api/runners/register",
        json={"name": "attacker", "hostname": "attacker", "platform": "test", "capabilities": ["shell"], "metadata": {}, "runner_id": runner["id"]},
    ).status_code == 401
    assert client.post(
        f"/api/runners/{runner['id']}/heartbeat",
        json={"hostname": "test-host", "platform": "test", "capabilities": ["shell"], "metadata": {}},
        headers=runner_headers(runner),
    ).status_code == 200


def test_runner_claims_capability_matched_tasks(client, memory_db):
    _, factory = memory_db
    with factory() as db:
        graph = tool_graph()
        graph["nodes"][1]["config"]["retry"] = {"max_retries": 1}
        run = make_run(db, graph)
        run_id = run.id
        WorkflowScheduler(default_max_attempts=1).schedule_ready_nodes(db, run.id)
        db.commit()

    git_runner = register_runner(client, name="git-only", capabilities=["git"])
    shell_runner = register_runner(client, name="shell", capabilities=["shell"])

    git_claim = client.post(f"/api/runners/{git_runner['id']}/claim", headers=runner_headers(git_runner)).json()
    assert git_claim is None  # capability mismatch

    shell_claim = client.post(f"/api/runners/{shell_runner['id']}/claim", headers=runner_headers(shell_runner))
    assert shell_claim.status_code == 200
    claimed = shell_claim.json()
    assert claimed is not None
    assert claimed["execution_type"] == "shell"
    assert claimed["config"]["command"] == "echo hello"
    assert claimed["node_id"] == "t"


def test_runner_claim_submit_completes_workflow(client, memory_db, tmp_path, monkeypatch):
    monkeypatch.setattr("app.runners.runner.get_settings", lambda: Settings(runner_root=str(tmp_path), backend_url="http://x", _env_file=None))
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, tool_graph())
        run_id = run.id
        WorkflowScheduler(default_max_attempts=1).schedule_ready_nodes(db, run.id)
        db.commit()

    runner = register_runner(client)
    claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=runner_headers(runner)).json()
    assert claimed is not None

    result = asyncio.run(execute_task(claimed))
    assert result["ok"] is True
    assert result["output"]["stdout"].strip() == "hello"

    submitted = client.post(
        f"/api/runners/{runner['id']}/submit-result",
        json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": result},
        headers=runner_headers(runner),
    )
    assert submitted.status_code == 200

    drive_worker(factory, WorkflowScheduler(default_max_attempts=1))
    with factory() as db:
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value
        tool_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "t"))
        assert tool_run.status == NodeRunStatus.COMPLETED.value
        assert tool_run.output_json["stdout"].strip() == "hello"


def test_runner_result_is_idempotent(client, memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, tool_graph())
        WorkflowScheduler(default_max_attempts=1).schedule_ready_nodes(db, run.id)
        db.commit()

    runner = register_runner(client)
    claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=runner_headers(runner)).json()
    result = {"ok": True, "output": {"stdout": "hello"}, "metadata": {"exit_code": 0}, "artifacts": [], "error": None}
    assert client.post(f"/api/runners/{runner['id']}/submit-result", json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": result}, headers=runner_headers(runner)).status_code == 200
    second = client.post(f"/api/runners/{runner['id']}/submit-result", json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": result}, headers=runner_headers(runner))
    assert second.status_code == 409


def test_cancelled_runner_task_is_signalled_and_cannot_publish_result(client, memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, tool_graph("sleep 30"))
        WorkflowScheduler(default_max_attempts=1).schedule_ready_nodes(db, run.id)
        db.commit()

    runner = register_runner(client)
    claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=runner_headers(runner)).json()
    assert claimed is not None
    assert client.post(f"/api/workflow-runs/{claimed['workflow_run_id']}/cancel").status_code == 200

    cancellation = client.post(
        f"/api/runners/{runner['id']}/tasks/{claimed['task_id']}/heartbeat",
        params={"lease_token": claimed["lease_token"]},
        headers=runner_headers(runner),
    )
    assert cancellation.status_code == 200
    assert cancellation.json() == {"cancel_requested": True}
    stale = client.post(
        f"/api/runners/{runner['id']}/submit-result",
        json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": {"ok": True, "output": {"stdout": "must not persist"}, "metadata": {}, "artifacts": [], "error": None}},
        headers=runner_headers(runner),
    )
    assert stale.status_code == 409


def test_runner_output_is_redacted_before_becoming_context(client, memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, tool_graph())
        WorkflowScheduler(default_max_attempts=1).schedule_ready_nodes(db, run.id)
        db.commit()

    runner = register_runner(client)
    claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=runner_headers(runner)).json()
    result = {
        "ok": True,
        "output": {"token": "plain-secret", "echo": "Authorization: plain-secret"},
        "metadata": {"password": "plain-secret"},
        "artifacts": [],
        "error": None,
    }
    assert client.post(
        f"/api/runners/{runner['id']}/submit-result",
        json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": result},
        headers=runner_headers(runner),
    ).status_code == 200
    with factory() as db:
        node_run = db.get(NodeRun, claimed["node_run_id"])
        assert node_run.output_json == {"token": "***REDACTED***", "echo": "Authorization:***REDACTED***"}
        assert node_run.execution_metadata_json == {"password": "***REDACTED***"}


def test_runner_cancellation_event_kills_local_process_group(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.runners.runner.get_settings",
        lambda: Settings(runner_root=str(tmp_path), runner_allow_unsandboxed_execution=True, _env_file=None),
    )

    async def execute_and_cancel():
        cancelled = asyncio.Event()
        future = asyncio.create_task(execute_task({"config": {"command": "sleep 30", "timeout_seconds": 60}}, cancel_event=cancelled))
        await asyncio.sleep(0.1)
        cancelled.set()
        return await future

    result = asyncio.run(execute_and_cancel())
    assert result["ok"] is False
    assert result["error"]["code"] == "RUNNER_CANCELLED"


def test_runner_lost_recovers_via_lease(client, memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, tool_graph())
        run_id = run.id
        WorkflowScheduler(default_max_attempts=1).schedule_ready_nodes(db, run.id)
        db.commit()

    runner = register_runner(client)
    claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=runner_headers(runner)).json()
    assert claimed is not None

    # Expired ownership is fenced even before recovery returns the task to the
    # pending queue.
    with factory() as db:
        task = db.scalar(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run_id))
        task.lease_expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert client.post(
        f"/api/runners/{runner['id']}/submit-result",
        json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": {"ok": True, "output": {}, "artifacts": [], "metadata": {}, "error": None}},
        headers=runner_headers(runner),
    ).status_code == 409

    # Runner crashes: expire its lease and recover.
    with factory() as db:
        task = db.scalar(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run_id))
        task.lease_expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    backend = MySQLExecutionBackend(factory)
    assert asyncio.run(backend.recover_expired()) == 1

    # A fresh Runner can reclaim and complete the task.
    runner_b = register_runner(client, name="replacement")
    re_claimed = client.post(f"/api/runners/{runner_b['id']}/claim", headers=runner_headers(runner_b)).json()
    assert re_claimed is not None
    assert client.post(
        f"/api/runners/{runner_b['id']}/submit-result",
        json={"task_id": re_claimed["task_id"], "lease_token": re_claimed["lease_token"], "result": {"ok": True, "output": {"stdout": "x"}, "artifacts": [], "metadata": {}, "error": None}},
        headers=runner_headers(runner_b),
    ).status_code == 200


def test_runner_failure_uses_durable_retry(client, memory_db):
    _, factory = memory_db
    with factory() as db:
        graph = tool_graph()
        graph["nodes"][1]["config"]["retry"] = {"max_retries": 1}
        run = make_run(db, graph)
        WorkflowScheduler(default_max_attempts=2, default_backoff_seconds=0).schedule_ready_nodes(db, run.id)
        db.commit()

    runner = register_runner(client)
    claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=runner_headers(runner)).json()
    failed = {"ok": False, "output": {}, "artifacts": [], "metadata": {}, "error": {"code": "TEMP", "message": "retry", "retryable": True, "details": {}}}
    assert client.post(
        f"/api/runners/{runner['id']}/submit-result",
        json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": failed},
        headers=runner_headers(runner),
    ).status_code == 200
    with factory() as db:
        task = db.get(ExecutionTask, claimed["task_id"])
        node = db.get(NodeRun, task.node_run_id)
        assert task.status == ExecutionTaskStatus.RETRY_WAIT.value
        assert node.status == NodeRunStatus.RETRYING.value
    assert asyncio.run(MySQLExecutionBackend(factory).promote_due_retries()) == 1
    retried = client.post(f"/api/runners/{runner['id']}/claim", headers=runner_headers(runner)).json()
    assert retried is not None and retried["attempt"] == 2


def test_runner_artifact_result(client, memory_db, monkeypatch):
    _, factory = memory_db
    from app.infrastructure.artifact_storage import LocalArtifactStorage
    import tempfile

    storage = LocalArtifactStorage(tempfile.mkdtemp())
    monkeypatch.setattr("app.api.routes.runners.get_artifact_storage", lambda: storage)
    with factory() as db:
        run = make_run(db, tool_graph())
        run_id = run.id
        WorkflowScheduler(default_max_attempts=1).schedule_ready_nodes(db, run.id)
        db.commit()

    runner = register_runner(client)
    claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=runner_headers(runner)).json()
    result = {
        "ok": True,
        "output": {"stdout": "done"},
        "artifacts": [{"name": "report.txt", "type": "report", "content_type": "text/plain", "content": "cnVubmVyLXJlcG9ydA==", "output_key": "report"}],
        "metadata": {"exit_code": 0},
        "error": None,
    }
    assert client.post(f"/api/runners/{runner['id']}/submit-result", json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": result}, headers=runner_headers(runner)).status_code == 200

    with factory() as db:
        tool_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "t"))
        assert tool_run.output_json["report"].startswith("artifact://")
        artifact_id = tool_run.output_json["report"][len("artifact://"):]
    assert storage.open(artifact_id).read() == b"runner-report"


def test_execute_task_units(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.runners.runner.get_settings",
        lambda: Settings(runner_root=str(tmp_path), backend_url="http://x", _env_file=None),
    )
    ok = asyncio.run(execute_task({"config": {"command": "echo hello", "timeout_seconds": 10}}))
    assert ok["ok"] is True and ok["output"]["stdout"].strip() == "hello"

    failed = asyncio.run(execute_task({"config": {"command": "exit 3", "timeout_seconds": 10}}))
    assert failed["ok"] is False and failed["error"]["code"] == "RUNNER_EXIT_NONZERO" and failed["error"]["retryable"] is True

    timeout = asyncio.run(execute_task({"config": {"command": "sleep 5", "timeout_seconds": 1}}))
    assert timeout["ok"] is False and timeout["error"]["code"] == "RUNNER_TIMEOUT"


def test_execute_task_rejects_cwd_escape(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr("app.runners.runner.get_settings", lambda: Settings(runner_root=str(root), backend_url="http://x", _env_file=None))
    result = asyncio.run(execute_task({"config": {"command": "pwd", "working_directory": str(tmp_path), "timeout_seconds": 5}}))
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_WORKING_DIRECTORY"
