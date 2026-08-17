"""Workspace persistent model.

A Workspace is the isolated working directory a Node executes in (local
repository, or a dedicated Git worktree). Metadata lives here; the actual
filesystem lives on the bound Runner machine and is prepared by the Runner.
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, utc_now


class WorkspaceType(StrEnum):
    LOCAL_REPOSITORY = "local_repository"
    GIT_WORKTREE = "git_worktree"


class WorkspaceStatus(StrEnum):
    CREATING = "creating"
    READY = "ready"
    IN_USE = "in_use"
    FAILED = "failed"
    RELEASED = "released"


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    runner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("runners.id", ondelete="RESTRICT"), nullable=True, index=True)
    repository: Mapped[str] = mapped_column(String(2048), nullable=False)
    path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workspace_type: Mapped[str] = mapped_column(String(32), nullable=False, default=WorkspaceType.GIT_WORKTREE.value)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=WorkspaceStatus.CREATING.value, index=True)
    workflow_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    node_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("node_runs.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


__all__ = ["Workspace", "WorkspaceStatus", "WorkspaceType"]
