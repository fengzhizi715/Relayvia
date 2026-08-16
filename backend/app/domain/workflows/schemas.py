from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workflows.graph import GRAPH_SCHEMA_VERSION, WorkflowGraph
from app.domain.workflows.model import WorkflowStatus


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    graph: dict[str, Any] | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    status: WorkflowStatus | None = None


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    status: WorkflowStatus
    draft_graph: WorkflowGraph
    graph_schema_version: str
    current_version: int | None
    created_at: datetime
    updated_at: datetime


class WorkflowGraphUpdate(BaseModel):
    graph: dict[str, Any]


class WorkflowValidateRequest(BaseModel):
    graph: dict[str, Any] | None = None


class GraphWarning(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class WorkflowGraphRead(BaseModel):
    workflow_id: str
    schema_version: str = GRAPH_SCHEMA_VERSION
    graph: WorkflowGraph
    warnings: list[GraphWarning] = Field(default_factory=list)
    updated_at: datetime


class WorkflowVersionCreate(BaseModel):
    change_note: str | None = Field(default=None, max_length=2000)


class WorkflowVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    version: int
    graph_schema_version: str
    graph: WorkflowGraph
    change_note: str | None
    created_at: datetime

