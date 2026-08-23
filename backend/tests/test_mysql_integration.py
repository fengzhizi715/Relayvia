"""Opt-in MySQL 8 integration coverage for the durable queue.

Run only against a disposable database whose name ends in `_test` after
`alembic upgrade head`; the test deliberately does not create tables itself.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.domain.execution.models import ExecutionTask
from app.domain.execution.state_machine import ExecutionTaskStatus
from app.domain.runs.models import NodeRun, WorkflowRun
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
