"""Structured Validation issues and results."""

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["error", "warning"]


class ValidationIssue(BaseModel):
    """A single, structured validation finding. `node_id` / `edge_id` allow the
    Frontend to locate and focus the exact element; `field` points at the
    specific config / mapping path."""

    code: str
    severity: Severity
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    field: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Aggregated result. `valid` is True only when there are zero errors.
    Warnings never block execution readiness."""

    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)

    @classmethod
    def from_issues(cls, issues: list[ValidationIssue]) -> "ValidationResult":
        return cls(
            valid=not any(issue.severity == "error" for issue in issues),
            errors=[issue for issue in issues if issue.severity == "error"],
            warnings=[issue for issue in issues if issue.severity == "warning"],
        )
