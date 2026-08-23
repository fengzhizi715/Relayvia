import ipaddress
import socket
from urllib.parse import urljoin, urlparse

from app.core.config import get_settings
from app.core.errors import RelayviaError


ALLOWED_URL_SCHEMES = {"http", "https"}


def validate_http_url(value: str, *, field: str, allow_private_network_urls: bool | None = None) -> str:
    """Validate a target URL before storing or invoking it.

    SSRF defense is policy-based rather than a blanket localhost ban: local
    and edge deployments can opt in with ``RELAYVIA_ALLOW_PRIVATE_NETWORK_URLS``.
    The default rejects every non-global IP resolved from a hostname and the
    policy is re-applied immediately before every HTTP request.
    """
    parsed = urlparse(value)
    if parsed.scheme not in ALLOWED_URL_SCHEMES or not parsed.netloc or parsed.username or parsed.password:
        raise RelayviaError(
            "INVALID_URL",
            f"{field} must be a valid http or https URL",
            details={"field": field},
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise RelayviaError("INVALID_URL", f"{field} has an invalid port", details={"field": field}) from exc
    if port is not None and not 1 <= port <= 65535:
        raise RelayviaError("INVALID_URL", f"{field} has an invalid port", details={"field": field})
    host = parsed.hostname
    if not host:
        raise RelayviaError("INVALID_URL", f"{field} must include a host", details={"field": field})
    allow_private = get_settings().allow_private_network_urls if allow_private_network_urls is None else allow_private_network_urls
    if not allow_private:
        _reject_non_public_host(host, field=field)
    return value.rstrip("/")


def _reject_non_public_host(host: str, *, field: str) -> None:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise RelayviaError(
            "URL_HOST_UNRESOLVABLE",
            f"{field} host could not be resolved",
            details={"field": field},
        ) from exc
    if not addresses:
        raise RelayviaError("URL_HOST_UNRESOLVABLE", f"{field} host could not be resolved", details={"field": field})
    blocked: list[str] = []
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:  # pragma: no cover - getaddrinfo guarantees addresses
            raise RelayviaError("INVALID_URL", f"{field} host is invalid", details={"field": field}) from exc
        if not ip.is_global:
            blocked.append(address)
    if blocked:
        raise RelayviaError(
            "URL_PRIVATE_NETWORK_FORBIDDEN",
            f"{field} resolves to a private or reserved network address",
            details={"field": field},
        )


def normalize_action_path(value: str) -> str:
    if not value or not value.strip():
        raise RelayviaError("INVALID_PATH", "Service action path cannot be empty")
    path = value.strip()
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc or "\\" in path:
        raise RelayviaError(
            "INVALID_PATH",
            "Service action path must be relative",
            details={"field": "path"},
        )
    return "/" + path.lstrip("/")


def combine_service_url(base_url: str, path: str) -> str:
    base = validate_http_url(base_url, field="base_url")
    normalized_path = normalize_action_path(path)
    return urljoin(f"{base}/", normalized_path.lstrip("/"))
