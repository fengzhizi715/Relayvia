import asyncio
import uuid

from sqlalchemy import select

from app.domain.execution.models import ExecutionTask
from app.domain.execution.state_machine import ExecutionTaskStatus
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.base import NodeExecutionContext, NodeExecutionResult, NodeExecutor
from app.runtime.executor.result import ExecutionError
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler, derive_workflow_state
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.workers.workflow_worker import _process_task


def linear_graph(agent_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object", "properties": {}}}, "input_mapping": {}, "metadata": {}},
            {"id": "a", "type": "agent", "subtype": "agent", "name": "A", "position": {"x": 100, "y": 0}, "config": {"agent_id": agent_id}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 200, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "a", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "a", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def make_run(db, graph: dict, *, status: WorkflowRunStatus = WorkflowRunStatus.RUNNING) -> WorkflowRun:
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
        status=status.value,
        graph_schema_version="1.0",
        graph_snapshot_json=graph,
        execution_snapshot_json={"schema_version": "1"},
        input_json={"requirement": "x"},
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
                output_json={"requirement": "x"} if is_input else None,
                attempt=0,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def make_backend(factory, lease_seconds: int = 60) -> MySQLExecutionBackend:
    return MySQLExecutionBackend(factory, lease_seconds=lease_seconds)


class FakeExecutor(NodeExecutor):
    def __init__(self, *, fail_once: set[str] | None = None, always_retryable: bool = False, fail_forever: set[str] | None = None) -> None:
        self.fail_once = fail_once or set()
        self.fail_forever = fail_forever or set()
        self.always_retryable = always_retryable
        self.calls: dict[str, int] = {}

    async def execute(self, ctx: NodeExecutionContext) -> NodeExecutionResult:
        self.calls[ctx.node_id] = self.calls.get(ctx.node_id, 0) + 1
        if ctx.node_id in self.fail_forever or self.always_retryable:
            return NodeExecutionResult(ok=False, retryable=True, error=ExecutionError("FAILED", "boom", retryable=True))
        if ctx.node_id in self.fail_once and self.calls[ctx.node_id] == 1:
            return NodeExecutionResult(ok=False, retryable=True, error=ExecutionError("FAILED", "boom", retryable=True))
        return NodeExecutionResult(ok=True, output={"node": ctx.node_id, "ok": True})


# --- Scheduler ---


def test_scheduler_is_idempotent(db_session):
    run = make_run(db_session, linear_graph("agent-1"))
    scheduler = WorkflowScheduler()
    assert scheduler.schedule_ready_nodes(db_session, run.id) == ["a"]
    db_session.commit()
    assert scheduler.schedule_ready_nodes(db_session, run.id) == []
    db_session.commit()

    tasks = db_session.scalars(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run.id)).all()
    assert len(tasks) == 1
    task = tasks[0]
    assert task.status == ExecutionTaskStatus.PENDING.value
    node_run = db_session.get(NodeRun, task.node_run_id)
    assert node_run.status == NodeRunStatus.QUEUED.value


def test_scheduler_does_not_schedule_non_running_run(db_session):
    run = make_run(db_session, linear_graph("agent-1"), status=WorkflowRunStatus.PAUSED)
    assert WorkflowScheduler().schedule_ready_nodes(db_session, run.id) == []
    db_session.commit()
    tasks = db_session.scalars(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run.id)).all()
    assert tasks == []


def test_scheduler_reconcile_completes_workflow(db_session):
    run = make_run(db_session, linear_graph("agent-1"))
    scheduler = WorkflowScheduler()
    scheduler.reconcile_run(db_session, run.id)
    db_session.commit()
    tasks = db_session.scalars(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run.id)).all()
    assert len(tasks) == 1

    # Simulate full completion of every node.
    for node_run in db_session.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run.id)).all():
        node_run.status = NodeRunStatus.COMPLETED.value
        node_run.output_json = {"ok": True}
    derived = scheduler.reconcile_run(db_session, run.id)
    db_session.commit()
    assert derived is WorkflowRunStatus.COMPLETED
    refreshed = db_session.get(WorkflowRun, run.id)
    assert refreshed.status == WorkflowRunStatus.COMPLETED.value
    assert refreshed.finished_at is not None


def test_derive_workflow_state(db_session):
    run = make_run(db_session, linear_graph("agent-1"))
    node_runs = db_session.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run.id)).all()
    assert derive_workflow_state(None, node_runs) is WorkflowRunStatus.RUNNING
    for node_run in node_runs:
        node_run.status = NodeRunStatus.COMPLETED.value
    assert derive_workflow_state(None, node_runs) is WorkflowRunStatus.COMPLETED
    node_runs[1].status = NodeRunStatus.FAILED.value
    assert derive_workflow_state(None, node_runs) is WorkflowRunStatus.FAILED


