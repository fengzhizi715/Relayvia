"""Execution Snapshot building.

An Execution Snapshot captures the non-secret invocation metadata a Run will
need, so a historical Run always knows *what* it was configured to call even
after Registry entries change.

Security invariant: only `credential_id` is stored. Secret material is never
read, decrypted or persisted here.
"""

from dataclasses import dataclass, field
from typing import Any

EXECUTION_SNAPSHOT_VERSION = "2"


@dataclass(frozen=True)
class SnapshotAgent:
    id: str
    name: str
    connector_type: str
    endpoint: str | None = None
    http_method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    health_check_url: str | None = None
    timeout_seconds: int | None = None
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    credential_id: str | None = None


@dataclass(frozen=True)
class SnapshotService:
    id: str
    name: str
    base_url: str
    health_check_url: str | None = None
    credential_id: str | None = None


@dataclass(frozen=True)
class SnapshotServiceAction:
    id: str
    service_id: str
    name: str
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query_schema: dict[str, Any] = field(default_factory=dict)
    path_schema: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int | None = None
    retry_policy: dict[str, Any] = field(default_factory=dict)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


def build_execution_snapshot(
    *,
    agents: list[SnapshotAgent],
    services: list[SnapshotService],
    service_actions: list[SnapshotServiceAction],
) -> dict[str, Any]:
    """Deduplicates Registry entries by id; Nodes keep referencing by id."""
    return {
        "schema_version": EXECUTION_SNAPSHOT_VERSION,
        "agents": {agent.id: _agent(agent) for agent in agents},
        "services": {service.id: _service(service) for service in services},
        "service_actions": {action.id: _action(action) for action in service_actions},
    }


def _agent(agent: SnapshotAgent) -> dict[str, Any]:
    return {
        "name": agent.name,
        "connector_type": agent.connector_type,
        "endpoint": agent.endpoint,
        "http_method": agent.http_method,
        "headers": agent.headers,
        "health_check_url": agent.health_check_url,
        "timeout_seconds": agent.timeout_seconds,
        "input_schema": agent.input_schema,
        "output_schema": agent.output_schema,
        "credential_id": agent.credential_id,
    }


def _service(service: SnapshotService) -> dict[str, Any]:
    return {
        "name": service.name,
        "base_url": service.base_url,
        "health_check_url": service.health_check_url,
        "credential_id": service.credential_id,
    }


def _action(action: SnapshotServiceAction) -> dict[str, Any]:
    return {
        "service_id": action.service_id,
        "name": action.name,
        "method": action.method,
        "path": action.path,
        "headers": action.headers,
        "query_schema": action.query_schema,
        "path_schema": action.path_schema,
        "timeout_seconds": action.timeout_seconds,
        "retry_policy": action.retry_policy,
        "input_schema": action.input_schema,
        "output_schema": action.output_schema,
    }


__all__ = [
    "EXECUTION_SNAPSHOT_VERSION",
    "SnapshotAgent",
    "SnapshotService",
    "SnapshotServiceAction",
    "build_execution_snapshot",
]
