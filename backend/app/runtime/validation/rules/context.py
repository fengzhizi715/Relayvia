"""Pass 5 - Context reference validation.

References are validated in the fields each Node type actually allows
(`reference_bearing_values`); metadata and other free-form strings are never
scanned. Rules: syntax, unknown node / variable / workflow-input, self and
forward references, upstream (ancestor) dependency, parallel sibling
dependency and output-field existence when the schema is closed.
"""

from typing import Any

from app.core.errors import RelayviaError
from app.domain.workflows.context_reference import ContextReference, extract_context_references
from app.domain.workflows.graph import NodeType, WorkflowGraph

from ..result import ValidationIssue
from ..codes import ValidationCode
from ..context import ValidationContext
from ..graph_index import GraphIndex


def validate_context(graph: WorkflowGraph, index: GraphIndex, context: ValidationContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    has_cycle = index.has_cycle()

    for node in graph.nodes:
        for value in reference_bearing_values(node):
            try:
                references = extract_context_references(value)
            except RelayviaError as exc:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_CONTEXT_REFERENCE,
                        severity="error",
                        message=exc.message,
                        node_id=node.id,
                        field=_reference_field(node),
                    )
                )
                continue
            for reference in references:
                _validate_reference(graph, index, context, node.id, reference, has_cycle, issues)

    return issues


def reference_bearing_values(node) -> list[Any]:
    """The exact config / mapping fields that may hold Context References."""
    values: list[Any] = []
    if node.type == NodeType.AGENT:
        template = node.config.get("task_template")
        if template:
            values.append(template)
        values.append(node.input_mapping)
    elif node.type in (NodeType.SERVICE, NodeType.TOOL, NodeType.HUMAN):
        values.append(node.input_mapping)
    elif node.type == NodeType.LOGIC:
        if node.subtype == "condition":
            expression = node.config.get("expression")
            if isinstance(expression, dict):
                values.append(expression.get("left"))
                values.append(expression.get("right"))
    elif node.type == NodeType.DATA:
        if node.subtype == "transform":
            values.append(node.config.get("mappings"))
        elif node.subtype == "output":
            values.append(node.config.get("output_mapping"))
    return values


def _reference_field(node) -> str:
    if node.type == NodeType.DATA and node.subtype == "output":
        return "config.output_mapping"
    if node.type == NodeType.DATA and node.subtype == "transform":
        return "config.mappings"
    if node.type == NodeType.LOGIC and node.subtype == "condition":
        return "config.expression"
    return "input_mapping"


def _validate_reference(
    graph: WorkflowGraph,
    index: GraphIndex,
    context: ValidationContext,
    node_id: str,
    reference: ContextReference,
    has_cycle: bool,
    issues: list[ValidationIssue],
) -> None:
    node = index.node(node_id)
    field = _reference_field(node)

    if reference.scope == "workflow.variables":
        if reference.path not in graph.variables:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.UNKNOWN_VARIABLE,
                    severity="error",
                    message=f"Workflow variable {reference.path!r} is not defined",
                    node_id=node_id,
                    field=field,
                    details={"reference": reference.raw},
                )
            )
        return

    if reference.scope == "workflow.input":
        _validate_workflow_input(index, node_id, reference, field, issues)
        return

    if reference.scope == "run":
        return

    target_id = reference.node_id
    if target_id is None:
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONTEXT_REFERENCE,
                severity="error",
                message=f"Reference {reference.raw!r} has an invalid shape",
                node_id=node_id,
                field=field,
            )
        )
        return

    target_node = index.node(target_id)
    if target_node is None:
        issues.append(
            ValidationIssue(
                code=ValidationCode.UNKNOWN_CONTEXT_NODE,
                severity="error",
                message=f"Context reference points to unknown node {target_id!r}",
                node_id=node_id,
                field=field,
                details={"reference": reference.raw},
            )
        )
        return

    if target_id == node_id:
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_CONTEXT_REFERENCE,
                severity="error",
                message="Node cannot reference its own output",
                node_id=node_id,
                field=field,
                details={"reference": reference.raw},
            )
        )
        return

    # Only nodes with explicit output semantics are referenceable: Agents,
    # Services and Data Transform. Referencing logic / human / tool / other
    # data nodes would create data dependencies the Runtime cannot satisfy.
    provider_kind = _output_provider_kind(target_node)
    if provider_kind is None:
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_OUTPUT_REFERENCE,
                severity="error",
                message=f"Node {target_id!r} does not produce a referenceable output",
                node_id=node_id,
                field=field,
                details={"reference": reference.raw, "target_node_id": target_id},
            )
        )
        return

    if not has_cycle and target_id not in index.ancestors(node_id):
        if _is_parallel_sibling(index, node_id, target_id):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_PARALLEL_DATA_DEPENDENCY,
                    severity="error",
                    message=f"Node references output of parallel sibling {target_id!r}",
                    node_id=node_id,
                    field=field,
                    details={"reference": reference.raw, "target_node_id": target_id},
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_DATA_DEPENDENCY,
                    severity="error",
                    message=f"Referenced node {target_id!r} is not an upstream dependency of this node",
                    node_id=node_id,
                    field=field,
                    details={"reference": reference.raw, "target_node_id": target_id},
                )
            )
        return

    if provider_kind == "transform":
        _validate_transform_output_field(target_node, node_id, reference, field, issues)
        return

    output_schema = _node_output_schema(index, context, target_id)
    if output_schema is not None:
        missing = _closed_object_missing_field(output_schema, reference.path)
        if missing is not None:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_OUTPUT_REFERENCE,
                    severity="error",
                    message=f"Output field {reference.path!r} is not declared in the output schema of {target_id!r}",
                    node_id=node_id,
                    field=field,
                    details={"reference": reference.raw, "target_node_id": target_id},
                )
            )


