from datetime import datetime
from enum import StrEnum

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

