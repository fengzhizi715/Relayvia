"""Public API contracts for the Workspace control-plane resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.workspaces.models import WorkspaceStatus, WorkspaceType


class WorkspaceRead(BaseModel):
    """A workspace record; no Runner credentials or command payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    runner_id: str | None
    repository: str
    path: str | None
    branch: str | None
    base_branch: str | None
    workspace_type: WorkspaceType
    status: WorkspaceStatus
    workflow_run_id: str
    node_run_id: str
    metadata: dict
    created_at: datetime
    updated_at: datetime
