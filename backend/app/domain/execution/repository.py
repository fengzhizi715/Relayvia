"""Persistence access for ExecutionTask."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.execution.models import ExecutionTask


def create_task(db: Session, task: ExecutionTask) -> ExecutionTask:
    db.add(task)
    db.flush()
    return task


def get_task(db: Session, task_id: str, *, lock: bool = False) -> ExecutionTask | None:
    query = select(ExecutionTask).where(ExecutionTask.id == task_id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def get_task_by_node_run(db: Session, node_run_id: str) -> ExecutionTask | None:
    return db.scalar(select(ExecutionTask).where(ExecutionTask.node_run_id == node_run_id))


def list_tasks_for_run(db: Session, workflow_run_id: str) -> list[ExecutionTask]:
    return list(
        db.scalars(
            select(ExecutionTask).where(ExecutionTask.workflow_run_id == workflow_run_id).order_by(ExecutionTask.created_at)
        ).all()
    )
