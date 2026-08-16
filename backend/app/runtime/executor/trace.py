"""Safe persistence helpers for connector diagnostics in Run Trace."""

from __future__ import annotations

import json
from typing import Any


_SENSITIVE_KEYWORDS = ("authorization", "cookie", "credential", "password", "secret", "token", "api_key", "apikey")
_MAX_TRACE_BYTES = 32_000
_REDACTED = "***REDACTED***"
_TRUNCATED = "***TRUNCATED***"


def sanitize_metadata(value: Any) -> dict[str, Any]:
    sanitized = _sanitize(value)
    return sanitized if isinstance(sanitized, dict) else {"value": sanitized}


def sanitize_artifacts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items = [_sanitize(item) for item in value]
    return [item for item in items if isinstance(item, dict)]


def sanitize_error(value: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize(value)
    return sanitized if isinstance(sanitized, dict) else {"code": "UNKNOWN", "message": "execution failed", "retryable": False, "details": {}}


def _sanitize(value: Any) -> Any:
    sanitized = _sanitize_value(value)
    try:
        encoded = json.dumps(sanitized, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return _TRUNCATED
    if len(encoded.encode("utf-8")) <= _MAX_TRACE_BYTES:
        return sanitized
    return {"trace": _TRUNCATED}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _REDACTED if _is_sensitive_key(key) else _sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _is_sensitive_key(value: Any) -> bool:
    normalized = str(value).lower().replace("-", "_")
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)
