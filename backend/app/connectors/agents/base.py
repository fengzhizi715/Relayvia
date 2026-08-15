from abc import ABC, abstractmethod

from app.connectors.http import HTTPConnectionConfig
from app.connectors.result import ConnectionTestResult


class AgentConnector(ABC):
    @abstractmethod
    async def test_connection(self, config: HTTPConnectionConfig) -> ConnectionTestResult:
        raise NotImplementedError

