"""Artifact metadata API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import Field


class ArtifactRead(BaseModel):
    id: str
    workflow_run_id: str
    producer_node_run_id: str
    type: str
    name: str
    uri: str
    size: int | None
    content_type: str | None
    metadata: dict[str, Any]
    created_at: datetime


class RunnerArtifactUploadCreate(BaseModel):
    task_id: str
    lease_token: str
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(default="file", min_length=1, max_length=32)
    content_type: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)
    output_key: str | None = Field(default=None, max_length=255)


class RunnerArtifactUploadRead(BaseModel):
    artifact_id: str
    uri: str
