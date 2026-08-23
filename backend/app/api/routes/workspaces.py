"""Workspace API: minimal read + release (creation is Runtime/Manager-driven)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.domain.workspaces.models import Workspace, WorkspaceStatus
from app.domain.workspaces.schemas import WorkspaceRead
from app.domain.workspaces.service import get_workspace, list_workspaces, release_workspace
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _to_read(workspace: Workspace) -> WorkspaceRead:
    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        runner_id=workspace.runner_id,
        repository=workspace.repository,
        path=workspace.path,
        branch=workspace.branch,
        base_branch=workspace.base_branch,
        workspace_type=workspace.workspace_type,
        status=WorkspaceStatus(workspace.status),
        workflow_run_id=workspace.workflow_run_id,
        node_run_id=workspace.node_run_id,
        metadata=workspace.metadata_json,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.get("", response_model=list[WorkspaceRead])
def get_workspaces(run_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[WorkspaceRead]:
    return [_to_read(workspace) for workspace in list_workspaces(db, run_id=run_id)]


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace_detail(workspace_id: str, db: Session = Depends(get_db)) -> WorkspaceRead:
    return _to_read(get_workspace(db, workspace_id))


@router.post("/{workspace_id}/release", response_model=WorkspaceRead)
def post_release(workspace_id: str, db: Session = Depends(get_db)) -> WorkspaceRead:
    return _to_read(release_workspace(db, workspace_id))
