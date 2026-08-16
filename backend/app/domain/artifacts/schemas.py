"""Artifact metadata API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
