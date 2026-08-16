"""Validation context.

The Validation Engine never queries the database directly. Registry data is
passed in as plain, immutable snapshots via `ValidationContext`, so the engine
is fully testable without FastAPI, HTTP or a session.
"""

from dataclasses import dataclass, field
from typing import Any

from app.domain.workflows.graph import WorkflowGraph


@dataclass(frozen=True)
class RegistryAgent:
    id: str
    name: str
    enabled: bool
    status: str = "unknown"
    timeout_seconds: int | None = None
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegistryService:
    id: str
    name: str
    enabled: bool
    status: str = "unknown"
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class RegistryServiceAction:
    id: str
    service_id: str
    name: str
    enabled: bool
    timeout_seconds: int | None = None
    query_schema: dict[str, Any] = field(default_factory=dict)
    path_schema: dict[str, Any] = field(default_factory=dict)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationContext:
    graph: WorkflowGraph
    agents: dict[str, RegistryAgent] = field(default_factory=dict)
    services: dict[str, RegistryService] = field(default_factory=dict)
    service_actions: dict[str, RegistryServiceAction] = field(default_factory=dict)
