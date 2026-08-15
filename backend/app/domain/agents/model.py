from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin


class AgentConnectorType(StrEnum):
    HTTP = "http"
    LOCAL = "local"
    CUSTOM = "custom"


class AgentHTTPMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class AgentStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False, default=AgentConnectorType.HTTP.value)
    endpoint: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    http_method: Mapped[str] = mapped_column(String(10), nullable=False, default=AgentHTTPMethod.POST.value)
    health_check_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    headers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    runner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    input_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    credential_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("credentials.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=AgentStatus.UNKNOWN.value, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    credential = relationship("Credential", back_populates="agents")


__all__ = ["Agent", "AgentConnectorType", "AgentHTTPMethod", "AgentStatus"]

