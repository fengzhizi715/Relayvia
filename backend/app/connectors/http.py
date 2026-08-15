from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

import httpx

from app.connectors.result import ConnectionTestResult, ConnectionTestStatus
from app.domain.credentials.model import Credential, CredentialType
from app.infrastructure.security.crypto import CredentialCrypto


@dataclass(frozen=True)
class HTTPConnectionConfig:
    url: str | None
    timeout_seconds: int
    headers: dict[str, str] = field(default_factory=dict)
    credential: Credential | None = None


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
