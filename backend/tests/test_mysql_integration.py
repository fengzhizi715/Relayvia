"""Opt-in MySQL 8 integration coverage for the durable queue.

Run only against a disposable database whose name ends in `_test` after
`alembic upgrade head`; the test deliberately does not create tables itself.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import time
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.domain.execution.models import ExecutionTask
from app.domain.execution.state_machine import ExecutionTaskStatus
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.runs.service import cancel_run
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.database.base import utc_now
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus


MYSQL_TEST_URL = os.getenv("RELAYVIA_MYSQL_TEST_URL")
pytestmark = [
    pytest.mark.mysql,
    pytest.mark.skipif(not MYSQL_TEST_URL, reason="set RELAYVIA_MYSQL_TEST_URL to run MySQL 8 integration tests"),
]


def test_mysql_8_claim_uses_migrated_schema_and_fences_one_owner():
    url = make_url(MYSQL_TEST_URL)
    if not (url.database or "").endswith("_test"):
        pytest.fail("RELAYVIA_MYSQL_TEST_URL must target a disposable database ending in '_test'")
    engine = create_engine(MYSQL_TEST_URL)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid.uuid4().hex[:12]
    workflow_id = version_id = run_id = node_id = task_id = None
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        with factory() as db:
            workflow = Workflow(name=f"mysql-{suffix}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
            db.add(workflow)
            db.flush()
            version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json={})
            db.add(version)
            db.flush()
            run = WorkflowRun(workflow_id=workflow.id, workflow_version_id=version.id, version_number=1, status=WorkflowRunStatus.RUNNING.value, graph_schema_version="1.0", graph_snapshot_json={}, execution_snapshot_json={}, input_json={}, variables_json={})
            db.add(run)
            db.flush()
            node = NodeRun(workflow_run_id=run.id, node_id="node", node_type="data", node_subtype="transform", node_name_snapshot="node", status=NodeRunStatus.QUEUED.value)
            db.add(node)
            db.flush()
            task = ExecutionTask(workflow_run_id=run.id, node_run_id=node.id, status=ExecutionTaskStatus.PENDING.value, payload_json={"node_id": "node"}, available_at=utc_now(), execution_key=f"{run.id}:{node.id}")
            db.add(task)
            db.commit()
            workflow_id, version_id, run_id, node_id, task_id = workflow.id, version.id, run.id, node.id, task.id

        backend = MySQLExecutionBackend(factory)
        first = asyncio.run(backend.claim("mysql-worker-a"))
        second = asyncio.run(backend.claim("mysql-worker-b"))
        assert first is not None and first.id == task_id
        assert second is None
    finally:
        if workflow_id:
            with factory() as db:
                if task_id:
                    db.query(ExecutionTask).filter(ExecutionTask.id == task_id).delete()
                if node_id:
                    db.query(NodeRun).filter(NodeRun.id == node_id).delete()
                if run_id:
                    db.query(WorkflowRun).filter(WorkflowRun.id == run_id).delete()
                if version_id:
                    db.query(WorkflowVersion).filter(WorkflowVersion.id == version_id).delete()
                db.query(Workflow).filter(Workflow.id == workflow_id).delete()
                db.commit()
        engine.dispose()


def test_mysql_8_concurrent_claims_cancel_race_and_lease_recovery():
    """Exercise the queue with independent real MySQL connections.

    This intentionally covers behavior SQLite cannot model: concurrent row
    locks, SKIP LOCKED polling, cancellation lock ordering and expired leases.
    """
    url = make_url(MYSQL_TEST_URL)
    if not (url.database or "").endswith("_test"):
        pytest.fail("RELAYVIA_MYSQL_TEST_URL must target a disposable database ending in '_test'")
    engine = create_engine(MYSQL_TEST_URL, pool_size=8, max_overflow=0)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    ids: dict[str, object] = {"tasks": [], "nodes": []}
    try:
        suffix = uuid.uuid4().hex[:12]
        with factory() as db:
            workflow = Workflow(name=f"mysql-concurrent-{suffix}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
            db.add(workflow)
            db.flush()
            version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json={})
            db.add(version)
            db.flush()
            run = WorkflowRun(workflow_id=workflow.id, workflow_version_id=version.id, version_number=1, status=WorkflowRunStatus.RUNNING.value, graph_schema_version="1.0", graph_snapshot_json={}, execution_snapshot_json={}, input_json={}, variables_json={})
            db.add(run)
            db.flush()
            for index in range(4):
                node = NodeRun(workflow_run_id=run.id, node_id=f"node-{index}", node_type="data", node_subtype="transform", node_name_snapshot=f"node-{index}", status=NodeRunStatus.QUEUED.value)
                db.add(node)
                db.flush()
                task = ExecutionTask(workflow_run_id=run.id, node_run_id=node.id, status=ExecutionTaskStatus.PENDING.value, payload_json={"node_id": node.node_id}, available_at=utc_now(), execution_key=f"{run.id}:{node.id}")
                db.add(task)
                db.flush()
                ids["nodes"].append(node.id)
                ids["tasks"].append(task.id)
            db.commit()
            ids.update(workflow=workflow.id, version=version.id, run=run.id)

        backend = MySQLExecutionBackend(factory, lease_seconds=1)

        def claim_until_owned(worker: str):
            for _ in range(20):
                claimed = asyncio.run(backend.claim(worker))
                if claimed is not None:
                    return claimed
                time.sleep(0.01)
            return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            claimed = list(pool.map(claim_until_owned, [f"mysql-worker-{i}" for i in range(4)]))
        assert all(item is not None for item in claimed)
        assert len({item.id for item in claimed}) == 4

        first = claimed[0]
        assert asyncio.run(backend.start(first.id, first.locked_by, first.lease_token))

        with factory() as db:
            task = db.get(ExecutionTask, first.id)
            task.lease_expires_at = utc_now().replace(year=2000)
            db.commit()
        assert asyncio.run(backend.recover_expired()) == 1
        recovered = claim_until_owned("mysql-worker-recovery")
        assert recovered is not None and recovered.id == first.id

        def cancel_parent():
            with factory() as db:
                return cancel_run(db, ids["run"])

        def renew_or_start_sibling():
            item = claimed[1]
            return asyncio.run(backend.start(item.id, item.locked_by, item.lease_token))

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [pool.submit(cancel_parent), pool.submit(renew_or_start_sibling)]
            [future.result(timeout=10) for future in outcomes]

        with factory() as db:
            assert db.get(WorkflowRun, ids["run"]).status == WorkflowRunStatus.CANCELLED.value
            assert all(
                db.get(ExecutionTask, task_id).status == ExecutionTaskStatus.CANCELLED.value
                for task_id in ids["tasks"]
            )

    finally:
        if ids.get("workflow"):
            with factory() as db:
                db.query(ExecutionTask).filter(ExecutionTask.id.in_(ids["tasks"])).delete(synchronize_session=False)
                db.query(NodeRun).filter(NodeRun.id.in_(ids["nodes"])).delete(synchronize_session=False)
                db.query(WorkflowRun).filter(WorkflowRun.id == ids["run"]).delete()
                db.query(WorkflowVersion).filter(WorkflowVersion.id == ids["version"]).delete()
                db.query(Workflow).filter(Workflow.id == ids["workflow"]).delete()
                db.commit()
        engine.dispose()
