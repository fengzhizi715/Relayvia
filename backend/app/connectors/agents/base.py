from abc import ABC, abstractmethod

from app.connectors.http import HTTPConnectionConfig, HTTPInvocationConfig
from app.connectors.result import ConnectionTestResult, HTTPInvocationResult


class AgentConnector(ABC):
    @abstractmethod
    async def test_connection(self, config: HTTPConnectionConfig) -> ConnectionTestResult:
        raise NotImplementedError

    @abstractmethod
    async def invoke(self, config: HTTPInvocationConfig) -> HTTPInvocationResult:
        raise NotImplementedError
