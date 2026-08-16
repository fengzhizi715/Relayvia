"""Persistence access for WorkflowRun / NodeRun."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.runs.models import NodeRun, WorkflowRun
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus


def create_run(db: Session, run: WorkflowRun) -> WorkflowRun:
    db.add(run)
    db.flush()
    return run


def create_node_run(db: Session, node_run: NodeRun) -> NodeRun:
    db.add(node_run)
    db.flush()
    return node_run


def get_run(db: Session, run_id: str, *, lock: bool = False) -> WorkflowRun | None:
    query = select(WorkflowRun).where(WorkflowRun.id == run_id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def list_runs(
    db: Session,
    *,
    workflow_id: str | None = None,
    status: WorkflowRunStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[WorkflowRun]:
    query = select(WorkflowRun).order_by(WorkflowRun.created_at.desc())
    if workflow_id:
        query = query.where(WorkflowRun.workflow_id == workflow_id)
    if status:
        query = query.where(WorkflowRun.status == status.value)
    query = query.limit(limit).offset(offset)
    return list(db.scalars(query).all())


def get_node_run(db: Session, run_id: str, node_run_id: str) -> NodeRun | None:
    return db.scalar(
        select(NodeRun).where(NodeRun.id == node_run_id, NodeRun.workflow_run_id == run_id)
    )


def list_node_runs(db: Session, run_id: str) -> list[NodeRun]:
    return list(
        db.scalars(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id).order_by(NodeRun.created_at)
        ).all()
    )


def get_run_with_node_runs(db: Session, run_id: str) -> WorkflowRun | None:
    return db.scalar(
        select(WorkflowRun).options(selectinload(WorkflowRun.node_runs)).where(WorkflowRun.id == run_id)
    )


def list_pending_node_runs(db: Session, run_id: str) -> list[NodeRun]:
    return list(
        db.scalars(
            select(NodeRun)
            .where(NodeRun.workflow_run_id == run_id, NodeRun.status == NodeRunStatus.PENDING.value)
        ).all()
    )
