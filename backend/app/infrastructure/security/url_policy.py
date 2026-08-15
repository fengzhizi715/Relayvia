from urllib.parse import urljoin, urlparse

from app.core.errors import RelayviaError


ALLOWED_URL_SCHEMES = {"http", "https"}


def validate_http_url(value: str, *, field: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ALLOWED_URL_SCHEMES or not parsed.netloc:
        raise RelayviaError(
            "INVALID_URL",
            f"{field} must be a valid http or https URL",
            details={"field": field},
        )
    return value.rstrip("/")


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

