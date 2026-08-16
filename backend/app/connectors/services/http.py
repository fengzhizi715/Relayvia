from app.connectors.base import ExecutionResult, http_invocation_to_execution_result
from app.connectors.http import HTTPConnectionConfig, HTTPInvocationConfig, invoke_http, test_http_connection
from app.connectors.result import ConnectionTestResult
from app.connectors.services.base import ServiceConnector


class HTTPServiceConnector(ServiceConnector):
    async def test_connection(self, config: HTTPConnectionConfig) -> ConnectionTestResult:
        return await test_http_connection(config)

    async def execute(self, config: HTTPInvocationConfig) -> ExecutionResult:
        result = await invoke_http(config)
        return http_invocation_to_execution_result(result)
