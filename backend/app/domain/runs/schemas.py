"""Workflow Run / Node Run API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workflows.graph import WorkflowGraph
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus


class WorkflowRunCreate(BaseModel):
    workflow_version_id: str | None = None
    version: int | None = None
    input: dict[str, Any] = Field(default_factory=dict)


class NodeRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_run_id: str
    node_id: str
    node_type: str
    node_subtype: str
    node_name_snapshot: str
    status: NodeRunStatus
    input: dict[str, Any]
    output: dict[str, Any] | None
    error: dict[str, Any] | None
    execution_metadata: dict[str, Any]
    artifacts: list[dict[str, Any]]
    attempt: int
    waiting_reason: str | None
    waiting_metadata: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    workflow_name: str | None = None
    workflow_version_id: str
    version: int
    status: WorkflowRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunRead(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str | None = None
    workflow_version_id: str
    version: int
    status: WorkflowRunStatus
    graph_schema_version: str
    graph_snapshot: WorkflowGraph
    execution_snapshot: dict[str, Any]
    input: dict[str, Any]
    variables: dict[str, Any]
    error: dict[str, Any] | None
    waiting_reason: str | None
    waiting_metadata: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    paused_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    node_runs: list[NodeRunRead]
