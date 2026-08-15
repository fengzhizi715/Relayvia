from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin


class ServiceType(StrEnum):
    HTTP = "http"


class HTTPMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ServiceStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class Service(TimestampMixin, Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_type: Mapped[str] = mapped_column(String(32), nullable=False, default=ServiceType.HTTP.value)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    credential_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("credentials.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    health_check_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ServiceStatus.UNKNOWN.value, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    credential = relationship("Credential", back_populates="services")
    actions = relationship(
        "ServiceAction",
        back_populates="service",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ServiceAction.name",
    )


class ServiceAction(TimestampMixin, Base):
    __tablename__ = "service_actions"
    __table_args__ = (UniqueConstraint("service_id", "name", name="uq_service_actions_service_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False, default=HTTPMethod.POST.value)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    headers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    query_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    path_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    input_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    retry_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    service = relationship("Service", back_populates="actions")


__all__ = ["HTTPMethod", "Service", "ServiceAction", "ServiceStatus", "ServiceType"]

