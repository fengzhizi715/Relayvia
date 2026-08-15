from typing import Any

from jsonschema import Draft7Validator, SchemaError

from app.core.errors import RelayviaError


SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "x-api-key",
}
SENSITIVE_METADATA_NAMES = {"password", "token", "secret", "api_key", "authorization"}


def validate_json_schema(value: dict[str, Any], *, field: str) -> dict[str, Any]:
    try:
        Draft7Validator.check_schema(value)
    except SchemaError as exc:
        raise RelayviaError(
            "INVALID_SCHEMA",
            f"{field} must be a valid JSON Schema",
            details={"field": field},
        ) from exc
    return value


def validate_headers(headers: dict[str, str], *, field: str = "headers") -> dict[str, str]:
    for name in headers:
        if name.lower() in SENSITIVE_HEADER_NAMES:
            raise RelayviaError(
                "SECRET_IN_CONFIG",
                "Authentication secrets must be stored in a Credential",
                details={"field": field, "header": name},
            )
    return headers


def validate_metadata(metadata: dict[str, Any], *, field: str = "metadata") -> dict[str, Any]:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(key).lower().replace("-", "_")
                if normalized_key in SENSITIVE_METADATA_NAMES or any(
                    marker in normalized_key for marker in ("password", "token", "secret")
                ):
                    raise RelayviaError(
                        "SECRET_IN_CONFIG",
                        "Authentication secrets must be stored in a Credential",
                        details={"field": field, "key": str(key)},
                    )
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(metadata)
    return metadata
