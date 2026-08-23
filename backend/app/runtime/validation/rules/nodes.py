"""Pass 4 - Node configuration and node-specific semantics."""

from app.domain.workflows.graph import ConditionOperator, NodeType, WorkflowGraph

from ..result import ValidationIssue
from ..codes import ValidationCode
from ..context import ValidationContext
from ..graph_index import GraphIndex

CONDITION_OPERATORS = {operator.value for operator in ConditionOperator}
CONDITION_HANDLES = {"true", "false"}


def validate_nodes(graph: WorkflowGraph, index: GraphIndex, context: ValidationContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for node in graph.nodes:
        if node.type == NodeType.AGENT:
            continue
        if node.type == NodeType.SERVICE:
            continue
        if node.type == NodeType.TOOL:
            _validate_tool(node, issues)
        elif node.type == NodeType.LOGIC:
            _validate_logic(node, index, issues)
        elif node.type == NodeType.HUMAN:
            _validate_human(node, issues)
        elif node.type == NodeType.DATA:
            _validate_data(node, issues)
    return issues


def _validate_tool(node, issues: list[ValidationIssue]) -> None:
    if not node.config.get("command"):
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_REQUIRED_CONFIG,
                severity="error",
                message="Tool command is required",
                node_id=node.id,
                field="config.command",
            )
        )


def _validate_logic(node, index: GraphIndex, issues: list[ValidationIssue]) -> None:
    if node.subtype == "condition":
        _validate_condition(node, index, issues)
    elif node.subtype == "wait":
        mode = node.config.get("mode")
        if mode != "duration":
            issues.append(
                ValidationIssue(
                    code=ValidationCode.UNSUPPORTED_WAIT_MODE,
                    severity="error",
                    message=f"Wait mode {mode!r} is not supported in V1",
                    node_id=node.id,
                    field="config.mode",
                )
            )
        duration = node.config.get("duration_seconds")
        if not isinstance(duration, int) or duration <= 0:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_WAIT_CONFIG,
                    severity="error",
                    message="Wait duration must be greater than 0",
                    node_id=node.id,
                    field="config.duration_seconds",
                )
            )
    elif node.subtype == "router":
        # Router is retained in the persisted Graph vocabulary for a future
        # deterministic routing contract, but has no scheduler semantics yet.
        # A draft may contain it; an immutable Version may not.
        issues.append(
            ValidationIssue(
                code=ValidationCode.UNSUPPORTED_NODE_EXECUTION,
                severity="error",
                message="Router nodes cannot be published because Router execution semantics are not implemented",
                node_id=node.id,
                field="type",
            )
        )
    # parallel / merge counts are handled in the topology pass.


def _validate_condition(node, index: GraphIndex, issues: list[ValidationIssue]) -> None:
    expression = node.config.get("expression")
    if not isinstance(expression, dict):
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONDITION,
                severity="error",
                message="Condition requires a structured expression",
                node_id=node.id,
                field="config.expression",
            )
        )
        return
    _validate_expression(expression, node.id, issues)

    branches: dict[str, list] = {}
    for edge in index.outgoing_edges(node.id):
        handle = edge.source_handle
        if handle in CONDITION_HANDLES:
            branches.setdefault(handle, []).append(edge)
        else:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONDITION_BRANCH,
                    severity="error",
                    message="Condition output edges must use the true/false source handle",
                    edge_id=edge.id,
                    node_id=node.id,
                    field="edges[].source_handle",
                )
            )
    for handle in ("true", "false"):
        edges = branches.get(handle, [])
        if len(edges) == 0:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONDITION_BRANCH,
                    severity="error",
                    message=f"Condition requires exactly one {handle!r} branch",
                    node_id=node.id,
                    field="edges[]",
                    details={"branch": handle},
                )
            )
        elif len(edges) > 1:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONDITION_BRANCH,
                    severity="error",
                    message=f"Condition must have a single {handle!r} branch",
                    node_id=node.id,
                    field="edges[]",
                    details={"branch": handle, "edge_ids": [edge.id for edge in edges]},
                )
            )


def _validate_expression(expression: dict, node_id: str, issues: list[ValidationIssue]) -> None:
    """Recursively validate a Condition clause: comparison or AND/OR."""
    if "and" in expression or "or" in expression:
        if "and" in expression and "or" in expression:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONDITION,
                    severity="error",
                    message="Condition expression cannot combine 'and' and 'or'",
                    node_id=node_id,
                    field="config.expression",
                )
            )
            return
        clauses = expression.get("and") or expression.get("or")
        if not isinstance(clauses, list) or not clauses:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_CONDITION,
                    severity="error",
                    message="Condition 'and'/'or' requires a non-empty clause list",
                    node_id=node_id,
                    field="config.expression",
                )
            )
            return
        for clause in clauses:
            if isinstance(clause, dict):
                _validate_expression(clause, node_id, issues)
            else:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_CONDITION,
                        severity="error",
                        message="Condition clauses must be structured expressions",
                        node_id=node_id,
                        field="config.expression",
                    )
                )
        return

    left = expression.get("left")
    if left is None or left == "":
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONDITION,
                severity="error",
                message="Condition left value is required",
                node_id=node_id,
                field="config.expression.left",
            )
        )
    operator = expression.get("operator")
    if operator not in CONDITION_OPERATORS:
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONDITION_OPERATOR,
                severity="error",
                message=f"Condition operator {operator!r} is not supported",
                node_id=node_id,
                field="config.expression.operator",
            )
        )


def _validate_human(node, issues: list[ValidationIssue]) -> None:
    if node.subtype == "approval":
        if not node.config.get("title"):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_REQUIRED_CONFIG,
                    severity="error",
                    message="Approval title is required",
                    node_id=node.id,
                    field="config.title",
                )
            )
    elif node.subtype == "input":
        form_schema = node.config.get("form_schema")
        if not isinstance(form_schema, dict) or form_schema.get("type") != "object":
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_HUMAN_CONFIG,
                    severity="error",
                    message="Human Input form schema must be a JSON Schema object",
                    node_id=node.id,
                    field="config.form_schema",
                )
            )


def _validate_data(node, issues: list[ValidationIssue]) -> None:
    if node.subtype == "input":
        schema = node.config.get("schema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_DATA_INPUT,
                    severity="error",
                    message="Data Input schema must declare type 'object'",
                    node_id=node.id,
                    field="config.schema",
                )
            )
    elif node.subtype == "transform":
        mappings = node.config.get("mappings")
        if not isinstance(mappings, dict):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_TRANSFORM_CONFIG,
                    severity="error",
                    message="Transform mappings must be an object",
                    node_id=node.id,
                    field="config.mappings",
                )
            )
    elif node.subtype == "output":
        mapping = node.config.get("output_mapping")
        if not isinstance(mapping, dict):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_DATA_OUTPUT,
                    severity="error",
                    message="Data Output mapping must be an object",
                    node_id=node.id,
                    field="config.output_mapping",
                )
            )
