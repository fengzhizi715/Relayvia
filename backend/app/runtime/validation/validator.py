"""Workflow Graph Validation Engine.

`validate_graph(graph, context)` is the single entry point. It is pure:
no FastAPI, no HTTP, no database access. The registry snapshots arrive via
`ValidationContext`. Output is a structured `ValidationResult` with stable,
deterministic ordering.
"""

from app.domain.workflows.graph import WorkflowGraph

from .codes import ValidationCode
from .context import ValidationContext
from .graph_index import GraphIndex
from .result import ValidationIssue, ValidationResult
from .rules import GROUP_ORDER, RULES


def validate_graph(graph: WorkflowGraph, context: ValidationContext) -> ValidationResult:
    index = GraphIndex.build(graph)

    if not graph.nodes:
        return ValidationResult(
            valid=False,
            errors=[
                ValidationIssue(
                    code=ValidationCode.GRAPH_EMPTY,
                    severity="error",
                    message="Workflow graph is empty",
                )
            ],
            warnings=[],
        )

    node_position = {node.id: position for position, node in enumerate(graph.nodes)}
    edge_position = {edge.id: position for position, edge in enumerate(graph.edges)}

    collected: list[tuple[int, ValidationIssue]] = []
    for group, rule in RULES:
        for issue in rule(graph, index, context):  # type: ignore[operator]
            collected.append((GROUP_ORDER[group], issue))

    def rank(issue: ValidationIssue) -> int:
        if issue.node_id and issue.node_id in node_position:
            return node_position[issue.node_id]
        if issue.edge_id and issue.edge_id in edge_position:
            return edge_position[issue.edge_id]
        return -1

    collected.sort(key=lambda item: (item[0], rank(item[1]), item[1].code))
    issues = [issue for _, issue in collected]
    return ValidationResult.from_issues(issues)


__all__ = [
    "ValidationCode",
    "ValidationContext",
    "ValidationIssue",
    "ValidationResult",
    "validate_graph",
]
