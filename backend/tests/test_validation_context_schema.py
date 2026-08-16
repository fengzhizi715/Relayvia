from validation_helpers import (
    action,
    agent,
    agent_node,
    codes_of,
    input_node,
    output_node,
    raw_edge,
    raw_node,
    run,
    service,
    service_node,
)


def test_invalid_syntax():
    input_mapping = {"x": "{{nodes.a.output.foo"}
    node = agent_node("a", input_mapping=input_mapping)
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert "INVALID_CONTEXT_REFERENCE" in codes_of(result)


def test_unknown_context_node():
    node = agent_node("a", input_mapping={"x": "{{nodes.ghost.output.result}}"})
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert "UNKNOWN_CONTEXT_NODE" in codes_of(result)


def test_unknown_variable():
    node = agent_node("a", input_mapping={"x": "{{workflow.variables.threshold}}"})
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert "UNKNOWN_VARIABLE" in codes_of(result)


def test_known_variable_is_valid():
    node = agent_node("a", input_mapping={"x": "{{workflow.variables.threshold}}"})
    result = run(
        [input_node(), node, output_node()],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")],
        agents={"agent-1": agent()},
        variables={"threshold": {"type": "number", "default": 0.8}},
    )
    assert result.valid is True


def test_self_reference():
    node = agent_node("a", input_mapping={"x": "{{nodes.a.output.result}}"})
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert "INVALID_CONTEXT_REFERENCE" in codes_of(result)


def test_forward_reference_is_invalid_data_dependency():
    # a -> b -> output, b references a.output which is NOT an upstream dependency of b
    a_node = agent_node("a")
    b_node = agent_node("b", input_mapping={"x": "{{nodes.a.output.result}}"})
    result = run(
        [input_node(), a_node, b_node, output_node()],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "b"), raw_edge("e3", "b", "output")],
        agents={"agent-1": agent()},
    )
    # a is an upstream ancestor of b (a -> b), so this reference IS valid.
    assert result.valid is True


def test_invalid_data_dependency_when_not_upstream():
    # input -> b -> output ; a -> output ; b references a.output (a is not upstream of b)
    a_node = agent_node("a")
    b_node = agent_node("b", input_mapping={"x": "{{nodes.a.output.result}}"})
    result = run(
        [input_node(), a_node, b_node, output_node()],
        [
            raw_edge("e1", "input", "b"),
            raw_edge("e2", "a", "output"),
            raw_edge("e3", "b", "output"),
        ],
        agents={"agent-1": agent()},
    )
    assert "INVALID_DATA_DEPENDENCY" in codes_of(result)


def test_upstream_reference_through_chain_is_valid():
    # input -> a -> b -> output ; b references a.output and input node output implicitly
    a_node = agent_node("a")
    b_node = agent_node("b", input_mapping={"x": "{{nodes.a.output.result}}"})
    result = run(
        [input_node(), a_node, b_node, output_node()],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "b"), raw_edge("e3", "b", "output")],
        agents={"agent-1": agent()},
    )
    assert result.valid is True


def test_parallel_sibling_reference():
    parallel = raw_node("p", "logic", "parallel")
    merge = raw_node("m", "logic", "merge", config={"strategy": "all"})
    a_node = agent_node("a")
    b_node = agent_node("b")
    c_node = agent_node("c", input_mapping={"x": "{{nodes.a.output.result}}"})
    result = run(
        [input_node(), parallel, a_node, b_node, c_node, merge, output_node()],
        [
            raw_edge("e1", "input", "p"),
            raw_edge("e2", "p", "a"),
            raw_edge("e3", "p", "b"),
            raw_edge("e4", "p", "c"),
            raw_edge("e5", "a", "m"),
            raw_edge("e6", "b", "m"),
            raw_edge("e7", "c", "m"),
            raw_edge("e8", "m", "output"),
        ],
        agents={"agent-1": agent()},
    )
    assert "INVALID_PARALLEL_DATA_DEPENDENCY" in codes_of(result)


def test_merge_child_can_reference_all_branches():
    parallel = raw_node("p", "logic", "parallel")
    merge = raw_node("m", "logic", "merge", config={"strategy": "all"})
    a_node = agent_node("a")
    b_node = agent_node("b")
    after = agent_node("after", input_mapping={"x": "{{nodes.a.output.result}}", "y": "{{nodes.b.output.result}}"})
    result = run(
        [input_node(), parallel, a_node, b_node, after, merge, output_node()],
        [
            raw_edge("e1", "input", "p"),
            raw_edge("e2", "p", "a"),
            raw_edge("e3", "p", "b"),
            raw_edge("e4", "a", "m"),
            raw_edge("e5", "b", "m"),
            raw_edge("e6", "m", "after"),
            raw_edge("e7", "after", "output"),
        ],
        agents={"agent-1": agent()},
    )
    assert result.valid is True


