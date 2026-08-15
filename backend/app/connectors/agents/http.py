from app.connectors.agents.base import AgentConnector
from app.connectors.http import HTTPConnectionConfig, test_http_connection
from app.connectors.result import ConnectionTestResult


class HTTPAgentConnector(AgentConnector):
    async def test_connection(self, config: HTTPConnectionConfig) -> ConnectionTestResult:
        return await test_http_connection(config)

