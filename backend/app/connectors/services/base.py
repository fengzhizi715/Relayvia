from abc import ABC, abstractmethod

from app.connectors.base import Connector, ExecutionResult
from app.connectors.http import HTTPConnectionConfig, HTTPInvocationConfig
from app.connectors.result import ConnectionTestResult


class ServiceConnector(Connector, ABC):
    @abstractmethod
    async def test_connection(self, config: HTTPConnectionConfig) -> ConnectionTestResult:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, config: HTTPInvocationConfig) -> ExecutionResult:
        raise NotImplementedError
