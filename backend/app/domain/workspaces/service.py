"""Workspace service.

Creates the Workspace metadata record (status CREATING) at scheduling time.
Actual filesystem preparation happens on the Runner (git worktree add, path
validation); the Runner reports the resulting path back through the task
result and this service finalizes the record.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.workspaces.models import Workspace, WorkspaceStatus


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


def list_workspaces(db: Session, *, run_id: str | None = None) -> list[Workspace]:
    query = select(Workspace).order_by(Workspace.created_at)
    if run_id:
        query = query.where(Workspace.workflow_run_id == run_id)
    return list(db.scalars(query).all())


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
    if workspace.status == WorkspaceStatus.RELEASED.value:
        return workspace
    workspace.status = WorkspaceStatus.RELEASED.value
    db.commit()
    db.refresh(workspace)
    return workspace