def test_cancel_run_tasks(db_session):
    run = make_run(db_session, linear_graph("agent-1"))
    scheduler = WorkflowScheduler()
    scheduler.schedule_ready_nodes(db_session, run.id)
    db_session.commit()
    scheduler.cancel_run_tasks(db_session, run.id)
    db_session.commit()

    task = db_session.scalar(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run.id))
    assert task.status == ExecutionTaskStatus.CANCELLED.value
    node_run = db_session.get(NodeRun, task.node_run_id)
    assert node_run.status == NodeRunStatus.CANCELLED.value
    input_node = db_session.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run.id, NodeRun.node_id == "input"))
    assert input_node.status == NodeRunStatus.COMPLETED.value


# --- ExecutionBackend ---


def test_claim_and_complete(memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, linear_graph("agent-1"))
    backend = make_backend(factory)
    scheduler = WorkflowScheduler()

    async def flow():
        with factory() as db:
            scheduler.schedule_ready_nodes(db, run.id)
            db.commit()
        task = await backend.claim("w1")
        assert task is not None
        assert task.workflow_run_id == run.id
        assert await backend.claim("w2") is None  # only one owner
        assert await backend.start(task.id, "w1", task.lease_token) is True
        assert await backend.start(task.id, "w1", "wrong-token") is False  # fencing
        assert await backend.complete(task.id, "w1", task.lease_token, {"ok": True}) is True
        return task

    task = asyncio.run(flow())
    with factory() as db:
        task_row = db.get(ExecutionTask, task.id)
        assert task_row.status == ExecutionTaskStatus.COMPLETED.value
        node_run = db.get(NodeRun, task.node_run_id)
        assert node_run.status == NodeRunStatus.COMPLETED.value
        assert node_run.output_json == {"ok": True}


def test_lease_expiry_fencing(memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, linear_graph("agent-1"))
    backend = make_backend(factory)
    scheduler = WorkflowScheduler()

    async def flow():
        with factory() as db:
            scheduler.schedule_ready_nodes(db, run.id)
            db.commit()
        first = await backend.claim("w1")
        assert first is not None
        with factory() as db:
            task = db.get(ExecutionTask, first.id)
            task.lease_expires_at = task.lease_expires_at.replace(year=2000)
            db.commit()
        assert await backend.recover_expired() == 1
        second = await backend.claim("w2")
        assert second is not None
        # Old worker's token must no longer work.
        assert await backend.complete(first.id, "w1", first.lease_token, {}) is False
        assert await backend.start(second.id, "w2", second.lease_token) is True
        assert await backend.complete(second.id, "w2", second.lease_token, {"ok": True}) is True

    asyncio.run(flow())
    with factory() as db:
        task = db.scalar(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run.id))
        assert task.status == ExecutionTaskStatus.COMPLETED.value


def test_available_at_and_priority(memory_db):
    from datetime import datetime, timedelta, timezone

    _, factory = memory_db
    with factory() as db:
        run = make_run(db, linear_graph("agent-1"))
        node_runs = {nr.node_id: nr.id for nr in db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run.id)).all()}
    backend = make_backend(factory)
    future = datetime.now(timezone.utc) + timedelta(hours=1)

    async def flow():
        await backend.submit(run.id, node_runs["a"], payload={}, priority=0, max_attempts=1, available_at=future)
        await backend.submit(run.id, node_runs["output"], payload={}, priority=5, max_attempts=1, available_at=datetime.now(timezone.utc))
        claimed = await backend.claim("w1")
        assert claimed is not None
        assert claimed.node_run_id == node_runs["output"]  # higher priority
        assert await backend.claim("w1") is None  # lower-priority task is in the future

    asyncio.run(flow())
    with factory() as db:
        tasks = db.scalars(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run.id)).all()
        statuses = {task.node_run_id: task.status for task in tasks}
        assert statuses[node_runs["output"]] == ExecutionTaskStatus.CLAIMED.value
        assert statuses[node_runs["a"]] == ExecutionTaskStatus.PENDING.value


def test_retry_flow(memory_db):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, linear_graph("agent-1"))
    backend = make_backend(factory)
    scheduler = WorkflowScheduler(default_backoff_seconds=0)

    async def flow():
        with factory() as db:
            scheduler.schedule_ready_nodes(db, run.id)
            db.commit()
        task = await backend.claim("w1")
        assert task is not None
        await backend.start(task.id, "w1", task.lease_token)
        assert await backend.schedule_retry(task.id, "w1", task.lease_token, backoff_seconds=0) is True

    asyncio.run(flow())
    with factory() as db:
        task = db.scalar(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run.id))
        assert task.status == ExecutionTaskStatus.RETRY_WAIT.value
        node_run = db.get(NodeRun, task.node_run_id)
        assert node_run.status == NodeRunStatus.RETRYING.value

    async def promote_and_rerun():
        assert await backend.promote_due_retries() == 1
        retried = await backend.claim("w1")
        assert retried is not None
        assert retried.attempt == 1
        await backend.start(retried.id, "w1", retried.lease_token)
        await backend.complete(retried.id, "w1", retried.lease_token, {"ok": True})

    asyncio.run(promote_and_rerun())
    with factory() as db:
        task = db.scalar(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run.id))
        assert task.status == ExecutionTaskStatus.COMPLETED.value
        assert task.attempt == 2
        assert db.get(NodeRun, task.node_run_id).status == NodeRunStatus.COMPLETED.value


