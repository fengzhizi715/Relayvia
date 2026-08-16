"""RuntimeContext: the Workflow-level execution context.

Source of truth per WorkflowRun:
- `input`: the validated Workflow input (workflow_runs.input_json)
- `variables`: Workflow variables initialized from the Definition defaults
  (workflow_runs.variables_json)

Node Outputs are intentionally NOT stored here. They live in
`node_runs.output_json` (single source of truth); the `ContextResolver`
reads them from the NodeRun map.
"""

from typing import Any


class RuntimeContext:
    def __init__(self, *, input_data: dict[str, Any] | None = None, variables: dict[str, Any] | None = None) -> None:
        self.input: dict[str, Any] = dict(input_data or {})
        self.variables: dict[str, Any] = dict(variables or {})

    def to_persisted(self) -> dict[str, Any]:
        return {"input": self.input, "variables": self.variables}

    @classmethod
    def from_persisted(cls, data: dict[str, Any] | None) -> "RuntimeContext":
        payload = data or {}
        return cls(input_data=payload.get("input"), variables=payload.get("variables"))
