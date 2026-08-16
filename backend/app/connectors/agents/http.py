from app.connectors.agents.base import AgentConnector
from app.connectors.http import HTTPConnectionConfig, HTTPInvocationConfig, invoke_http, test_http_connection
from app.connectors.result import ConnectionTestResult, HTTPInvocationResult


class HTTPAgentConnector(AgentConnector):
    async def test_connection(self, config: HTTPConnectionConfig) -> ConnectionTestResult:
        return await test_http_connection(config)

    async def invoke(self, config: HTTPInvocationConfig) -> HTTPInvocationResult:
        return await invoke_http(config)
