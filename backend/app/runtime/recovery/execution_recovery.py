"""Periodic execution recovery.

- recover expired leases (CLAIMED/RUNNING past lease) back to PENDING
- promote due retries (RETRY_WAIT past available_at) back to PENDING
- reconcile active (RUNNING/PAUSED) runs so missed scheduling is repaired
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.runs.models import WorkflowRun
from app.infrastructure.execution_backend.base import ExecutionBackend
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import WorkflowRunStatus


async def run_execution_recovery(
    *,
    backend: ExecutionBackend,
    scheduler: WorkflowScheduler,
    session_factory: sessionmaker[Session],
    reconcile_active: bool = True,
) -> tuple[int, int]:
    expired = await backend.recover_expired()
    due = await backend.promote_due_retries()

    if reconcile_active:
        with session_factory() as db:
            active_ids = db.scalars(
                select(WorkflowRun.id).where(
                    WorkflowRun.status.in_([WorkflowRunStatus.RUNNING.value, WorkflowRunStatus.PAUSED.value])
                )
            ).all()
            for run_id in active_ids:
                scheduler.reconcile_run(db, run_id)
            db.commit()

    return expired, due
