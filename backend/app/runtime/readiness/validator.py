"""Run Readiness validation.

A Version is validated once at creation, but Registry state can change
afterwards. Run creation re-checks that referenced Agents / Services / Actions
still exist and are enabled. Health (UNHEALTHY) is a Warning only: the
external service may recover before execution actually starts.
"""

from dataclasses import dataclass, field

from app.domain.workflows.graph import WorkflowGraph
from app.runtime.validation.context import ValidationContext
from app.runtime.validation.graph_index import GraphIndex
from app.runtime.validation.rules.references import validate_references


@dataclass
class ReadinessResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_run_readiness(graph: WorkflowGraph, context: ValidationContext) -> ReadinessResult:
    index = GraphIndex.build(graph)
    issues = validate_references(graph, index, context)
    return ReadinessResult(
        valid=not any(issue.severity == "error" for issue in issues),
        errors=[issue.message for issue in issues if issue.severity == "error"],
        warnings=[issue.message for issue in issues if issue.severity == "warning"],
    )
