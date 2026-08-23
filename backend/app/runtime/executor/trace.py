"""Safe persistence helpers for connector diagnostics in Run Trace."""

from __future__ import annotations

import json
import re
from typing import Any


_SENSITIVE_KEYWORDS = ("authorization", "cookie", "credential", "password", "secret", "token", "api_key", "apikey")
_MAX_TRACE_BYTES = 32_000
_REDACTED = "***REDACTED***"
_TRUNCATED = "***TRUNCATED***"


def sanitize_metadata(value: Any, *, sensitive_values: set[str] | None = None) -> dict[str, Any]:
    sanitized = _sanitize(value, sensitive_values=sensitive_values)
    return sanitized if isinstance(sanitized, dict) else {"value": sanitized}


def sanitize_artifacts(value: Any, *, sensitive_values: set[str] | None = None) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items = [_sanitize(item, sensitive_values=sensitive_values) for item in value]
    return [item for item in items if isinstance(item, dict)]


def sanitize_error(value: dict[str, Any], *, sensitive_values: set[str] | None = None) -> dict[str, Any]:
    sanitized = _sanitize(value, sensitive_values=sensitive_values)
    return sanitized if isinstance(sanitized, dict) else {"code": "UNKNOWN", "message": "execution failed", "retryable": False, "details": {}}


def sanitize_output(value: Any, *, sensitive_values: set[str] | None = None) -> dict[str, Any]:
    """Sanitize Connector / Runner output before it becomes durable Context.

    Output is as observable as metadata and errors: a capability can echo an
    Authorization header or a credential value in its JSON response.  The
    caller can pass credential values held only in worker memory so exact
    echoes are removed too; those values never enter the persisted result.
    """
    sanitized = _sanitize(value, sensitive_values=sensitive_values)
    return sanitized if isinstance(sanitized, dict) else {"result": sanitized}


def _sanitize(value: Any, *, sensitive_values: set[str] | None = None) -> Any:
    sanitized = _sanitize_value(value, sensitive_values=sensitive_values or set())
    try:
        encoded = json.dumps(sanitized, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return _TRUNCATED
    if len(encoded.encode("utf-8")) <= _MAX_TRACE_BYTES:
        return sanitized
    return {"trace": _TRUNCATED}


def _sanitize_value(value: Any, *, sensitive_values: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _REDACTED if _is_sensitive_key(key) else _sanitize_value(item, sensitive_values=sensitive_values)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item, sensitive_values=sensitive_values) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item, sensitive_values=sensitive_values) for item in value]
    if isinstance(value, str):
        return _redact_text(value, sensitive_values)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _is_sensitive_key(value: Any) -> bool:
    normalized = str(value).lower().replace("-", "_")
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)


_INLINE_SECRET = re.compile(r"(?i)\b(authorization|api[_-]?key|token|password|secret)\b\s*([:=])\s*([^\s,;]+)")


def _redact_text(value: str, sensitive_values: set[str]) -> str:
    sanitized = _INLINE_SECRET.sub(lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}", value)
    # Do not attempt to redact very short values: replacing e.g. "on" would
    # corrupt normal output. Credential values are normally high entropy and
    # the exact replacement protects a raw echo even without a sensitive key.
    for secret in sorted((item for item in sensitive_values if len(item) >= 4), key=len, reverse=True):
        sanitized = sanitized.replace(secret, _REDACTED)
    return sanitized
