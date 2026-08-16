from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from time import perf_counter
from typing import Any

import httpx

from app.connectors.result import ConnectionTestResult, ConnectionTestStatus, HTTPInvocationResult
from app.domain.credentials.model import Credential, CredentialType
from app.infrastructure.security.crypto import CredentialCrypto


@dataclass(frozen=True)
class HTTPConnectionConfig:
    url: str | None
    timeout_seconds: int
    headers: dict[str, str] = field(default_factory=dict)
    credential: Credential | None = None


@dataclass(frozen=True)
class HTTPInvocationConfig:
    url: str
    method: str
    timeout_seconds: int
    headers: dict[str, str] = field(default_factory=dict)
    credential: Credential | None = None
    json_body: Any = None
    query: dict[str, Any] = field(default_factory=dict)
    retry_on_status: set[int] = field(default_factory=lambda: {408, 429, 500, 502, 503, 504})


def _authentication(config: HTTPConnectionConfig) -> tuple[dict[str, str], tuple[str, str] | None]:
    headers = dict(config.headers)
    basic_auth = None
    if config.credential is None:
        return headers, basic_auth

    payload = CredentialCrypto().decrypt(config.credential.encrypted_payload)
    credential_type = CredentialType(config.credential.type)
    if credential_type is CredentialType.API_KEY:
        headers["X-API-Key"] = str(payload["value"])
    elif credential_type is CredentialType.BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {payload['value']}"
    elif credential_type is CredentialType.BASIC_AUTH:
        basic_auth = (str(payload["username"]), str(payload["password"]))
    return headers, basic_auth


async def test_http_connection(config: HTTPConnectionConfig) -> ConnectionTestResult:
    checked_at = datetime.now(timezone.utc)
    if not config.url:
        return ConnectionTestResult(
            status=ConnectionTestStatus.UNSUPPORTED,
            checked_at=checked_at,
            error_code="HEALTH_CHECK_NOT_CONFIGURED",
            message="A health check URL is not configured",
        )

    headers, basic_auth = _authentication(config)
    started_at = perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=config.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(config.url, headers=headers, auth=basic_auth)
    except httpx.TimeoutException:
        return ConnectionTestResult(
            status=ConnectionTestStatus.UNHEALTHY,
            checked_at=checked_at,
            latency_ms=round((perf_counter() - started_at) * 1000),
            error_code="CONNECTION_TIMEOUT",
            message="Connection timed out",
        )
    except httpx.RequestError:
        return ConnectionTestResult(
            status=ConnectionTestStatus.UNHEALTHY,
            checked_at=checked_at,
            latency_ms=round((perf_counter() - started_at) * 1000),
            error_code="CONNECTION_TEST_FAILED",
            message="Unable to reach the configured health check URL",
        )

    latency_ms = round((perf_counter() - started_at) * 1000)
    if 200 <= response.status_code < 400:
        return ConnectionTestResult(
            status=ConnectionTestStatus.HEALTHY,
            checked_at=checked_at,
            latency_ms=latency_ms,
            message="Connection successful",
        )
    return ConnectionTestResult(
        status=ConnectionTestStatus.UNHEALTHY,
        checked_at=checked_at,
        latency_ms=latency_ms,
        error_code=f"HTTP_{response.status_code}",
        message=f"HTTP {response.status_code} {response.reason_phrase}",
    )


# Cap on the response body read by a single invocation. Protects the Worker
# from unbounded response sizes; oversized responses are treated as a
# non-retryable failure (a retry will not make the body smaller).
MAX_RESPONSE_BYTES = 1_000_000


async def invoke_http(config: HTTPInvocationConfig) -> HTTPInvocationResult:
    """Invoke a configured HTTP capability without persisting secret details.

    The response body is streamed and capped at `MAX_RESPONSE_BYTES`; larger
    responses are rejected as `RESPONSE_TOO_LARGE` (non-retryable).
    """
    headers, basic_auth = _authentication(
        HTTPConnectionConfig(
            url=config.url,
            timeout_seconds=config.timeout_seconds,
            headers=config.headers,
            credential=config.credential,
        )
    )
    status_code = None
    try:
        async with httpx.AsyncClient(
            timeout=config.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(
                config.method,
                config.url,
                headers=headers,
                auth=basic_auth,
                params=config.query or None,
                json=config.json_body,
            ) as response:
                status_code = response.status_code
                if not 200 <= response.status_code < 300:
                    return HTTPInvocationResult(
                        ok=False,
                        status_code=response.status_code,
                        retryable=response.status_code in config.retry_on_status,
                        error_code=f"HTTP_{response.status_code}",
                        message=f"HTTP endpoint returned status {response.status_code}",
                    )
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        return HTTPInvocationResult(
                            ok=False,
                            status_code=response.status_code,
                            retryable=False,
                            error_code="RESPONSE_TOO_LARGE",
                            message=f"HTTP response exceeded {MAX_RESPONSE_BYTES} bytes",
                        )
    except httpx.TimeoutException:
        return HTTPInvocationResult(ok=False, retryable=True, error_code="HTTP_TIMEOUT", message="HTTP invocation timed out")
    except httpx.RequestError:
        return HTTPInvocationResult(
            ok=False,
            retryable=True,
            error_code="HTTP_REQUEST_FAILED",
            message="Unable to reach the configured HTTP endpoint",
        )

    text = bytes(content).decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except ValueError:
        payload = {"body": text}
    if not isinstance(payload, dict):
        payload = {"result": payload}
    return HTTPInvocationResult(ok=True, status_code=status_code, output=payload)
