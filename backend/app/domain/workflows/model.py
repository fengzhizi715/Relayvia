from enum import StrEnum
from uuid import uuid4

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.workflows.graph import GRAPH_SCHEMA_VERSION
from app.infrastructure.database.base import Base, TimestampMixin, utc_now


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Workflow(TimestampMixin, Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=WorkflowStatus.DRAFT.value, index=True)
    draft_graph_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    graph_schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default=GRAPH_SCHEMA_VERSION)
    current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    versions = relationship(
        "WorkflowVersion",
        back_populates="workflow",
        order_by="WorkflowVersion.version",
        passive_deletes=True,
    )


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflows.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default=GRAPH_SCHEMA_VERSION)
    graph_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    workflow = relationship("Workflow", back_populates="versions")


__all__ = ["Workflow", "WorkflowStatus", "WorkflowVersion"]
