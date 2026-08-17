"""ExecutionTask persistent model (MySQL-backed Execution Queue)."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.execution.state_machine import ExecutionTaskStatus
from app.infrastructure.database.base import Base, TimestampMixin, utc_now


class ExecutionTask(TimestampMixin, Base):
    __tablename__ = "execution_tasks"
    __table_args__ = (
        UniqueConstraint("node_run_id", name="uq_execution_tasks_node_run"),
        Index("ix_execution_tasks_claim", "status", "available_at", "priority", "created_at"),
        Index("ix_execution_tasks_run", "workflow_run_id", "status"),
        Index("ix_execution_tasks_lease_expires", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    node_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("node_runs.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, default="node_execution")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ExecutionTaskStatus.PENDING.value, index=True)

    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Runner-targeted tasks: a specific runner id (optional) and the
    # capability required to execute it. Tasks with a required capability are
    # claimed by Runners, never by the server Worker.
    runner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("runners.id", ondelete="RESTRICT"), nullable=True, index=True)
    required_capability: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    execution_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["ExecutionTask"]
