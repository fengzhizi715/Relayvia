"""Tool Connector contract.

Tools execute in a Worker-controlled environment (never from a FastAPI request
handler). `ToolInvocationConfig` carries only the command and its working
directory; no credentials or environment secrets are injected.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.connectors.base import ExecutionResult


@dataclass(frozen=True)
class ToolInvocationConfig:
    command: str
    working_directory: str | None = None
    timeout_seconds: int = 60


class ToolConnector(ABC):
    @abstractmethod
    async def execute(self, config: ToolInvocationConfig) -> ExecutionResult:
        raise NotImplementedError
