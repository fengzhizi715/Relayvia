"""Shell-based Tool execution (shell / git / test_command subtypes).

Runs a command as a subprocess with an optional working directory and a hard
timeout. The process is terminated on timeout. Command and cwd come from the
Graph; the Worker is the controlled execution environment.
"""

import asyncio

from app.connectors.base import ExecutionError, ExecutionResult
from app.connectors.tools.base import ToolConnector, ToolInvocationConfig


class ShellToolConnector(ToolConnector):
    async def execute(self, config: ToolInvocationConfig) -> ExecutionResult:
        command = config.command.strip()
        if not command:
            return ExecutionResult(
                status="failed",
                error=ExecutionError("EMPTY_TOOL_COMMAND", "Tool command is empty", retryable=False),
            )
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=config.working_directory,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:
            return ExecutionResult(
                status="failed",
                error=ExecutionError("TOOL_SPAWN_FAILED", str(exc), retryable=False),
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=config.timeout_seconds
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return ExecutionResult(
                status="failed",
                error=ExecutionError(
                    "TOOL_TIMEOUT",
                    f"Tool command timed out after {config.timeout_seconds}s",
                    retryable=False,
                ),
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        metadata = {"exit_code": process.returncode, "stderr": stderr}
        if process.returncode != 0:
            return ExecutionResult(
                status="failed",
                retryable=True,
                metadata=metadata,
                error=ExecutionError(
                    "TOOL_EXIT_NONZERO",
                    f"Tool command exited with status {process.returncode}",
                    retryable=True,
                    details={"exit_code": process.returncode, "stderr": stderr[-2000:]},
                ),
            )
        return ExecutionResult(status="success", output={"stdout": stdout, "exit_code": process.returncode}, metadata=metadata)
