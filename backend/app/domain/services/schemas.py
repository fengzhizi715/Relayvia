from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.services.model import HTTPMethod, ServiceStatus, ServiceType


class RetryPolicy(BaseModel):
    max_retries: int = Field(default=0, ge=0, le=10)
    backoff_seconds: int = Field(default=0, ge=0, le=86400)
    retry_on_status: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    service_type: ServiceType = ServiceType.HTTP
    base_url: str
    credential_id: str | None = None
    health_check_url: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    service_type: ServiceType | None = None
    base_url: str | None = None
    credential_id: str | None = None
    health_check_url: str | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class ServiceActionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    method: HTTPMethod = HTTPMethod.POST
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    query_schema: dict[str, Any] = Field(default_factory=dict)
    path_schema: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceActionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    method: HTTPMethod | None = None
    path: str | None = None
    headers: dict[str, str] | None = None
    query_schema: dict[str, Any] | None = None
    path_schema: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    retry_policy: RetryPolicy | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class ServiceActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    service_id: str
    name: str
    description: str | None
    method: HTTPMethod
    path: str
    headers: dict[str, str]
    query_schema: dict[str, Any]
    path_schema: dict[str, Any]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    timeout_seconds: int
    retry_policy: RetryPolicy
    enabled: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    service_type: ServiceType
    base_url: str
    credential_id: str | None
    credential_name: str | None
    health_check_url: str | None
    status: ServiceStatus
    enabled: bool
    metadata: dict[str, Any]
    last_checked_at: datetime | None
    last_latency_ms: int | None
    last_error: str | None
    actions_count: int
    created_at: datetime
    updated_at: datetime

