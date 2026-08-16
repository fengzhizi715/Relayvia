"""Run Trace events: the structured, durable record of Workflow execution."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, utc_now


class RunEventType(StrEnum):
    # Workflow lifecycle
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_WAITING = "workflow_waiting"
    WORKFLOW_RESUMED = "workflow_resumed"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    # Node lifecycle
    NODE_QUEUED = "node_queued"
    NODE_STARTED = "node_started"
    NODE_LOG = "node_log"
    NODE_RETRYING = "node_retrying"
    NODE_WAITING = "node_waiting"
    NODE_RESUMED = "node_resumed"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_SKIPPED = "node_skipped"
    NODE_CANCELLED = "node_cancelled"
    # Runtime semantics
    CONDITION_EVALUATED = "condition_evaluated"
    BRANCH_SELECTED = "branch_selected"


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        Index("ix_run_events_run_id", "workflow_run_id", "id"),
    )

    # Auto-increment id gives a stable, total order per Run (multiple Workers
    # may append concurrently). SQLite needs INTEGER for rowid autoincrement.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("node_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


def record_event(
    db,
    *,
    workflow_run_id: str,
    node_run_id: str | None = None,
    event_type: RunEventType,
    message: str | None = None,
    payload: dict | None = None,
) -> RunEvent:
    """Create a RunEvent inside the caller's transaction (atomic with the
    state change it accompanies)."""
    event = RunEvent(
        workflow_run_id=workflow_run_id,
        node_run_id=node_run_id,
        event_type=event_type.value,
        message=message,
        payload_json=payload or {},
    )
    db.add(event)
    return event


__all__ = ["RunEvent", "RunEventType", "record_event"]
