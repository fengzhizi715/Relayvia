"""Reference protection for Registry resources used by Workflow definitions."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import RelayviaError
from app.domain.workflows.model import Workflow, WorkflowVersion


def _nodes(graph: Any) -> list[dict[str, Any]]:
    if not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes", [])
    return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []


def _node_references(node: dict[str, Any], resource_type: str, resource_id: str) -> bool:
    config = node.get("config")
    if not isinstance(config, dict):
        return False
    if resource_type == "agent":
        return node.get("type") == "agent" and config.get("agent_id") == resource_id
    if resource_type == "service":
        return node.get("type") == "service" and config.get("service_id") == resource_id
    if resource_type == "service_action":
        return node.get("type") == "service" and config.get("service_action_id") == resource_id
    return False


def is_resource_referenced(db: Session, resource_type: str, resource_id: str) -> bool:
    for workflow in db.scalars(select(Workflow)).all():
        if any(_node_references(node, resource_type, resource_id) for node in _nodes(workflow.draft_graph_json)):
            return True
    for version in db.scalars(select(WorkflowVersion)).all():
        if any(_node_references(node, resource_type, resource_id) for node in _nodes(version.graph_json)):
            return True
    return False


def ensure_resource_not_referenced(db: Session, resource_type: str, resource_id: str) -> None:
    if is_resource_referenced(db, resource_type, resource_id):
        raise RelayviaError(
            "RESOURCE_IN_USE",
            "Resource is referenced by a Workflow and cannot be deleted",
            status_code=409,
            details={"resource_type": resource_type, "resource_id": resource_id},
        )

