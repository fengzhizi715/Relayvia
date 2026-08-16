"""Pass 6 - Limited, reliable JSON Schema compatibility for Input Mapping.

Supported: top-level primitive types, integer->number widening, number->integer
narrowing (warning), required fields, additionalProperties=false rejection,
and constant / reference / template source classification. Nested structural
subtyping is intentionally out of scope for V1.
"""

from typing import Any

from app.core.errors import RelayviaError
from app.domain.workflows.context_reference import ContextReference, parse_context_reference
from app.domain.workflows.graph import NodeType, WorkflowGraph

from ..result import ValidationIssue
from ..codes import ValidationCode
from ..context import ValidationContext
from ..graph_index import GraphIndex

KNOWN_TYPES = {"string", "number", "integer", "boolean", "object", "array", "null"}


def validate_schema(graph: WorkflowGraph, index: GraphIndex, context: ValidationContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for node in graph.nodes:
        if node.type == NodeType.AGENT:
            schema = _node_input_schema(index, context, node.id)
            _validate_mapping(node, schema, graph, index, context, issues)
        elif node.type == NodeType.SERVICE:
            schema = _node_input_schema(index, context, node.id)
            _validate_mapping(node, schema, graph, index, context, issues)
    return issues


def _node_input_schema(index: GraphIndex, context: ValidationContext, node_id: str) -> dict[str, Any] | None:
    node = index.node(node_id)
    if node is None:
        return None
    if node.type == NodeType.AGENT:
        agent = context.agents.get(node.config.get("agent_id"))
        return agent.input_schema if agent else None
    if node.type == NodeType.SERVICE:
        action = context.service_actions.get(node.config.get("service_action_id"))
        return action.input_schema if action else None
    return None


def _validate_mapping(node, schema: dict[str, Any] | None, graph, index, context, issues: list[ValidationIssue]) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return
    mapping = node.input_mapping if isinstance(node.input_mapping, dict) else {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}

    for required in schema.get("required", []):
        if required not in mapping:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_REQUIRED_INPUT,
                    severity="error",
                    message=f"Required input {required!r} is not mapped",
                    node_id=node.id,
                    field=f"input_mapping.{required}",
                )
            )

    if schema.get("additionalProperties") is False:
        for key in mapping:
            if key not in properties:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.UNKNOWN_INPUT_FIELD,
                        severity="error",
                        message=f"Input field {key!r} is not allowed by the target schema",
                        node_id=node.id,
                        field=f"input_mapping.{key}",
                    )
                )

    for key, value in mapping.items():
        target = properties.get(key)
        if not isinstance(target, dict):
            continue
        target_type = target.get("type")
        if target_type not in KNOWN_TYPES:
            continue
        source_type = _mapping_source_type(value, graph, index, context)
        if source_type is None:
            continue
        compatible, narrowing = _check_compatibility(source_type, target_type)
        if not compatible:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.SCHEMA_TYPE_MISMATCH,
                    severity="error",
                    message=f"Input {key!r} has type {source_type!r} but the target expects {target_type!r}",
                    node_id=node.id,
                    field=f"input_mapping.{key}",
                    details={"source_type": source_type, "target_type": target_type},
                )
            )
        elif narrowing:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.SCHEMA_TYPE_MISMATCH,
                    severity="warning",
                    message=f"Input {key!r} is a number mapped to an integer target",
                    node_id=node.id,
                    field=f"input_mapping.{key}",
                    details={"source_type": source_type, "target_type": target_type},
                )
            )


def _mapping_source_type(value: Any, graph: WorkflowGraph, index: GraphIndex, context: ValidationContext) -> str | None:
    """Classify a mapping value and resolve its JSON Schema type when possible.

    Literal values are inferred from Python; pure references resolve through
    the referenced schema (node output / workflow input / variable); any
    templated string is treated as `string`. Unresolvable values return None
    and skip the type check.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    if not isinstance(value, str):
        return None

    reference = _as_pure_reference(value)
    if reference is None:
        return "string"
    return _reference_type(reference, graph, index, context)


def _as_pure_reference(value: str) -> ContextReference | None:
    if not (value.startswith("{{") and value.endswith("}}") and value.count("{{") == 1 and value.count("}}") == 1):
        return None
    try:
        return parse_context_reference(value)
    except RelayviaError:
        return None


def _reference_type(reference: ContextReference, graph: WorkflowGraph, index: GraphIndex, context: ValidationContext) -> str | None:
    if reference.scope == "workflow.variables":
        variable = graph.variables.get(reference.path)
        return variable.type.value if variable else None

    if reference.scope == "workflow.input":
        entry = index.entry_node_ids()
        if len(entry) != 1:
            return None
        schema = index.node(entry[0]).config.get("schema")
        return _field_type(schema, reference.path)

    if reference.scope == "run":
        return None

    target_id = reference.node_id
    if target_id is None:
        return None
    schema = _node_output_schema(index, context, target_id)
    return _field_type(schema, reference.path)


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


def _field_type(schema: Any, field_path: str) -> str | None:
    if not isinstance(schema, dict):
        return None
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None
    child = properties.get(field_path.split(".")[0])
    if not isinstance(child, dict):
        return None
    return child.get("type")


def _check_compatibility(source_type: str, target_type: str) -> tuple[bool, bool]:
    """Return (compatible, narrowing). integer->number is safe; number->integer
    is a narrowing that is allowed with a warning."""
    if source_type == target_type:
        return True, False
    if source_type == "integer" and target_type == "number":
        return True, False
    if source_type == "number" and target_type == "integer":
        return True, True
    return False, False
