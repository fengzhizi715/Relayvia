"""Public API contracts for the Workspace control-plane resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.workspaces.models import WorkspaceStatus


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
    # Older persisted records may use the explicit names
    # ``local_repository`` / ``git_worktree`` while the runtime currently
    # writes ``local`` / ``worktree``. Keep the read contract compatible until
    # a dedicated storage migration normalizes historical values.
    workspace_type: str
    status: WorkspaceStatus
    workflow_run_id: str
    node_run_id: str
    metadata: dict
    created_at: datetime
    updated_at: datetime
