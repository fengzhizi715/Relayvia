from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ConnectionTestStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNSUPPORTED = "unsupported"


class ConnectionTestResult(BaseModel):
    status: ConnectionTestStatus
    latency_ms: int | None = None
    checked_at: datetime
    error_code: str | None = None
    message: str | None = None


class HTTPInvocationResult(BaseModel):
    """Sanitized result of an outbound HTTP invocation."""

    ok: bool
    status_code: int | None = None
    output: dict[str, Any] | None = None
    retryable: bool = False
    error_code: str | None = None
    message: str | None = None
