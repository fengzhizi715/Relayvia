"""ExecutionTask read schemas (read-only, debug surface)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.execution.state_machine import ExecutionTaskStatus


class ExecutionTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_run_id: str
    node_run_id: str
    task_type: str
    status: ExecutionTaskStatus
    payload: dict[str, Any]
    priority: int
    attempt: int
    max_attempts: int
    available_at: datetime
    locked_by: str | None
    locked_at: datetime | None
    lease_expires_at: datetime | None
    execution_key: str | None
    last_error: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
