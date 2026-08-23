"""Regression coverage for bounded in-process Worker concurrency."""

import asyncio
import uuid

from app.domain.execution.models import ExecutionTask
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.runtime.executor.base import NodeExecutionContext, NodeExecutionResult, NodeExecutor
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.workers.workflow_worker import run_worker


def _graph() -> dict:
    nodes = [
        {
            "id": node_id,
            "type": "data",
            "subtype": "transform",
            "name": node_id,
            "position": {"x": index * 100, "y": 0},
            "config": {"mappings": {}},
            "input_mapping": {},
            "metadata": {},
        }
        for index, node_id in enumerate(("first", "second"))
    ]
    return {"schema_version": "1.0", "nodes": nodes, "edges": [], "variables": {}, "metadata": {}}


def _seed(factory) -> tuple[str, list[str]]:
    graph = _graph()
    with factory() as db:
        workflow = Workflow(name=f"worker-concurrency-{uuid.uuid4().hex[:8]}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
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
        task_ids: list[str] = []
        for node in graph["nodes"]:
            node_run = NodeRun(
                workflow_run_id=run.id,
                node_id=node["id"],
                node_type=node["type"],
                node_subtype=node["subtype"],
                node_name_snapshot=node["name"],
                status=NodeRunStatus.QUEUED.value,
                attempt=0,
            )
            db.add(node_run)
            db.flush()
            task = ExecutionTask(
                workflow_run_id=run.id,
                node_run_id=node_run.id,
                task_type="node_execution",
                status="pending",
                payload_json={"node_id": node["id"]},
                priority=0,
                attempt=0,
                max_attempts=1,
                execution_key=f"{run.id}:{node_run.id}",
            )
            db.add(task)
            db.flush()
            task_ids.append(task.id)
        db.commit()
        return run.id, task_ids


class BlockingExecutor(NodeExecutor):
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self._active = 0
        self.max_active = 0

    async def execute(self, _context: NodeExecutionContext) -> NodeExecutionResult:
        self._active += 1
        self.max_active = max(self.max_active, self._active)
        if self._active == 2:
            self.entered.set()
        try:
            await self.release.wait()
            return NodeExecutionResult(ok=True, output={})
        finally:
            self._active -= 1


def test_one_worker_processes_independent_tasks_concurrently(memory_db):
    _, factory = memory_db
    _run_id, task_ids = _seed(factory)

    async def scenario() -> None:
        executor = BlockingExecutor()
        stop = asyncio.Event()
        worker = asyncio.create_task(
            run_worker(
                executor,
                session_factory=factory,
                poll_interval=0.01,
                recovery_interval=3600,
                renew_interval=30,
                concurrency=2,
                worker_id="concurrency-test-worker",
                stop_event=stop,
            )
        )
        await asyncio.wait_for(executor.entered.wait(), timeout=1)
        assert executor.max_active == 2
        executor.release.set()
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(worker, timeout=1)

    asyncio.run(scenario())
    with factory() as db:
        tasks = [db.get(ExecutionTask, task_id) for task_id in task_ids]
        assert all(task is not None and task.status == "completed" for task in tasks)
