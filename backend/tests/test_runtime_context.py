import pytest

from app.runtime.context import ContextResolver, UnresolvedContextReference


def make_resolver(**overrides):
    defaults = dict(
        workflow_input={"requirement": "build a parser", "meta": {"priority": 2}},
        variables={"threshold": 0.8},
        node_outputs={"planner": {"result": {"score": 95}, "status": "done"}},
        run={"id": "run-123", "status": "running"},
    )
    defaults.update(overrides)
    return ContextResolver(**defaults)


def test_workflow_input_read():
    resolver = make_resolver()
    assert resolver.resolve_reference(_ref("{{workflow.input.requirement}}")) == "build a parser"
    assert resolver.resolve("{{workflow.input.meta.priority}}") == 2


def test_workflow_variable_read():
    resolver = make_resolver()
    assert resolver.resolve("{{workflow.variables.threshold}}") == 0.8


def test_node_output_read():
    resolver = make_resolver()
    assert resolver.resolve("{{nodes.planner.output.result.score}}") == 95
    assert resolver.resolve("{{nodes.planner.output.status}}") == "done"


def test_run_metadata_read():
    resolver = make_resolver()
    assert resolver.resolve("{{run.id}}") == "run-123"


def test_pending_node_output_unresolved():
    resolver = make_resolver(node_outputs={})
    with pytest.raises(UnresolvedContextReference):
        resolver.resolve("{{nodes.planner.output.result}}")


def test_missing_property_unresolved():
    resolver = make_resolver()
    with pytest.raises(UnresolvedContextReference):
        resolver.resolve("{{nodes.planner.output.nope}}")


def test_template_interpolation_returns_string():
    resolver = make_resolver()
    assert resolver.resolve("Review {{nodes.planner.output.status}} with {{workflow.input.requirement}}") == (
        "Review done with build a parser"
    )


def test_pure_reference_preserves_native_type():
    resolver = make_resolver()
    assert isinstance(resolver.resolve("{{workflow.variables.threshold}}"), float)
    assert isinstance(resolver.resolve("{{nodes.planner.output.result.score}}"), int)


def test_non_string_values_pass_through():
    resolver = make_resolver()
    assert resolver.resolve({"task": "{{workflow.input.requirement}}", "tags": ["a", "b"]}) == {
        "task": "build a parser",
        "tags": ["a", "b"],
    }


def test_boolean_interpolation():
    resolver = make_resolver(node_outputs={"a": {"ok": True}})
    assert resolver.resolve("ok={{nodes.a.output.ok}}") == "ok=true"


def _ref(value: str):
    from app.domain.workflows.context_reference import parse_context_reference

    return parse_context_reference(value)
