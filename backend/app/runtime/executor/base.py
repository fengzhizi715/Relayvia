"""NodeExecutor boundary.

Workers receive a resolved execution context and return a structured result.
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
    resolved_config: dict[str, Any]
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
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class NodeExecutor:
    async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        raise NotImplementedError
