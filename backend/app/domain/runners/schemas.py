"""Relayvia Runner API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RunnerRegister(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    hostname: str = Field(min_length=1, max_length=255)
    platform: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    runner_id: str | None = None
    runner_token: str | None = Field(default=None, min_length=32, max_length=512)


class RunnerHeartbeat(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    platform: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunnerRead(BaseModel):
    id: str
    name: str
    hostname: str
    platform: str | None
    status: str
    capabilities: list[str]
    last_seen_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RunnerStatusUpdate(BaseModel):
    enabled: bool


class RunnerTokenRead(BaseModel):
    runner_id: str
    enrollment_token: str


class RunnerRegistrationRead(RunnerRead):
    """Enrollment response. `enrollment_token` is returned only once."""

    enrollment_token: str | None = None


class RunnerClaimRead(BaseModel):
    task_id: str
    workflow_run_id: str
    node_run_id: str
    node_id: str | None
    execution_type: str | None
    config: dict[str, Any] | None
    workspace: dict[str, Any] | None = None
    attempt: int
    lease_token: str


class RunnerTaskHeartbeatRead(BaseModel):
    """Response to a Runner's in-flight task heartbeat.

    `cancel_requested` is a cooperative cancellation signal. The Runner must
    terminate its child process group and must not submit a normal result.
    """

    cancel_requested: bool


class RunnerResult(BaseModel):
    ok: bool
    output: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


class RunnerSubmitRequest(BaseModel):
    task_id: str
    lease_token: str
    result: RunnerResult


class RunnerWorkspaceCleanupClaim(BaseModel):
    workspace_id: str
    repository: str
    path: str
    branch: str | None
    strategy: str


class RunnerWorkspaceCleanupResult(BaseModel):
    ok: bool
    error: str | None = Field(default=None, max_length=1000)
