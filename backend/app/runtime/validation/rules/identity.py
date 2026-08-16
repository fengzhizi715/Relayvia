"""Pass 1 - Graph identity: structural edge sanity, duplicate ids/connections."""

from collections import Counter

from app.domain.workflows.graph import WorkflowGraph

from ..result import ValidationIssue
from ..codes import ValidationCode
from ..context import ValidationContext
from ..graph_index import GraphIndex


def validate_identity(graph: WorkflowGraph, index: GraphIndex, context: ValidationContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    node_ids = [node.id for node in graph.nodes]
    for node_id, count in Counter(node_ids).items():
        if count > 1:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.DUPLICATE_NODE_ID,
                    severity="error",
                    message=f"Node id {node_id!r} is duplicated",
                    node_id=node_id,
                    field="nodes[].id",
                )
            )

    edge_ids = [edge.id for edge in graph.edges]
    for edge_id, count in Counter(edge_ids).items():
        if count > 1:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.DUPLICATE_EDGE_ID,
                    severity="error",
                    message=f"Edge id {edge_id!r} is duplicated",
                    edge_id=edge_id,
                    field="edges[].id",
                )
            )

    node_id_set = set(node_ids)
    seen_connections: set[tuple[str, str, str | None]] = set()
    for edge in graph.edges:
        if edge.source not in node_id_set:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_EDGE_SOURCE,
                    severity="error",
                    message=f"Edge source node {edge.source!r} does not exist",
                    edge_id=edge.id,
                    field="edges[].source",
                )
            )
        if edge.target not in node_id_set:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_EDGE_TARGET,
                    severity="error",
                    message=f"Edge target node {edge.target!r} does not exist",
                    edge_id=edge.id,
                    field="edges[].target",
                )
            )
        if edge.source == edge.target:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.SELF_CONNECTION,
                    severity="error",
                    message=f"Node {edge.source!r} cannot connect to itself",
                    edge_id=edge.id,
                    node_id=edge.source,
                    field="edges[]",
                )
            )
        connection_key = (edge.source, edge.target, edge.source_handle)
        if connection_key in seen_connections:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.DUPLICATE_CONNECTION,
                    severity="error",
                    message=f"Duplicate connection {edge.source!r} -> {edge.target!r}",
                    edge_id=edge.id,
                    node_id=edge.source,
                    field="edges[]",
                )
            )
        seen_connections.add(connection_key)

    return issues
