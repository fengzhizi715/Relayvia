"""Parsing and dependency extraction for Workflow Context References."""

from dataclasses import dataclass
import re
from typing import Any

from app.core.errors import RelayviaError


_IDENTIFIER = r"[A-Za-z0-9_-]+"
_PATH = rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})*"
_REFERENCE = re.compile(
    rf"\{{\{{\s*(?P<scope>workflow\.input|workflow\.variables|nodes\.(?P<node_id>{_IDENTIFIER})\.output|run)\.(?P<path>{_PATH})\s*\}}\}}"
)
_TEMPLATE = re.compile(r"\{\{.*?\}\}")


@dataclass(frozen=True)
class ContextReference:
    """A parsed, unresolved reference used by a Workflow definition."""

    raw: str
    scope: str
    path: str
    node_id: str | None = None


def parse_context_reference(value: str) -> ContextReference:
    match = _REFERENCE.fullmatch(value)
    if match is None:
        raise RelayviaError(
            "INVALID_CONTEXT_REFERENCE",
            "Context reference syntax is invalid",
            details={"reference": value},
        )
    return ContextReference(
        raw=value,
        scope=match.group("scope"),
        path=match.group("path"),
        node_id=match.group("node_id"),
    )


def parse_context_references(value: str) -> list[ContextReference]:
    """Parse all template references in a string, rejecting malformed braces."""

    if "{{" not in value and "}}" not in value:
        return []
    matches = list(_TEMPLATE.finditer(value))
    if "{{" in value and not matches:
        raise RelayviaError(
            "INVALID_CONTEXT_REFERENCE",
            "Context reference is missing a closing delimiter",
            details={"value": value},
        )
    references: list[ContextReference] = []
    for match in matches:
        references.append(parse_context_reference(match.group(0)))
    if value.count("{{") != value.count("}}"):
        raise RelayviaError(
            "INVALID_CONTEXT_REFERENCE",
            "Context reference delimiters are unbalanced",
            details={"value": value},
        )
    return references


def extract_context_references(value: Any) -> list[ContextReference]:
    """Recursively parse references in JSON-compatible values."""

    references: list[ContextReference] = []
    if isinstance(value, str):
        references.extend(parse_context_references(value))
    elif isinstance(value, dict):
        for child in value.values():
            references.extend(extract_context_references(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(extract_context_references(child))
    return references


def extract_node_references(value: Any) -> list[str]:
    """Return unique node IDs referenced by a JSON-compatible value."""

    return sorted({reference.node_id for reference in extract_context_references(value) if reference.node_id})


__all__ = [
    "ContextReference",
    "extract_context_references",
    "extract_node_references",
    "parse_context_reference",
    "parse_context_references",
]