def test_unknown_workflow_input_field():
    closed_input = input_node("in", schema={"type": "object", "properties": {"requirement": {"type": "string"}}, "additionalProperties": False})
    node = agent_node("a", input_mapping={"x": "{{workflow.input.typo}}"})
    result = run([closed_input, node, output_node()], [raw_edge("e1", "in", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert "UNKNOWN_WORKFLOW_INPUT" in codes_of(result)


def test_open_input_schema_allows_unknown_field():
    open_input = input_node("in", schema={"type": "object", "properties": {"requirement": {"type": "string"}}})
    node = agent_node("a", input_mapping={"x": "{{workflow.input.anything}}"})
    result = run([open_input, node, output_node()], [raw_edge("e1", "in", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert result.valid is True


def test_unknown_output_field_when_closed():
    a_node = agent_node("a")
    b_node = agent_node("b", input_mapping={"x": "{{nodes.a.output.nope}}"})
    out_schema = {"type": "object", "properties": {"result": {"type": "string"}}, "additionalProperties": False}
    result = run(
        [input_node(), a_node, b_node, output_node()],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "b"), raw_edge("e3", "b", "output")],
        agents={"agent-1": agent(output_schema=out_schema)},
    )
    assert "INVALID_OUTPUT_REFERENCE" in codes_of(result)


def test_unknown_output_schema_skips_field_check():
    a_node = agent_node("a")
    b_node = agent_node("b", input_mapping={"x": "{{nodes.a.output.anything}}"})
    result = run(
        [input_node(), a_node, b_node, output_node()],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "b"), raw_edge("e3", "b", "output")],
        agents={"agent-1": agent(output_schema={})},
    )
    assert result.valid is True


def test_missing_required_input():
    target_schema = {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}
    node = agent_node("a", input_mapping={"language": "python"})
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent(input_schema=target_schema)})
    assert "MISSING_REQUIRED_INPUT" in codes_of(result)


def test_unknown_input_field():
    target_schema = {"type": "object", "properties": {"task": {"type": "string"}}, "additionalProperties": False}
    node = agent_node("a", input_mapping={"task": "hello", "nope": "x"})
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent(input_schema=target_schema)})
    assert "UNKNOWN_INPUT_FIELD" in codes_of(result)


def test_string_mapped_to_number_is_mismatch():
    target_schema = {"type": "object", "properties": {"threshold": {"type": "number"}}}
    node = agent_node("a", input_mapping={"threshold": "not-a-number"})
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent(input_schema=target_schema)})
    assert "SCHEMA_TYPE_MISMATCH" in codes_of(result)


def test_integer_to_number_is_compatible():
    target_schema = {"type": "object", "properties": {"threshold": {"type": "number"}}}
    node = agent_node("a", input_mapping={"threshold": 5})
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent(input_schema=target_schema)})
    assert result.valid is True


def test_number_to_integer_is_narrowing_warning():
    target_schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
    node = agent_node("a", input_mapping={"count": 3.5})
    result = run([input_node(), node, output_node()], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent(input_schema=target_schema)})
    assert result.valid is True
    assert "SCHEMA_TYPE_MISMATCH" in codes_of(result, severity="warning")


def test_template_string_resolves_to_string():
    target_schema = {"type": "object", "properties": {"task": {"type": "string"}}}
    node = agent_node("a", input_mapping={"task": "Review {{nodes.b.output.result}}"})
    b_node = agent_node("b")
    result = run(
        [input_node(), b_node, node, output_node()],
        [raw_edge("e1", "input", "b"), raw_edge("e2", "b", "a"), raw_edge("e3", "a", "output")],
        agents={"agent-1": agent(input_schema=target_schema)},
    )
    assert result.valid is True


def test_pure_reference_uses_source_schema():
    b_out = {"type": "object", "properties": {"score": {"type": "integer"}}, "additionalProperties": False}
    target = {"type": "object", "properties": {"score": {"type": "number"}}}
    b_node = agent_node("b")
    a_node = agent_node("a", input_mapping={"score": "{{nodes.b.output.score}}"})
    result = run(
        [input_node(), b_node, a_node, output_node()],
        [raw_edge("e1", "input", "b"), raw_edge("e2", "b", "a"), raw_edge("e3", "a", "output")],
        agents={"agent-1": agent(output_schema=b_out, input_schema=target)},
    )
    assert result.valid is True


