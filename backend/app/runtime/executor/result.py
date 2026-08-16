"""Structured execution errors shared by Runtime / Worker."""

from typing import Any


class ExecutionError:
    def __init__(self, code: str, message: str, *, retryable: bool = False, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable, "details": self.details}

    def __repr__(self) -> str:  # pragma: no cover
        return f"ExecutionError({self.code!r}, retryable={self.retryable})"
