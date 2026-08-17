"""Coding Agent Connector.

A Coding Agent (Codex / OpenCode / Cursor) is invoked through the Relayvia
Runner inside an isolated Workspace. The Backend-side Connector owns the
CLI-specific command construction; the Runner executes the command (it does
not know product-specific behavior). Capability detection tells the Runner
which coding CLIs actually exist on its machine.
"""

import shlex
import shutil
from typing import Any

from app.connectors.agents.base import AgentConnector
from app.connectors.base import ExecutionError, ExecutionResult
from app.connectors.http import HTTPConnectionConfig, HTTPInvocationConfig
from app.connectors.result import ConnectionTestResult


class CodingAgentConnector(AgentConnector):
    """Marker base for coding-agent adapters executed on a Runner."""

    cli_name: str = ""
    capability: str = ""

    async def test_connection(self, config: HTTPConnectionConfig) -> ConnectionTestResult:
        from datetime import datetime, timezone
        from app.connectors.result import ConnectionTestStatus

        return ConnectionTestResult(
            status=ConnectionTestStatus.HEALTHY if shutil.which(self.cli_name) else ConnectionTestStatus.UNHEALTHY,
            checked_at=datetime.now(timezone.utc),
            message=f"{self.cli_name} CLI {'found' if shutil.which(self.cli_name) else 'not found'}",
        )

    def build_command(self, *, task: str, timeout_seconds: int, executable: str | None = None) -> str:
        raise NotImplementedError

    async def execute(self, config: HTTPInvocationConfig) -> ExecutionResult:
        # Coding agents are executed by the Runner; this HTTP-shape invoke is
        # never used directly by the Runtime.
        return ExecutionResult(status="failed", error=ExecutionError("RUNNER_REQUIRED", "Coding agents execute on a Runner", retryable=False))


class CodexConnector(CodingAgentConnector):
    cli_name = "codex"
    capability = "codex"

    def build_command(self, *, task: str, timeout_seconds: int, executable: str | None = None) -> str:
        cli = executable or self.cli_name
        return f"{shlex.quote(cli)} exec --json {shlex.quote(task)}"


def detect_coding_agent_capabilities() -> list[str]:
    """Report which coding-agent CLIs are actually installed on this machine."""
    capabilities: list[str] = []
    for connector in (CodexConnector(),):
        if shutil.which(connector.cli_name):
            capabilities.append(connector.capability)
    return capabilities
