"""Tool Connector contract.

Tool commands are deliberately not executed by the Relayvia server Worker.
They must be delegated to a registered Relayvia Runner, which owns the local
workspace and process environment.  The current V1 connector remains a
structured compatibility boundary while Runner dispatch is introduced.
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
