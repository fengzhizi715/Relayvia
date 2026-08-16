"""Phase 10: Condition / Parallel / Merge runtime + scheduling tests."""

import asyncio
import threading
import uuid

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.domain.execution.models import ExecutionTask
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.database.base import Base
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.default import DefaultNodeExecutor, _evaluate_expression
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
            task = await backend.claim("phase10-worker")
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="phase10-worker", renew_interval=60.0)

    asyncio.run(_drive())


def condition_merge_graph(expression: dict) -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "condition", "type": "logic", "subtype": "condition", "name": "Condition", "position": {"x": 100, "y": 0}, "config": {"expression": expression}, "input_mapping": {}, "metadata": {}},
            {"id": "true_agent", "type": "agent", "subtype": "agent", "name": "True Agent", "position": {"x": 200, "y": -80}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "false_agent", "type": "agent", "subtype": "agent", "name": "False Agent", "position": {"x": 200, "y": 80}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "merge", "type": "logic", "subtype": "merge", "name": "Merge", "position": {"x": 300, "y": 0}, "config": {"strategy": "all"}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 400, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "condition", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "condition", "target": "true_agent", "source_handle": "true", "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "condition", "target": "false_agent", "source_handle": "false", "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e4", "source": "true_agent", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e5", "source": "false_agent", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e6", "source": "merge", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def parallel_merge_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "parallel", "type": "logic", "subtype": "parallel", "name": "Parallel", "position": {"x": 100, "y": 0}, "config": {}, "input_mapping": {}, "metadata": {}},
            {"id": "a", "type": "agent", "subtype": "agent", "name": "Agent A", "position": {"x": 200, "y": -80}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "b", "type": "agent", "subtype": "agent", "name": "Agent B", "position": {"x": 200, "y": 80}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "merge", "type": "logic", "subtype": "merge", "name": "Merge", "position": {"x": 300, "y": 0}, "config": {"strategy": "all"}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 400, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "parallel", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "parallel", "target": "a", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "parallel", "target": "b", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e4", "source": "a", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e5", "source": "b", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e6", "source": "merge", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def node_statuses(factory, run_id) -> dict:
    with factory() as db:
        rows = db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run_id)).all()
        return {row.node_id: NodeRunStatus(row.status) for row in rows}


def task_count_for(factory, run_id, node_id: str) -> int:
    with factory() as db:
        rows = db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run_id)).all()
        tasks = db.scalars(select(__import__("app.domain.execution.models", fromlist=["ExecutionTask"]).ExecutionTask).where(
            __import__("app.domain.execution.models", fromlist=["ExecutionTask"]).ExecutionTask.workflow_run_id == run_id
        )).all()
    node_run_ids = {row.id: row.node_id for row in rows}
    return sum(1 for task in tasks if node_run_ids.get(task.node_run_id) == node_id)


# --- Condition expression evaluation (unit) ---


def test_expression_and_or_evaluation():
    assert _evaluate_expression({"left": 5, "operator": ">", "right": 3}) is True
    assert _evaluate_expression({"and": [{"left": 1, "operator": ">", "right": 0}, {"left": 2, "operator": "<", "right": 3}]}) is True
    assert _evaluate_expression({"and": [{"left": 1, "operator": "==", "right": 2}, {"left": 2, "operator": "<", "right": 3}]}) is False
    assert _evaluate_expression({"or": [{"left": 1, "operator": "==", "right": 2}, {"left": 2, "operator": "<", "right": 3}]}) is True
    assert _evaluate_expression({"or": [{"left": 1, "operator": "==", "right": 2}]}) is False


# --- Condition selects only one branch ---


def test_condition_true_branch_executes(memory_db, http_test_server):
    _, factory = memory_db
    expression = {"left": "{{workflow.input.score}}", "operator": ">=", "right": 0.8}
    with factory() as db:
        run = make_run(db, condition_merge_graph(expression), registry_snapshot(http_test_server))
        run.input_json = {"score": 0.9}
        db.commit()
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)

    statuses = node_statuses(factory, run_id)
    assert statuses["condition"] == NodeRunStatus.COMPLETED.value
    assert statuses["true_agent"] == NodeRunStatus.COMPLETED.value
    assert statuses["false_agent"] == NodeRunStatus.SKIPPED.value
    assert statuses["merge"] == NodeRunStatus.COMPLETED.value
    assert statuses["output"] == NodeRunStatus.COMPLETED.value
    with factory() as db:
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value


def test_condition_false_branch_executes(memory_db, http_test_server):
    _, factory = memory_db
    expression = {"left": "{{workflow.input.score}}", "operator": ">=", "right": 0.8}
    with factory() as db:
        run = make_run(db, condition_merge_graph(expression), registry_snapshot(http_test_server))
        run.input_json = {"score": 0.5}
        db.commit()
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)

    statuses = node_statuses(factory, run_id)
    assert statuses["true_agent"] == NodeRunStatus.SKIPPED.value
    assert statuses["false_agent"] == NodeRunStatus.COMPLETED.value
    assert statuses["merge"] == NodeRunStatus.COMPLETED.value
    with factory() as db:
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value


# --- Condition + Merge: unselected branch does not block ---