# --- Worker end-to-end ---


def test_linear_workflow_end_to_end(client, http_test_server, memory_db):
    _, factory = memory_db
    agent = client.post("/api/agents", json={"name": "Planner Agent", "endpoint": f"{http_test_server}/agent"}).json()
    workflow = client.post("/api/workflows", json={"name": "Queue E2E"}).json()
    graph = linear_graph(agent["id"])
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph}).status_code == 200
    assert client.post(f"/api/workflows/{workflow['id']}/versions", json={}).status_code == 201
    run = client.post(f"/api/workflows/{workflow['id']}/runs", json={"input": {"requirement": "x"}}).json()
    started = client.post(f"/api/workflow-runs/{run['id']}/start").json()
    assert started["status"] == "running"

    backend = make_backend(factory)
    scheduler = WorkflowScheduler()
    executor = FakeExecutor()

    async def drive():
        worker_id = "test-worker"
        while True:
            await backend.promote_due_retries()
            task = await backend.claim(worker_id)
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id=worker_id, renew_interval=60.0)

    asyncio.run(drive())

    detail = client.get(f"/api/workflow-runs/{run['id']}").json()
    assert detail["status"] == "completed"
    node_statuses = {node_run["node_id"]: node_run["status"] for node_run in detail["node_runs"]}
    assert node_statuses == {"input": "completed", "a": "completed", "output": "completed"}

    tasks = client.get(f"/api/workflow-runs/{run['id']}/execution-tasks").json()
    assert len(tasks) == 2  # a + output
    assert all(task["status"] == "completed" for task in tasks)


def test_worker_retry_then_success(client, http_test_server, memory_db):
    _, factory = memory_db
    agent = client.post("/api/agents", json={"name": "Retry Agent", "endpoint": f"{http_test_server}/agent"}).json()
    workflow = client.post("/api/workflows", json={"name": "Queue Retry"}).json()
    graph = linear_graph(agent["id"])
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph}).status_code == 200
    assert client.post(f"/api/workflows/{workflow['id']}/versions", json={}).status_code == 201
    run = client.post(f"/api/workflows/{workflow['id']}/runs", json={}).json()
    client.post(f"/api/workflow-runs/{run['id']}/start")

    backend = make_backend(factory)
    scheduler = WorkflowScheduler(default_backoff_seconds=0)
    executor = FakeExecutor(fail_once={"a"})

    async def drive():
        worker_id = "retry-worker"
        for _ in range(10):
            await backend.promote_due_retries()
            task = await backend.claim(worker_id)
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id=worker_id, renew_interval=60.0)

    asyncio.run(drive())

    detail = client.get(f"/api/workflow-runs/{run['id']}").json()
    assert detail["status"] == "completed"
    assert executor.calls["a"] == 2


def test_worker_retry_exhausted_fails_run(client, http_test_server, memory_db):
    _, factory = memory_db
    agent = client.post("/api/agents", json={"name": "Fail Agent", "endpoint": f"{http_test_server}/agent"}).json()
    workflow = client.post("/api/workflows", json={"name": "Queue Fail"}).json()
    graph = linear_graph(agent["id"])
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph}).status_code == 200
    assert client.post(f"/api/workflows/{workflow['id']}/versions", json={}).status_code == 201
    run = client.post(f"/api/workflows/{workflow['id']}/runs", json={}).json()
    client.post(f"/api/workflow-runs/{run['id']}/start")

    backend = make_backend(factory)
    scheduler = WorkflowScheduler(default_backoff_seconds=0)
    executor = FakeExecutor(always_retryable=True)

    async def drive():
        worker_id = "fail-worker"
        for _ in range(10):
            await backend.promote_due_retries()
            task = await backend.claim(worker_id)
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id=worker_id, renew_interval=60.0)

    asyncio.run(drive())

    detail = client.get(f"/api/workflow-runs/{run['id']}").json()
    assert detail["status"] == "failed"
    tasks = client.get(f"/api/workflow-runs/{run['id']}/execution-tasks").json()
    failed = [task for task in tasks if task["payload"].get("node_id") == "a"]
    assert failed and failed[0]["status"] == "failed"
    assert failed[0]["attempt"] == 3  # max_attempts
