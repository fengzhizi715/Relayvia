"""Artifact persistent model.

An Artifact is the metadata record for a non-JSON / large output produced by a
Node. The physical content lives in an `ArtifactStorage`; the database only
stores metadata plus the `artifact://<id>` reference.
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, utc_now


class ArtifactType(StrEnum):
    FILE = "file"
    IMAGE = "image"
    VIDEO = "video"
    DATASET = "dataset"
    MODEL = "model"
    PATCH = "patch"
    REPORT = "report"
    OTHER = "other"


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    producer_node_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("node_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False, default=ArtifactType.FILE.value)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    uri: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


__all__ = ["Artifact", "ArtifactType"]
