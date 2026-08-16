"""Relayvia Workflow Worker.

Standalone process: `python -m app.workers.workflow_worker`.

The Worker only executes tasks that already entered the Execution Queue. It
does NOT scan NodeRuns to decide Workflow steps (that is the Scheduler's job).
It claims under a lease with token fencing, executes via a NodeExecutor
boundary, and reports results back to the Queue / NodeRun / WorkflowRun.

Delivery: durable at-least-once. If a Worker crashes mid-execution the lease
expires and the task is recovered and may run again.
"""

import asyncio
import os
import signal
import socket
import time
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.domain.artifacts.service import register_artifact_candidates
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.graph import parse_workflow_graph
from app.infrastructure.artifact_storage import ArtifactStorage, get_artifact_storage
from app.infrastructure.database.base import utc_now
from app.infrastructure.database.session import get_session_factory
from app.infrastructure.execution_backend.base import ClaimedTask, ExecutionBackend
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.context import ContextResolver, UnresolvedContextReference
from app.runtime.executor.base import NodeExecutionContext, NodeExecutionResult, NodeExecutor
from app.runtime.executor.default import DefaultNodeExecutor
from app.runtime.executor.result import ExecutionError
from app.runtime.executor.trace import sanitize_artifacts, sanitize_error, sanitize_metadata
from app.runtime.recovery.execution_recovery import run_execution_recovery
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import WorkflowRunStatus


def _worker_id() -> str:
    return f"worker_{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex[:8]}"


def _build_execution_context(session_factory: sessionmaker[Session], task: ClaimedTask) -> NodeExecutionContext:
    with session_factory() as db:
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == task.workflow_run_id))
        if run is None:
            raise ExecutionError("WORKFLOW_RUN_MISSING", "WorkflowRun disappeared during execution", retryable=False)
        graph = parse_workflow_graph(run.graph_snapshot_json)
        node = next((node for node in graph.nodes if node.id == task.payload.get("node_id")), None)
        if node is None:
            raise ExecutionError("NODE_MISSING", "Node not found in Graph Snapshot", retryable=False, details={"node_id": task.payload.get("node_id")})
        node_runs = db.scalars(select(NodeRun).where(NodeRun.workflow_run_id == run.id)).all()
        completed = {node_run.node_id: node_run.output_json for node_run in node_runs if node_run.output_json is not None}
        resolver = ContextResolver(
            workflow_input=run.input_json,
            variables=run.variables_json,
            node_outputs=completed,
            run={"id": run.id, "status": run.status, "created_at": run.created_at.isoformat() if run.created_at else None},
        )
        resolved_input = resolver.resolve(node.input_mapping)
        # Persist the resolved input for Run Trace. Credentials never reach
        # this value: they are injected separately by the Connector layer.
        node_run = db.get(NodeRun, task.node_run_id)
        if node_run is not None:
            node_run.input_json = resolved_input
            db.commit()
        return NodeExecutionContext(
            workflow_run_id=run.id,
            node_run_id=task.node_run_id,
            node_id=node.id,
            node_definition=node.model_dump(mode="json"),
            resolved_config=resolver.resolve(node.config),
            resolved_input=resolved_input,
            execution_snapshot=run.execution_snapshot_json,
            attempt=task.attempt,
            execution_key=task.execution_key,
        )


def _reconcile_after(session_factory: sessionmaker[Session], scheduler: WorkflowScheduler, run_id: str) -> None:
    with session_factory() as db:
        scheduler.reconcile_run(db, run_id)
        db.commit()


def _waiting_for(context: NodeExecutionContext) -> tuple[str, dict] | None:
    """Waiting-type nodes are parked, not executed: Human Approval / Human
    Input park until an API action; Wait parks until resume_at passes."""
    node = context.node_definition
    if node["type"] == "human":
        if node["subtype"] == "approval":
            return ("HUMAN_APPROVAL", {})
        if node["subtype"] == "input":
            return ("HUMAN_INPUT", {})
    if node["type"] == "logic" and node["subtype"] == "wait":
        try:
            duration = max(int(context.resolved_config.get("duration_seconds") or 0), 1)
        except (TypeError, ValueError):
            duration = 1
        resume_at = utc_now() + timedelta(seconds=duration)
        return ("WAIT_TIMER", {"resume_at": resume_at.isoformat(), "duration_seconds": duration})
    return None


