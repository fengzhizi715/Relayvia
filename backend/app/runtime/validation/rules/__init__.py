"""Validation rules, registered in pipeline order.

Each rule is a pure function: `(graph, index, context) -> list[ValidationIssue]`.
Order determines grouping and default reporting order; the final sort in
`validator.validate_graph` stabilizes output.
"""

from ..rules.identity import validate_identity
from ..rules.topology import validate_topology
from ..rules.references import validate_references
from ..rules.nodes import validate_nodes
from ..rules.context import validate_context
from ..rules.schema import validate_schema

GROUP_ORDER = {
    "identity": 0,
    "topology": 1,
    "references": 2,
    "nodes": 3,
    "context": 4,
    "schema": 5,
}

RULES: list[tuple[str, object]] = [
    ("identity", validate_identity),
    ("topology", validate_topology),
    ("references", validate_references),
    ("nodes", validate_nodes),
    ("context", validate_context),
    ("schema", validate_schema),
]

__all__ = ["GROUP_ORDER", "RULES"]
