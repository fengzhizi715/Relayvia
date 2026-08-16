"""Default V1 execution units for HTTP Registries and deterministic graph nodes.

Secrets are looked up only inside the Worker, then handed straight to the HTTP
connector.  They never enter a Graph, Run snapshot, NodeRun output, or error.
"""

from typing import Any
from urllib.parse import quote

from jsonschema import Draft7Validator
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.agents.http import HTTPAgentConnector
from app.connectors.base import ExecutionResult
from app.connectors.http import HTTPInvocationConfig
from app.connectors.services.http import HTTPServiceConnector
from app.connectors.tools.base import ToolInvocationConfig
from app.connectors.tools.shell import ShellToolConnector
from app.domain.credentials.model import Credential
from app.infrastructure.security.url_policy import combine_service_url
from app.runtime.executor.base import NodeExecutionContext, NodeExecutionResult, NodeExecutor
from app.runtime.executor.result import ExecutionError


class DefaultNodeExecutor(NodeExecutor):
    """Dispatch stable Graph node types behind the NodeExecutor boundary.

    Agent / Service / Tool execution delegates to the matching Connector, which
    returns a unified `ExecutionResult`; the Runtime alone decides NodeRun /
    WorkflowRun state afterwards.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        node = context.node_definition
        node_type, subtype = node["type"], node["subtype"]
        if node_type == "agent" and subtype == "agent":
            return await self._execute_agent(context)
        if node_type == "service" and subtype == "http":
            return await self._execute_service(context)
        if node_type == "tool":
            return await self._execute_tool(context)
        if node_type == "logic" and subtype == "condition":
            return self._execute_condition(context)
        if node_type == "logic" and subtype in {"parallel", "merge"}:
            return NodeExecutionResult(ok=True, output=dict(context.resolved_input))
        if node_type == "data" and subtype == "transform":
            return NodeExecutionResult(ok=True, output=dict(context.resolved_config.get("mappings", {})))
        if node_type == "data" and subtype == "output":
            return NodeExecutionResult(ok=True, output=dict(context.resolved_config.get("output_mapping", {})))
        if node_type == "data" and subtype == "input":
            return NodeExecutionResult(ok=True, output=dict(context.resolved_input))
        return _failure("UNSUPPORTED_NODE_EXECUTION", f"Execution is not implemented for {node_type}.{subtype}")

    async def _execute_agent(self, context: NodeExecutionContext) -> NodeExecutionResult:
        config = context.node_definition["config"]
        agent = context.execution_snapshot.get("agents", {}).get(config["agent_id"])
        if not isinstance(agent, dict):
            return _failure("AGENT_SNAPSHOT_MISSING", "Agent invocation metadata is missing from the Run snapshot")
        if agent.get("connector_type") != "http":
            return _failure("UNSUPPORTED_AGENT_CONNECTOR", "Only HTTP Agent execution is supported")
        endpoint = agent.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            return _failure("AGENT_ENDPOINT_MISSING", "HTTP Agent endpoint is not configured")
        invalid = _validate_payload(context.resolved_input, agent.get("input_schema"), "Agent input")
        if invalid:
            return invalid
        try:
            credential = self._credential(agent.get("credential_id"))
        except ExecutionError as exc:
            return NodeExecutionResult(ok=False, error=exc)
        result = await HTTPAgentConnector().execute(
            HTTPInvocationConfig(
                url=endpoint,
                method=str(agent.get("http_method") or "POST"),
                timeout_seconds=int(context.resolved_config.get("timeout_seconds") or agent.get("timeout_seconds") or 30),
                headers=_string_dict(agent.get("headers")),
                credential=credential,
                json_body={
                    "input": context.resolved_input,
                    "context": {"workflow_run_id": context.workflow_run_id, "node_id": context.node_id, "attempt": context.attempt},
                },
            )
        )
        return _execution_result_to_node(result, agent.get("output_schema"), "Agent output")

    async def _execute_service(self, context: NodeExecutionContext) -> NodeExecutionResult:
        config = context.node_definition["config"]
        service = context.execution_snapshot.get("services", {}).get(config["service_id"])
        action = context.execution_snapshot.get("service_actions", {}).get(config["service_action_id"])
        if not isinstance(service, dict) or not isinstance(action, dict):
            return _failure("SERVICE_SNAPSHOT_MISSING", "Service invocation metadata is missing from the Run snapshot")
        try:
            payload = _service_payload(context.resolved_input)
            url = combine_service_url(str(service["base_url"]), _expand_path(str(action["path"]), payload["path"]))
            credential = self._credential(service.get("credential_id"))
        except ExecutionError as exc:
            return NodeExecutionResult(ok=False, error=exc)
        for value, schema, label in (
            (payload["path"], action.get("path_schema"), "Service path parameters"),
            (payload["query"], action.get("query_schema"), "Service query parameters"),
            (payload["body"], action.get("input_schema"), "Service body"),
        ):
            invalid = _validate_payload(value, schema, label)
            if invalid:
                return invalid
        retry_policy = action.get("retry_policy") or {}
        retry_on_status = {int(status) for status in retry_policy.get("retry_on_status", [408, 429, 500, 502, 503, 504])}
        result = await HTTPServiceConnector().execute(
            HTTPInvocationConfig(
                url=url,
                method=str(action["method"]),
                timeout_seconds=int(context.resolved_config.get("timeout_seconds") or action.get("timeout_seconds") or 30),
                headers=_string_dict(action.get("headers")),
                credential=credential,
                json_body=payload["body"],
                query=payload["query"],
                retry_on_status=retry_on_status,
            )
        )
        return _execution_result_to_node(result, action.get("output_schema"), "Service output")

    async def _execute_tool(self, context: NodeExecutionContext) -> NodeExecutionResult:
        config = context.resolved_config
        command = config.get("command")
        if not isinstance(command, str) or not command.strip():
            return _failure("MISSING_TOOL_COMMAND", "Tool command is required")
        result = await ShellToolConnector().execute(
            ToolInvocationConfig(
                command=command,
                working_directory=str(config["working_directory"]) if config.get("working_directory") else None,
                timeout_seconds=int(config.get("timeout_seconds") or 60),
            )
        )
        return _execution_result_to_node(result, None, "Tool output")

    def _execute_condition(self, context: NodeExecutionContext) -> NodeExecutionResult:
        expression = context.resolved_config.get("expression")
        if not isinstance(expression, dict):
            return _failure("INVALID_CONDITION", "Condition expression is missing")
        try:
            matched = _evaluate_expression(expression)
        except (TypeError, ValueError):
            return _failure("CONDITION_EVALUATION_FAILED", "Condition values cannot be compared with the configured operator")
        return NodeExecutionResult(ok=True, output={"selected_branch": "true" if matched else "false", "matched": matched})

    def _credential(self, credential_id: Any) -> Credential | None:
        if not credential_id:
            return None
        with self._session_factory() as db:
            credential = db.get(Credential, str(credential_id))
            if credential is None:
                raise ExecutionError("CREDENTIAL_UNAVAILABLE", "Credential referenced by this Run is no longer available")
            db.expunge(credential)
            return credential


def _service_payload(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionError("INVALID_SERVICE_INPUT", "Service input must resolve to an object")
    if {"path", "query", "body"} & value.keys():
        body, query, path = value.get("body", {}), value.get("query", {}), value.get("path", {})
    else:
        body, query, path = value, {}, {}
    if not isinstance(body, dict) or not isinstance(query, dict) or not isinstance(path, dict):
        raise ExecutionError("INVALID_SERVICE_INPUT", "Service path, query, and body inputs must each be objects")
    return {"body": body, "query": query, "path": path}


def _expand_path(path: str, values: dict[str, Any]) -> str:
    expanded = path
    for name, value in values.items():
        expanded = expanded.replace("{" + str(name) + "}", quote(str(value), safe=""))
    if "{" in expanded or "}" in expanded:
        raise ExecutionError("MISSING_PATH_PARAMETER", "A required Service path parameter is missing")
    return expanded


def _validate_payload(value: Any, schema: Any, label: str) -> NodeExecutionResult | None:
    if not isinstance(schema, dict) or not schema:
        return None
    if list(Draft7Validator(schema).iter_errors(value)):
        return _failure("EXECUTION_SCHEMA_MISMATCH", f"{label} does not match its declared schema")
    return None


def _execution_result_to_node(result: ExecutionResult, output_schema: Any, label: str) -> NodeExecutionResult:
    """Map the unified Connector `ExecutionResult` onto the Node boundary."""
    if result.status != "success":
        return NodeExecutionResult(ok=False, retryable=result.retryable, error=result.error)
    invalid = _validate_payload(result.output or {}, output_schema, label)
    return invalid or NodeExecutionResult(ok=True, output=result.output or {})


def _string_dict(value: Any) -> dict[str, str]:
    return {str(key): str(item) for key, item in value.items()} if isinstance(value, dict) else {}


def _compare(left: Any, operator: Any, right: Any) -> bool:
    if operator == "==": return left == right
    if operator == "!=": return left != right
    if operator == ">": return left > right
    if operator == ">=": return left >= right
    if operator == "<": return left < right
    if operator == "<=": return left <= right
    if operator == "contains": return right in left
    if operator == "not_contains": return right not in left
    if operator == "is_empty":
        # Scalars (no __len__) are never empty; None is empty.
        return left is None or (hasattr(left, "__len__") and len(left) == 0)
    if operator == "is_not_empty":
        return left is not None and (not hasattr(left, "__len__") or len(left) > 0)
    raise ValueError("unsupported operator")


def _evaluate_expression(expr: Any) -> bool:
    """Safe, finite Condition evaluation: recursive AND/OR of comparisons.

    No eval / arbitrary code. Operands arrive already resolved by the
    ContextResolver.
    """
    if not isinstance(expr, dict):
        raise ValueError("invalid condition expression")
    if "and" in expr:
        clauses = expr["and"]
        if not isinstance(clauses, list) or not clauses:
            raise ValueError("invalid 'and' expression")
        return all(_evaluate_expression(clause) for clause in clauses)
    if "or" in expr:
        clauses = expr["or"]
        if not isinstance(clauses, list) or not clauses:
            raise ValueError("invalid 'or' expression")
        return any(_evaluate_expression(clause) for clause in clauses)
    return _compare(expr.get("left"), expr.get("operator"), expr.get("right"))


def _failure(code: str, message: str) -> NodeExecutionResult:
    return NodeExecutionResult(ok=False, retryable=False, error=ExecutionError(code, message))