def _output_provider_kind(node) -> str | None:
    """Which output model a node exposes: 'schema' (agent/service output
    schema), 'transform' (Data Transform mappings), or None (no referenceable
    output in V1)."""
    if node.type in (NodeType.AGENT, NodeType.SERVICE):
        return "schema"
    if node.type == NodeType.DATA and node.subtype == "transform":
        return "transform"
    return None


def _validate_transform_output_field(node, node_id: str, reference: ContextReference, field: str | None, issues: list[ValidationIssue]) -> None:
    mappings = node.config.get("mappings")
    if not isinstance(mappings, dict):
        return
    output_field = reference.path.split(".")[0]
    if output_field not in mappings:
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_OUTPUT_REFERENCE,
                severity="error",
                message=f"Data Transform node does not produce field {reference.path!r}",
                node_id=node_id,
                field=field,
                details={"reference": reference.raw, "target_node_id": node.id},
            )
        )


def _is_parallel_sibling(index: GraphIndex, node_id: str, target_id: str) -> bool:
    for ancestor_id in index.ancestors(node_id):
        ancestor = index.node(ancestor_id)
        if ancestor is not None and ancestor.type == NodeType.LOGIC and ancestor.subtype == "parallel":
            if target_id not in index.descendants(ancestor_id):
                continue
            # A reference to a node that is already re-converged through one of
            # this Parallel's Merge joins is a downstream (forward) reference,
            # not a sibling-branch reference.
            if any(
                target_id in index.descendants(merge_id)
                for merge_id in _parallel_merge_descendants(index, ancestor_id)
            ):
                continue
            return True
    return False


def _parallel_merge_descendants(index: GraphIndex, parallel_id: str) -> list[str]:
    return [
        descendant_id
        for descendant_id in index.descendants(parallel_id)
        if (node := index.node(descendant_id)) is not None
        and node.type == NodeType.LOGIC
        and node.subtype == "merge"
    ]


def _validate_workflow_input(index: GraphIndex, node_id: str, reference: ContextReference, field: str | None, issues: list[ValidationIssue]) -> None:
    entry = index.entry_node_ids()
    if len(entry) != 1:
        return
    schema = index.node(entry[0]).config.get("schema")
    if not isinstance(schema, dict):
        return
    missing = _closed_object_missing_field(schema, reference.path)
    if missing is not None:
        issues.append(
            ValidationIssue(
                code=ValidationCode.UNKNOWN_WORKFLOW_INPUT,
                severity="error",
                message=f"Workflow input field {reference.path!r} is not declared in the Input schema",
                node_id=node_id,
                field=field,
                details={"reference": reference.raw},
            )
        )


def _node_output_schema(index: GraphIndex, context: ValidationContext, node_id: str) -> dict[str, Any] | None:
    node = index.node(node_id)
    if node is None:
        return None
    if node.type == NodeType.AGENT:
        agent = context.agents.get(node.config.get("agent_id"))
        return agent.output_schema if agent else None
    if node.type == NodeType.SERVICE:
        action = context.service_actions.get(node.config.get("service_action_id"))
        return action.output_schema if action else None
    return None


def _closed_object_missing_field(schema: dict[str, Any], field_path: str) -> str | None:
    field = field_path.split(".")[0]
    if schema.get("additionalProperties") is False and isinstance(schema.get("properties"), dict):
        if field not in schema["properties"]:
            return field
    return None