def test_condition_merge_waits_only_active_branch(memory_db, http_test_server):
    _, factory = memory_db
    expression = {"left": True, "operator": "==", "right": True}
    with factory() as db:
        run = make_run(db, condition_merge_graph(expression), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)

    statuses = node_statuses(factory, run_id)
    assert statuses["true_agent"] == NodeRunStatus.COMPLETED.value
    assert statuses["false_agent"] == NodeRunStatus.SKIPPED.value
    assert statuses["merge"] == NodeRunStatus.COMPLETED.value
    with factory() as db:
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value


# --- Parallel + Merge: both branches run, merge scheduled once ---


def test_parallel_merge_runs_all_branches_and_schedules_merge_once(memory_db, http_test_server):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, parallel_merge_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)

    statuses = node_statuses(factory, run_id)
    assert statuses["parallel"] == NodeRunStatus.COMPLETED.value
    assert statuses["a"] == NodeRunStatus.COMPLETED.value
    assert statuses["b"] == NodeRunStatus.COMPLETED.value
    assert statuses["merge"] == NodeRunStatus.COMPLETED.value
    assert statuses["output"] == NodeRunStatus.COMPLETED.value
    with factory() as db:
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value
    assert task_count_for(factory, run_id, "merge") == 1


def test_merge_scheduling_is_idempotent_across_reconciles(memory_db, http_test_server):
    """Simulate two workers each reconciling after completing a branch."""
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, parallel_merge_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    backend = MySQLExecutionBackend(factory)

    def complete_node(node_id: str) -> None:
        async def _complete():
            task = await backend.claim("w")
            assert task is not None
            await backend.start(task.id, "w", task.lease_token)
            await backend.complete(task.id, "w", task.lease_token, {"node": node_id})
            with factory() as db:
                scheduler.reconcile_run(db, run_id)
                db.commit()

        asyncio.run(_complete())

    # First reconcile schedules parallel; complete parallel, then a and b.
    complete_node("parallel")
    complete_node("a")
    complete_node("b")

    with factory() as db:
        tasks = db.scalars(select(__import__("app.domain.execution.models", fromlist=["ExecutionTask"]).ExecutionTask).where(
            __import__("app.domain.execution.models", fromlist=["ExecutionTask"]).ExecutionTask.workflow_run_id == run_id
        )).all()
        node_runs = {row.id: row.node_id for row in db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run_id)).all()}
    merge_tasks = [task for task in tasks if node_runs.get(task.node_run_id) == "merge"]
    assert len(merge_tasks) == 1


# --- Concurrent branch completion must schedule Merge exactly once ---


@pytest.fixture()
def file_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase10.db'}",
        connect_args={"timeout": 20},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_concurrent_branch_completion_schedules_merge_once(file_db, http_test_server):
    url = file_db.url.database
    factory = sessionmaker(bind=create_engine(f"sqlite:///{url}", connect_args={"timeout": 20}), autoflush=False, autocommit=False)
    with factory() as db:
        run = make_run(db, parallel_merge_graph(), registry_snapshot(http_test_server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    # Process the Parallel node so that branch tasks exist.
    backend = MySQLExecutionBackend(factory)

    async def _complete_parallel():
        task = await backend.claim("w")
        await backend.start(task.id, "w", task.lease_token)
        await backend.complete(task.id, "w", task.lease_token, {})
        with factory() as db:
            scheduler.reconcile_run(db, run_id)
            db.commit()

    asyncio.run(_complete_parallel())

    factory_a = sessionmaker(bind=create_engine(f"sqlite:///{url}", connect_args={"timeout": 20}), autoflush=False, autocommit=False)
    factory_b = sessionmaker(bind=create_engine(f"sqlite:///{url}", connect_args={"timeout": 20}), autoflush=False, autocommit=False)
    scheduler = WorkflowScheduler(default_max_attempts=1)

    def branch_worker(worker_factory):
        backend = MySQLExecutionBackend(worker_factory)
        executor = DefaultNodeExecutor(worker_factory)

        async def _run():
            for _ in range(50):
                task = await backend.claim("conc-worker")
                if task is None:
                    await asyncio.sleep(0.02)
                    continue
                await _process_task(task, backend=backend, scheduler=scheduler, session_factory=worker_factory, executor=executor, worker_id="conc-worker", renew_interval=60.0)
                return

        asyncio.run(_run())

    threads = [threading.Thread(target=branch_worker, args=(factory_a,)), threading.Thread(target=branch_worker, args=(factory_b,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with factory() as db:
        tasks = db.scalars(select(ExecutionTask).where(ExecutionTask.workflow_run_id == run_id)).all()
        node_runs = {row.id: row.node_id for row in db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run_id)).all()}
        statuses = {row.node_id: NodeRunStatus(row.status) for row in db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run_id)).all()}
    merge_tasks = [task for task in tasks if node_runs.get(task.node_run_id) == "merge"]
    assert len(merge_tasks) == 1  # concurrent completion scheduled Merge exactly once
    assert statuses["a"] == NodeRunStatus.COMPLETED.value
    assert statuses["b"] == NodeRunStatus.COMPLETED.value

    # Finish remaining queued work (merge, output) on a single worker.
    drive(factory, scheduler)
    with factory() as db:
        statuses = {row.node_id: NodeRunStatus(row.status) for row in db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run_id)).all()}
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value
    assert statuses["merge"] == NodeRunStatus.COMPLETED.value
