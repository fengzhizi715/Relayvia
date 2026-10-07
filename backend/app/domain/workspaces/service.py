"""Workspace service.

Creates the Workspace metadata record (status CREATING) at scheduling time.
Actual filesystem preparation happens on the Runner (git worktree add, path
validation); the Runner reports the resulting path back through the task
result and this service finalizes the record.
"""

from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.runners.models import Runner
from app.domain.workspaces.models import Workspace, WorkspaceStatus
from app.infrastructure.database.base import utc_now


def workspace_branch(run_id: str, node_id: str) -> str:
    return f"relayvia/{run_id[:12]}/{node_id}"


def create_workspace(
    db: Session,
    *,
    workflow_run_id: str,
    node_run_id: str,
    node_id: str,
    name: str,
    repository: str,
    strategy: str,
    base_branch: str | None,
    runner_id: str | None = None,
) -> Workspace:
    workspace = Workspace(
        name=name,
        runner_id=runner_id,
        repository=repository,
        branch=workspace_branch(workflow_run_id, node_id),
        base_branch=base_branch,
        workspace_type=strategy,
        status=WorkspaceStatus.CREATING.value,
        workflow_run_id=workflow_run_id,
        node_run_id=node_run_id,
    )
    db.add(workspace)
    db.flush()
    return workspace


def get_workspace(db: Session, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise RelayviaError("WORKSPACE_NOT_FOUND", "Workspace not found", status_code=404)
    return workspace


def _workspace_filter_query(*, run_id: str | None = None):
    query = select(Workspace)
    if run_id:
        query = query.where(Workspace.workflow_run_id == run_id)
    return query


def list_workspaces(
    db: Session,
    *,
    run_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Workspace]:
    query = _workspace_filter_query(run_id=run_id).order_by(Workspace.created_at).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return list(db.scalars(query).all())


def count_workspaces(db: Session, *, run_id: str | None = None) -> int:
    query = select(func.count()).select_from(Workspace)
    if run_id:
        query = query.where(Workspace.workflow_run_id == run_id)
    return int(db.scalar(query) or 0)


def finalize_workspace(db: Session, workspace_id: str, *, path: str, branch: str | None, status: WorkspaceStatus) -> Workspace:
    """Runner reported the prepared workspace path; mark it READY/RELEASED."""
    workspace = get_workspace(db, workspace_id)
    workspace.path = path
    if branch:
        workspace.branch = branch
    workspace.status = status.value
    db.commit()
    db.refresh(workspace)
    return workspace


def release_workspace(db: Session, workspace_id: str) -> Workspace:
    workspace = get_workspace(db, workspace_id)
    if workspace.status in {WorkspaceStatus.CREATING.value, WorkspaceStatus.IN_USE.value}:
        raise RelayviaError(
            "WORKSPACE_ACTIVE",
            "An active Workspace cannot be released before its Runner task completes",
            status_code=409,
        )
    if workspace.status in {WorkspaceStatus.RELEASED.value, WorkspaceStatus.RELEASING.value, WorkspaceStatus.CLEANING.value}:
        return workspace
    if workspace.workspace_type in {"local", "local_repository"} or not workspace.path:
        workspace.status = WorkspaceStatus.RELEASED.value
    else:
        workspace.status = WorkspaceStatus.RELEASING.value
        workspace.metadata_json = {**(workspace.metadata_json or {}), "cleanup_requested_at": utc_now().isoformat()}
    db.commit()
    db.refresh(workspace)
    return workspace


def claim_workspace_cleanup(db: Session, runner: Runner, *, stale_after_seconds: int) -> Workspace | None:
    stale_before = utc_now() - timedelta(seconds=stale_after_seconds)
    workspace = db.scalar(
        select(Workspace)
        .where(
            Workspace.runner_id == runner.id,
            or_(
                Workspace.status == WorkspaceStatus.RELEASING.value,
                (Workspace.status == WorkspaceStatus.CLEANING.value) & (Workspace.updated_at < stale_before),
            ),
        )
        .order_by(Workspace.updated_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if workspace is None:
        return None
    workspace.status = WorkspaceStatus.CLEANING.value
    workspace.metadata_json = {**(workspace.metadata_json or {}), "cleanup_started_at": utc_now().isoformat()}
    db.commit()
    db.refresh(workspace)
    return workspace


def complete_workspace_cleanup(db: Session, runner: Runner, workspace_id: str, *, ok: bool, error: str | None) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    if workspace is None:
        raise RelayviaError("WORKSPACE_NOT_FOUND", "Workspace not found", status_code=404)
    if workspace.runner_id != runner.id:
        raise RelayviaError("WORKSPACE_RUNNER_MISMATCH", "Workspace is bound to another Runner", status_code=409)
    if workspace.status not in {WorkspaceStatus.CLEANING.value, WorkspaceStatus.RELEASING.value, WorkspaceStatus.IN_USE.value}:
        if workspace.status == WorkspaceStatus.RELEASED.value and ok:
            return workspace
        raise RelayviaError("WORKSPACE_CLEANUP_NOT_PENDING", "Workspace cleanup is not pending", status_code=409)
    metadata = dict(workspace.metadata_json or {})
    metadata["cleanup_finished_at"] = utc_now().isoformat()
    if error:
        metadata["cleanup_error"] = error[:1000]
    else:
        metadata.pop("cleanup_error", None)
    workspace.metadata_json = metadata
    workspace.status = (WorkspaceStatus.RELEASED if ok else WorkspaceStatus.CLEANUP_FAILED).value
    db.commit()
    db.refresh(workspace)
    return workspace
