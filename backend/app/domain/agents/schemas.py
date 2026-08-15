from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.agents.model import AgentConnectorType, AgentHTTPMethod, AgentStatus


class Capability(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    connector_type: AgentConnectorType = AgentConnectorType.HTTP
    endpoint: str | None = None
    http_method: AgentHTTPMethod = AgentHTTPMethod.POST
    health_check_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    runner_id: str | None = None
    capabilities: list[Capability] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    credential_id: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    connector_type: AgentConnectorType | None = None
    endpoint: str | None = None
    http_method: AgentHTTPMethod | None = None
    health_check_url: str | None = None
    headers: dict[str, str] | None = None
    runner_id: str | None = None
    capabilities: list[Capability] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    credential_id: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    connector_type: AgentConnectorType
    endpoint: str | None
    http_method: AgentHTTPMethod
    health_check_url: str | None
    headers: dict[str, str]
    runner_id: str | None
    capabilities: list[Capability]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    credential_id: str | None
    credential_name: str | None
    timeout_seconds: int
    status: AgentStatus
    enabled: bool
    metadata: dict[str, Any]
    last_checked_at: datetime | None
    last_latency_ms: int | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

