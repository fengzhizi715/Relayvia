"""True concurrency test for safe task claiming.

Uses a file-backed SQLite database with independent connections per thread.
SQLite serializes writers (and the backend's conditional
`UPDATE ... WHERE status = 'pending'` guard guarantees exactly one winner), so
the invariant "one task, one owner" is verified under real threads. MySQL's
production guarantee comes from `FOR UPDATE SKIP LOCKED`.
"""

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
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus


def _seed(engine, graph: dict, n_tasks: int) -> list[str]:
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
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
            execution_snapshot_json={"schema_version": "1"},
            input_json={},
            variables_json={},
        )
        db.add(run)
        db.flush()
        node_run_ids = []
        for index in range(n_tasks):
            node_run = NodeRun(
                workflow_run_id=run.id,
                node_id=f"n{index}",
                node_type="agent",
                node_subtype="agent",
                node_name_snapshot=f"N{index}",
                status=NodeRunStatus.QUEUED.value,
                attempt=0,
            )
            db.add(node_run)
            db.flush()
            node_run_ids.append(node_run.id)
            db.add(
                ExecutionTask(
                    workflow_run_id=run.id,
                    node_run_id=node_run.id,
                    task_type="node_execution",
                    status="pending",
                    payload_json={"node_id": f"n{index}"},
                    priority=0,
                    attempt=0,
                    max_attempts=1,
                    execution_key=f"{run.id}:{node_run.id}",
                )
            )
        db.commit()
        return run.id


def _claim_once(factory, worker_id: str) -> str | None:
    backend = MySQLExecutionBackend(factory, lease_seconds=30)

    async def _run():
        return await backend.claim(worker_id)

    task = asyncio.run(_run())
    return task.id if task else None


@pytest.fixture()
def file_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'queue.db'}",
        connect_args={"timeout": 15},
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


def test_single_task_single_winner(file_db):
    graph = {"schema_version": "1.0", "nodes": [], "edges": [], "variables": {}, "metadata": {}}
    _seed(file_db, graph, n_tasks=1)

    factory_a = sessionmaker(bind=create_engine(f"sqlite:///{file_db.url.database}", connect_args={"timeout": 15}), autoflush=False, autocommit=False)
    factory_b = sessionmaker(bind=create_engine(f"sqlite:///{file_db.url.database}", connect_args={"timeout": 15}), autoflush=False, autocommit=False)

    results: list[str | None] = []
    barrier = threading.Barrier(2)

    def worker(factory, name):
        barrier.wait()
        results.append(_claim_once(factory, name))

    threads = [threading.Thread(target=worker, args=(factory_a, "wa")), threading.Thread(target=worker, args=(factory_b, "wb"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [result for result in results if result is not None]
    assert len(winners) == 1


def test_many_tasks_each_claimed_once(file_db):
    graph = {"schema_version": "1.0", "nodes": [], "edges": [], "variables": {}, "metadata": {}}
    _seed(file_db, graph, n_tasks=5)
    db_url = file_db.url.database

    factories = [
        sessionmaker(bind=create_engine(f"sqlite:///{db_url}", connect_args={"timeout": 15}), autoflush=False, autocommit=False)
        for _ in range(3)
    ]

    claimed: list[str] = []
    lock = threading.Lock()

    def worker(factory, name):
        while True:
            task_id = _claim_once(factory, name)
            if task_id is None:
                break
            with lock:
                claimed.append(task_id)

    threads = [threading.Thread(target=worker, args=(factory, f"w{i}")) for i, factory in enumerate(factories)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(claimed) == 5
    assert len(set(claimed)) == 5  # no double-claim
