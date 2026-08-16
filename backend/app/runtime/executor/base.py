"""NodeExecutor boundary.

Phase 7 defines the boundary only; no Connector executes yet. A Worker
receives an `ExecutionContext` (resolved input + snapshots, no DB session) and
returns a `NodeExecutionResult`. Phase 8 plugs in ExecutionUnit / Connector
implementations behind this interface.
"""

from dataclasses import dataclass, field
from typing import Any

from app.runtime.executor.result import ExecutionError


@dataclass(frozen=True)
class NodeExecutionContext:
    workflow_run_id: str
    node_run_id: str
    node_id: str
    node_definition: dict[str, Any]
    resolved_input: dict[str, Any]
    execution_snapshot: dict[str, Any]
    attempt: int
    execution_key: str | None = None


@dataclass
class NodeExecutionResult:
    ok: bool
    output: dict[str, Any] | None = None
    retryable: bool = False
    error: ExecutionError | None = None


class NodeExecutor:
    async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        raise NotImplementedError


class PlaceholderNodeExecutor(NodeExecutor):
    """Default for Phase 7: no Node type executes yet. Real Connectors arrive
    in Phase 8."""

    async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        return NodeExecutionResult(
            ok=False,
            retryable=False,
            error=ExecutionError(
                "NODE_EXECUTION_UNSUPPORTED",
                "Node execution is not implemented in Phase 7",
                details={"node_id": context.node_id, "node_type": context.node_definition.get("type")},
            ),
        )