def test_service_action_required_input():
    target_schema = {"type": "object", "properties": {"dataset_id": {"type": "string"}}, "required": ["dataset_id"]}
    node = service_node("s", input_mapping={})
    result = run(
        [input_node(), node, output_node()],
        [raw_edge("e1", "input", "s"), raw_edge("e2", "s", "output")],
        services={"service-1": service()},
        actions={"action-1": action(input_schema=target_schema)},
    )
    assert "MISSING_REQUIRED_INPUT" in codes_of(result)


def _run_with_ref(source_node, target_id: str, *, config_nodes=()):
    """Build input -> source -> output with source referencing target_id's output."""
    node = agent_node("ref", input_mapping={"x": f"{{{{nodes.{target_id}.output.result}}}}"})
    result = run(
        [input_node(), *config_nodes, node, output_node()],
        [raw_edge("e1", "input", "ref"), raw_edge("e2", "ref", "output")],
        agents={"agent-1": agent()},
    )
    return result


def test_cannot_reference_logic_node_output():
    condition = raw_node("c", "logic", "condition", config={"expression": {"left": "x", "operator": ">=", "right": 0}})
    result = _run_with_ref(condition, "c", config_nodes=(condition,))
    assert "INVALID_OUTPUT_REFERENCE" in codes_of(result)


def test_cannot_reference_merge_node_output():
    merge = raw_node("m", "logic", "merge", config={"strategy": "all"})
    result = _run_with_ref(merge, "m", config_nodes=(merge,))
    assert "INVALID_OUTPUT_REFERENCE" in codes_of(result)


def test_cannot_reference_human_output():
    approval = raw_node("h", "human", "approval", config={"title": "Approve?"})
    result = _run_with_ref(approval, "h", config_nodes=(approval,))
    assert "INVALID_OUTPUT_REFERENCE" in codes_of(result)


def test_cannot_reference_data_input_output():
    in_node = input_node("in")
    result = _run_with_ref(in_node, "in", config_nodes=(in_node,))
    assert "INVALID_OUTPUT_REFERENCE" in codes_of(result)


def test_transform_output_fields_are_checked():
    transform = raw_node("t", "data", "transform", config={"mappings": {"value": "{{workflow.input.requirement}}"}})
    ok = run(
        [input_node(), transform, agent_node("ref", input_mapping={"x": "{{nodes.t.output.value}}"}), output_node()],
        [raw_edge("e1", "input", "t"), raw_edge("e2", "t", "ref"), raw_edge("e3", "ref", "output")],
        agents={"agent-1": agent()},
    )
    assert ok.valid is True

    bad = run(
        [input_node(), transform, agent_node("ref", input_mapping={"x": "{{nodes.t.output.nope}}"}), output_node()],
        [raw_edge("e1", "input", "t"), raw_edge("e2", "t", "ref"), raw_edge("e3", "ref", "output")],
        agents={"agent-1": agent()},
    )
    assert "INVALID_OUTPUT_REFERENCE" in codes_of(bad)


def test_reference_to_merge_converged_downstream_is_data_dependency_not_sibling():
    parallel = raw_node("p", "logic", "parallel")
    merge = raw_node("m", "logic", "merge", config={"strategy": "all"})
    a_node = agent_node("a", input_mapping={"x": "{{nodes.c.output.result}}"})
    b_node = agent_node("b")
    c_node = agent_node("c")
    # A references C, which is re-converged through the merge (downstream of
    # merge). C is a forward reference, NOT a parallel sibling.
    result = run(
        [input_node(), parallel, a_node, b_node, c_node, merge, output_node()],
        [
            raw_edge("e1", "input", "p"),
            raw_edge("e2", "p", "a"),
            raw_edge("e3", "p", "b"),
            raw_edge("e4", "a", "m"),
            raw_edge("e5", "b", "m"),
            raw_edge("e6", "m", "c"),
            raw_edge("e7", "c", "output"),
        ],
        agents={"agent-1": agent()},
    )
    assert "INVALID_DATA_DEPENDENCY" in codes_of(result)
    assert "INVALID_PARALLEL_DATA_DEPENDENCY" not in codes_of(result)