async def _renew_loop(backend: ExecutionBackend, task: ClaimedTask, worker_id: str, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await backend.renew_lease(task.id, worker_id, task.lease_token)
        except Exception:
            return


async def _process_task(
    task: ClaimedTask,
    *,
    backend: ExecutionBackend,
    scheduler: WorkflowScheduler,
    session_factory: sessionmaker[Session],
    executor: NodeExecutor,
    worker_id: str,
    renew_interval: float,
    storage: ArtifactStorage | None = None,
) -> None:
    started = await backend.start(task.id, worker_id, task.lease_token)
    if not started:
        return

    try:
        context = _build_execution_context(session_factory, task)
    except UnresolvedContextReference as exc:
        await backend.fail(task.id, worker_id, task.lease_token, sanitize_error({"code": "UNRESOLVED_CONTEXT_REFERENCE", "message": exc.message, "retryable": False, "details": {"reference": exc.reference}}))
        _reconcile_after(session_factory, scheduler, task.workflow_run_id)
        return
    except ExecutionError as exc:
        await backend.fail(task.id, worker_id, task.lease_token, sanitize_error(exc.to_dict()))
        _reconcile_after(session_factory, scheduler, task.workflow_run_id)
        return

    waiting = _waiting_for(context)
    if waiting is not None:
        await backend.wait_node(
            task.id,
            worker_id,
            task.lease_token,
            waiting_reason=waiting[0],
            waiting_metadata=waiting[1],
        )
        _reconcile_after(session_factory, scheduler, task.workflow_run_id)
        return

    renewer = asyncio.create_task(_renew_loop(backend, task, worker_id, renew_interval))
    try:
        result = await executor.execute(context)
    except ExecutionError as exc:
        result = NodeExecutionResult(ok=False, retryable=exc.retryable, error=exc)
    except Exception as exc:  # pragma: no cover - defensive
        result = NodeExecutionResult(ok=False, retryable=False, error=ExecutionError("EXECUTOR_ERROR", str(exc)))
    finally:
        renewer.cancel()

    if result.ok:
        output = dict(result.output or {})
        artifact_refs: list[dict] = []
        if result.artifacts:
            with session_factory() as db:
                artifact_refs, output_keys = register_artifact_candidates(
                    db,
                    workflow_run_id=task.workflow_run_id,
                    producer_node_run_id=task.node_run_id,
                    candidates=result.artifacts,
                    storage=storage or get_artifact_storage(),
                )
                db.commit()
            output.update(output_keys)
        await backend.complete(
            task.id,
            worker_id,
            task.lease_token,
            output,
            execution_metadata=sanitize_metadata(result.metadata),
            artifacts=sanitize_artifacts(artifact_refs),
        )
        _reconcile_after(session_factory, scheduler, task.workflow_run_id)
    elif result.retryable and task.attempt + 1 < task.max_attempts:
        await backend.schedule_retry(
            task.id,
            worker_id,
            task.lease_token,
            _retry_backoff_seconds(task.payload, scheduler.default_backoff_seconds),
        )
    else:
        error = result.error.to_dict() if result.error else {"code": "UNKNOWN", "message": "execution failed", "retryable": False, "details": {}}
        await backend.fail(
            task.id,
            worker_id,
            task.lease_token,
            sanitize_error(error),
            execution_metadata=sanitize_metadata(result.metadata),
            artifacts=sanitize_artifacts(result.artifacts),
        )
        _reconcile_after(session_factory, scheduler, task.workflow_run_id)


def _retry_backoff_seconds(payload: dict, default: int) -> int:
    """Read the scheduler-owned backoff from a task payload defensively."""
    try:
        return max(0, min(int(payload.get("retry_backoff_seconds", default)), 86_400))
    except (AttributeError, TypeError, ValueError):
        return max(0, min(default, 86_400))


async def run_worker(
    executor: NodeExecutor | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    poll_interval: float | None = None,
    lease_seconds: int | None = None,
    renew_interval: float | None = None,
    recovery_interval: float | None = None,
    worker_id: str | None = None,
    storage: ArtifactStorage | None = None,
) -> None:
    settings = get_settings()
    session_factory = session_factory or get_session_factory()
    worker_id = worker_id or settings.worker_id or _worker_id()
    poll_interval = poll_interval if poll_interval is not None else settings.worker_poll_interval
    lease_seconds = lease_seconds if lease_seconds is not None else settings.worker_lease_seconds
    renew_interval = renew_interval if renew_interval is not None else settings.worker_lease_renew_interval
    recovery_interval = recovery_interval if recovery_interval is not None else settings.worker_recovery_interval

    backend = MySQLExecutionBackend(session_factory, lease_seconds=lease_seconds)
    scheduler = WorkflowScheduler()
    executor = executor or DefaultNodeExecutor(session_factory)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            break

    last_recovery = 0.0
    while not stop.is_set():
        now = time.monotonic()
        if now - last_recovery >= recovery_interval:
            await run_execution_recovery(backend=backend, scheduler=scheduler, session_factory=session_factory)
            last_recovery = now

        task = await backend.claim(worker_id)
        if task is None:
            await asyncio.sleep(poll_interval)
            continue
        await _process_task(
            task,
            backend=backend,
            scheduler=scheduler,
            session_factory=session_factory,
            executor=executor,
            worker_id=worker_id,
            renew_interval=renew_interval,
            storage=storage,
        )


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
