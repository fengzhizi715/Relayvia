"""Compatibility boundary for shell-like tools.

Direct server-side subprocess execution is intentionally disabled.  A future
Runner connector will dispatch this invocation to a registered Runner instead.
"""

from app.connectors.base import ExecutionError, ExecutionResult
from app.connectors.tools.base import ToolConnector, ToolInvocationConfig


class ShellToolConnector(ToolConnector):
    async def execute(self, config: ToolInvocationConfig) -> ExecutionResult:
        return ExecutionResult(
            status="failed",
            error=ExecutionError(
                "RUNNER_REQUIRED",
                "Tool commands require a registered Relayvia Runner; server-side execution is disabled",
                retryable=False,
            ),
        )
