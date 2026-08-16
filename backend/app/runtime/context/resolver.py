"""ContextResolver: safe, finite resolution of `{{...}}` Context References.

Supports:
- `{{workflow.input.<path>}}`  -> WorkflowRun input
- `{{workflow.variables.<path>}}` -> Workflow variables
- `{{nodes.<id>.output.<path>}}` -> NodeRun output
- `{{run.<path>}}` -> Run metadata (id / created_at / status ...)

A pure reference (the whole string is one reference) preserves the native
type; references embedded in surrounding text are interpolated as strings.
Unresolvable references raise `UnresolvedContextReference` (never silently
return null). No eval / template engine execution.
"""

from typing import Any

from app.core.errors import RelayviaError
from app.domain.workflows.context_reference import ContextReference, extract_context_references, parse_context_reference


class UnresolvedContextReference(Exception):
    def __init__(self, reference: str, message: str) -> None:
        super().__init__(message)
        self.reference = reference
        self.message = message


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _navigate(data: Any, path: str, reference: ContextReference) -> Any:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise UnresolvedContextReference(reference.raw, f"Value {path!r} is not available")
        current = current[part]
    return current


class ContextResolver:
    def __init__(
        self,
        *,
        workflow_input: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
        node_outputs: dict[str, Any] | None = None,
        run: dict[str, Any] | None = None,
    ) -> None:
        self.workflow_input = dict(workflow_input or {})
        self.variables = dict(variables or {})
        self.node_outputs: dict[str, Any] = dict(node_outputs or {})
        self.run = dict(run or {})

    def resolve(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self.resolve(child) for key, child in value.items()}
        if isinstance(value, list):
            return [self.resolve(child) for child in value]
        if isinstance(value, str):
            return self._resolve_string(value)
        return value

    def _resolve_string(self, text: str) -> Any:
        if "{{" not in text:
            return text
        pure = _as_pure_reference(text)
        if pure is not None:
            return self.resolve_reference(pure)
        references = _parse_all(text)
        resolved = text
        for reference in references:
            resolved = resolved.replace(reference.raw, _stringify(self.resolve_reference(reference)))
        return resolved

    def resolve_reference(self, reference: ContextReference) -> Any:
        scope = reference.scope
        if scope == "workflow.input":
            return _navigate(self.workflow_input, reference.path, reference)
        if scope == "workflow.variables":
            return _navigate(self.variables, reference.path, reference)
        if scope == "run":
            return _navigate(self.run, reference.path, reference)
        if reference.node_id is not None:
            output = self.node_outputs.get(reference.node_id)
            if output is None:
                raise UnresolvedContextReference(reference.raw, f"Node {reference.node_id!r} has no output yet")
            return _navigate(output, reference.path, reference)
        raise UnresolvedContextReference(reference.raw, f"Unsupported reference scope {scope!r}")


def _as_pure_reference(text: str) -> ContextReference | None:
    try:
        return parse_context_reference(text)
    except RelayviaError:
        return None


def _parse_all(text: str) -> list[ContextReference]:
    try:
        return extract_context_references(text)
    except RelayviaError as exc:
        raise UnresolvedContextReference(text, exc.message) from exc
