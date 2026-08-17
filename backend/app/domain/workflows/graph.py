"""Pydantic models and contract-level validation for Workflow Graph 1.0."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import RelayviaError
from app.domain.validation import validate_json_schema, validate_metadata
from app.domain.workflows.context_reference import extract_node_references


GRAPH_SCHEMA_VERSION = "1.0"


class NodeType(StrEnum):
    AGENT = "agent"
    SERVICE = "service"
    TOOL = "tool"
    LOGIC = "logic"
    HUMAN = "human"
    DATA = "data"


class ConditionOperator(StrEnum):
    EQ = "=="
    NE = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


class ConditionExpression(BaseModel):
    """A Condition clause: a single comparison, or a recursive AND/OR of
    clauses. Exactly one shape is allowed per clause.

    Comparison:  {"left": ..., "operator": ">=", "right": ...}
    Combination: {"and": [<clause>, ...]} or {"or": [<clause>, ...]}
    """

    model_config = ConfigDict(extra="forbid")

    and_: list["ConditionExpression"] | None = Field(default=None, alias="and")
    or_: list["ConditionExpression"] | None = Field(default=None, alias="or")
    left: Any = None
    operator: ConditionOperator | None = None
    right: Any = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ConditionExpression":
        combination_count = (self.and_ is not None) + (self.or_ is not None)
        if combination_count > 1:
            raise ValueError("Condition expression cannot combine 'and' and 'or'")
        if combination_count == 1:
            if self.left is not None or self.operator is not None or self.right is not None:
                raise ValueError("Condition 'and'/'or' cannot be combined with a comparison")
            clauses = self.and_ if self.and_ is not None else self.or_
            if not clauses:
                raise ValueError("Condition 'and'/'or' requires at least one clause")
            return self
        if self.operator is None:
            raise ValueError("Condition comparison requires an operator")
        return self


class VariableType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class RetryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(default=0, ge=0, le=10)


class ToolWorkspaceConfig(BaseModel):
    """Optional workspace for a Node: a local repository (shared) or a
    dedicated Git worktree (isolated per Node/Run)."""

    model_config = ConfigDict(extra="forbid")

    repository: str = Field(min_length=1, max_length=2048)
    strategy: Literal["local", "worktree"] = "worktree"
    base_branch: str | None = Field(default=None, max_length=255)


class AgentNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    task_template: str | None = None
    timeout_seconds: int = Field(default=600, ge=1, le=86400)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    workspace: ToolWorkspaceConfig | None = None


class ServiceNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: str = Field(min_length=1, max_length=120)
    service_action_id: str = Field(min_length=1, max_length=120)
    timeout_seconds: int = Field(default=60, ge=1, le=86400)
    retry: RetryConfig = Field(default_factory=RetryConfig)


class ToolNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1, max_length=4000)
    working_directory: str | None = Field(default=None, max_length=2048)
    # Tool commands must be pinned to the Runner which owns their local path.
    # It remains optional in the graph for backwards compatibility; Run
    # readiness rejects unpinned Tool nodes before execution.
    runner_id: str | None = Field(default=None, min_length=1, max_length=120)
    timeout_seconds: int = Field(default=600, ge=1, le=86400)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    workspace: ToolWorkspaceConfig | None = None


class ConditionNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: ConditionExpression


class ParallelNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MergeNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["all"] = "all"


class WaitNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["duration"] = "duration"
    duration_seconds: int = Field(ge=1, le=31_536_000)


class RouterNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HumanApprovalNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    allow_reject: bool = True


class HumanInputNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form_schema: dict[str, Any] = Field(default_factory=dict)


class DataInputNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class DataTransformNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: dict[str, Any] = Field(default_factory=dict)


class DataOutputNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_mapping: dict[str, Any] = Field(default_factory=dict)


class WorkflowVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: VariableType
    default: Any = None
    description: str | None = None


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    type: NodeType
    subtype: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    position: Position
    config: dict[str, Any] = Field(default_factory=dict)
    input_mapping: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_subtype_and_config(self) -> "WorkflowNode":
        config_models: dict[tuple[NodeType, str], type[BaseModel]] = {
            (NodeType.AGENT, "agent"): AgentNodeConfig,
            (NodeType.SERVICE, "http"): ServiceNodeConfig,
            (NodeType.TOOL, "shell"): ToolNodeConfig,
            (NodeType.TOOL, "git"): ToolNodeConfig,
            (NodeType.TOOL, "test_command"): ToolNodeConfig,
            (NodeType.LOGIC, "condition"): ConditionNodeConfig,
            (NodeType.LOGIC, "parallel"): ParallelNodeConfig,
            (NodeType.LOGIC, "merge"): MergeNodeConfig,
            (NodeType.LOGIC, "router"): RouterNodeConfig,
            (NodeType.LOGIC, "wait"): WaitNodeConfig,
            (NodeType.HUMAN, "approval"): HumanApprovalNodeConfig,
            (NodeType.HUMAN, "input"): HumanInputNodeConfig,
            (NodeType.DATA, "input"): DataInputNodeConfig,
            (NodeType.DATA, "transform"): DataTransformNodeConfig,
            (NodeType.DATA, "output"): DataOutputNodeConfig,
        }
        config_model = config_models.get((self.type, self.subtype))
        if config_model is None:
            raise ValueError(f"Unsupported node type/subtype: {self.type.value}.{self.subtype}")
        config_model.model_validate(self.config)
        return self


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    source: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)
    source_handle: str | None = Field(default=None, max_length=120)
    target_handle: str | None = Field(default=None, max_length=120)
    label: str | None = Field(default=None, max_length=240)
    condition: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    variables: dict[str, WorkflowVariable] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def empty_workflow_graph() -> WorkflowGraph:
    return WorkflowGraph(schema_version=GRAPH_SCHEMA_VERSION)


def parse_workflow_graph(raw: Any) -> WorkflowGraph:
    if not isinstance(raw, dict):
        raise RelayviaError("INVALID_GRAPH", "Workflow graph must be a JSON object")
    if raw.get("schema_version") != GRAPH_SCHEMA_VERSION:
        raise RelayviaError(
            "UNSUPPORTED_GRAPH_SCHEMA_VERSION",
            f"Only graph schema version {GRAPH_SCHEMA_VERSION} is supported",
            details={"schema_version": raw.get("schema_version")},
        )
    try:
        graph = WorkflowGraph.model_validate(raw)
    except Exception as exc:
        errors = exc.errors() if hasattr(exc, "errors") else [{"message": str(exc)}]
        raise RelayviaError("INVALID_GRAPH", "Workflow graph does not match Graph Schema 1.0", details={"errors": errors}) from exc
    validate_graph_contract(graph)
    return graph


def validate_graph_contract(graph: WorkflowGraph) -> WorkflowGraph:
    node_ids = [node.id for node in graph.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise RelayviaError("DUPLICATE_NODE_ID", "Node IDs must be unique")
    edge_ids = [edge.id for edge in graph.edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise RelayviaError("DUPLICATE_EDGE_ID", "Edge IDs must be unique")
    node_id_set = set(node_ids)
    for edge in graph.edges:
        if edge.source not in node_id_set:
            raise RelayviaError("INVALID_NODE_REFERENCE", "Edge source node does not exist", details={"edge_id": edge.id, "node_id": edge.source})
        if edge.target not in node_id_set:
            raise RelayviaError("INVALID_NODE_REFERENCE", "Edge target node does not exist", details={"edge_id": edge.id, "node_id": edge.target})

    validate_metadata(graph.metadata)
    for variable_name, variable in graph.variables.items():
        if not variable_name or len(variable_name) > 120:
            raise RelayviaError("INVALID_GRAPH", "Workflow variable names must be non-empty and concise", details={"variable": variable_name})
    for node in graph.nodes:
        validate_metadata(node.metadata, field=f"nodes.{node.id}.metadata")
        config = node.config
        if node.type is NodeType.DATA and node.subtype == "input":
            validate_json_schema(config.get("schema", {}), field=f"nodes.{node.id}.config.schema")
        if node.type is NodeType.HUMAN and node.subtype == "input":
            validate_json_schema(config.get("form_schema", {}), field=f"nodes.{node.id}.config.form_schema")
        for referenced_node_id in extract_node_references({"config": config, "input_mapping": node.input_mapping}):
            if referenced_node_id not in node_id_set:
                raise RelayviaError(
                    "INVALID_NODE_REFERENCE",
                    "Context reference points to a node that does not exist",
                    details={"node_id": referenced_node_id, "source_node_id": node.id},
                )
    return graph


__all__ = [
    "AgentNodeConfig",
    "ConditionExpression",
    "ConditionNodeConfig",
    "ConditionOperator",
    "DataInputNodeConfig",
    "DataOutputNodeConfig",
    "DataTransformNodeConfig",
    "GRAPH_SCHEMA_VERSION",
    "HumanApprovalNodeConfig",
    "HumanInputNodeConfig",
    "MergeNodeConfig",
    "NodeType",
    "ParallelNodeConfig",
    "Position",
    "RetryConfig",
    "RouterNodeConfig",
    "ServiceNodeConfig",
    "ToolNodeConfig",
    "VariableType",
    "WaitNodeConfig",
    "WorkflowEdge",
    "WorkflowGraph",
    "WorkflowNode",
    "WorkflowVariable",
    "empty_workflow_graph",
    "parse_workflow_graph",
    "validate_graph_contract",
]
