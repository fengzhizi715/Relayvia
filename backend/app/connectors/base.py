"""Unified Connector contract.

A `Connector` receives an execution request (its own request type) and returns
a single `ExecutionResult`. Connectors only call the external capability and
report the outcome. They never mutate WorkflowRun / NodeRun state, never
schedule the next node, and never decide retry policy — the Workflow Runtime
owns all of that.

`ExecutionResult.artifacts` contains sanitized Artifact references for the Run
Trace. Artifact binary storage remains outside this connector contract.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from app.connectors.result import HTTPInvocationResult


@dataclass
class ExecutionError(Exception):
    """Structured execution error shared by Connectors and the Runtime.

    Inherits Exception so it can be raised and caught across the execution
    boundary while still carrying structured fields.
    """

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable, "details": self.details}


@dataclass
class ExecutionResult:
    status: Literal["success", "failed"]
    output: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    error: ExecutionError | None = None


class Connector(ABC):
    @abstractmethod
    async def execute(self, request: Any) -> ExecutionResult:
        raise NotImplementedError


def http_invocation_to_execution_result(result: HTTPInvocationResult) -> ExecutionResult:
    """Map the HTTP transport result onto the unified ExecutionResult."""
    if result.ok:
        return ExecutionResult(
            status="success",
            output=result.output,
            metadata={"status_code": result.status_code},
        )
    return ExecutionResult(
        status="failed",
        retryable=result.retryable,
        metadata={"status_code": result.status_code},
        error=ExecutionError(
            result.error_code or "HTTP_INVOCATION_FAILED",
            result.message or "HTTP invocation failed",
            retryable=result.retryable,
        ),
    )
