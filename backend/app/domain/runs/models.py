"""WorkflowRun and NodeRun persistent models."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus


class WorkflowRun(TimestampMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_status_created", "status", "created_at"),
        Index("ix_workflow_runs_workflow_created", "workflow_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workflow_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=WorkflowRunStatus.CREATED.value, index=True)

    graph_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    graph_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    execution_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    variables_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    waiting_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    waiting_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    node_runs = relationship(
        "NodeRun",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="NodeRun.created_at",
    )


class NodeRun(TimestampMixin, Base):
    __tablename__ = "node_runs"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "node_id", name="uq_node_runs_workflow_node"),
        Index("ix_node_runs_run_status", "workflow_run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # `node_id` references WorkflowNode.id within the Run's Graph Snapshot.
    node_id: Mapped[str] = mapped_column(String(120), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    node_subtype: Mapped[str] = mapped_column(String(40), nullable=False)
    node_name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=NodeRunStatus.PENDING.value, index=True)

    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    execution_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    artifact_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    waiting_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    waiting_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow_run = relationship("WorkflowRun", back_populates="node_runs")


__all__ = ["NodeRun", "WorkflowRun"]
