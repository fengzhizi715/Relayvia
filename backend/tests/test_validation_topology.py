from validation_helpers import (
    agent,
    agent_node,
    codes_of,
    input_node,
    output_node,
    raw_edge,
    raw_node,
    run,
)

IN = input_node()
OUT = output_node()
A = agent_node("a")
B = agent_node("b")


def test_valid_linear_graph():
    result = run([IN, A, OUT], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert result.valid is True
    assert result.errors == []


def test_empty_graph():
    result = run([], [])
    assert result.valid is False
    assert codes_of(result) == {"GRAPH_EMPTY"}


def test_missing_input_node():
    result = run([A, OUT], [raw_edge("e1", "a", "output")], agents={"agent-1": agent()})
    assert "MISSING_INPUT_NODE" in codes_of(result)


def test_multiple_input_nodes():
    result = run(
        [input_node("in1"), input_node("in2"), A, OUT],
        [raw_edge("e1", "in1", "a"), raw_edge("e2", "a", "output")],
        agents={"agent-1": agent()},
    )
    assert "MULTIPLE_INPUT_NODES" in codes_of(result)


def test_missing_output_node():
    result = run([IN, A], [raw_edge("e1", "input", "a")], agents={"agent-1": agent()})
    assert "MISSING_OUTPUT_NODE" in codes_of(result)


def test_self_connection():
    result = run([IN, A, OUT], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "a")], agents={"agent-1": agent()})
    assert "SELF_CONNECTION" in codes_of(result)


def test_cycle_detection():
    result = run(
        [IN, A, B, OUT],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "b"), raw_edge("e3", "b", "a"), raw_edge("e4", "b", "output")],
        agents={"agent-1": agent()},
    )
    assert "UNSUPPORTED_CYCLE" in codes_of(result)


def test_unreachable_node():
    orphan = agent_node("orphan")
    result = run(
        [IN, A, OUT, orphan],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")],
        agents={"agent-1": agent()},
    )
    issues = result.errors
    assert any(issue.code == "UNREACHABLE_NODE" and issue.node_id == "orphan" for issue in issues)


def test_dead_end_branch():
    dead = agent_node("dead")
    result = run(
        [IN, A, OUT, dead],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "input", "dead"), raw_edge("e3", "a", "output")],
        agents={"agent-1": agent()},
    )
    issues = result.errors
    assert any(issue.code == "DEAD_END_BRANCH" and issue.node_id == "dead" for issue in issues)


def test_duplicate_connection():
    result = run(
        [IN, A, OUT],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "input", "a"), raw_edge("e3", "a", "output")],
        agents={"agent-1": agent()},
    )
    assert "DUPLICATE_CONNECTION" in codes_of(result)


def test_input_node_cannot_have_incoming():
    upstream = agent_node("upstream")
    result = run(
        [IN, A, OUT, upstream],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "upstream", "input"), raw_edge("e3", "a", "output")],
        agents={"agent-1": agent()},
    )
    assert any(issue.code == "INVALID_INPUT_NODE_EDGE" for issue in result.errors)


def test_output_node_cannot_have_outgoing():
    extra = agent_node("extra")
    result = run(
        [IN, A, OUT, extra],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output"), raw_edge("e3", "output", "extra")],
        agents={"agent-1": agent()},
    )
    assert any(issue.code == "INVALID_OUTPUT_NODE_EDGE" for issue in result.errors)


def test_invalid_edge_target():
    result = run([IN, A, OUT], [raw_edge("e1", "input", "missing")], agents={"agent-1": agent()})
    assert "INVALID_EDGE_TARGET" in codes_of(result)


def test_invalid_edge_source():
    result = run([IN, A, OUT], [raw_edge("e1", "missing", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert "INVALID_EDGE_SOURCE" in codes_of(result)


def test_parallel_requires_two_branches():
    parallel = raw_node("p", "logic", "parallel")
    result = run(
        [IN, parallel, A, OUT],
        [raw_edge("e1", "input", "p"), raw_edge("e2", "p", "a"), raw_edge("e3", "a", "output")],
        agents={"agent-1": agent()},
    )
    assert "INVALID_PARALLEL" in codes_of(result)


def test_merge_requires_two_incoming():
    merge = raw_node("m", "logic", "merge", config={"strategy": "all"})
    result = run(
        [IN, A, merge, OUT],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "m"), raw_edge("e3", "m", "output")],
        agents={"agent-1": agent()},
    )
    assert "INVALID_MERGE" in codes_of(result)


def test_valid_parallel_merge():
    parallel = raw_node("p", "logic", "parallel")
    merge = raw_node("m", "logic", "merge", config={"strategy": "all"})
    left = agent_node("left")
    right = agent_node("right")
    result = run(
        [IN, parallel, left, right, merge, OUT],
        [
            raw_edge("e1", "input", "p"),
            raw_edge("e2", "p", "left"),
            raw_edge("e3", "p", "right"),
            raw_edge("e4", "left", "m"),
            raw_edge("e5", "right", "m"),
            raw_edge("e6", "m", "output"),
        ],
        agents={"agent-1": agent()},
    )
    assert result.valid is True


def test_parallel_branch_bypasses_merge():
    parallel = raw_node("p", "logic", "parallel")
    merge = raw_node("m", "logic", "merge", config={"strategy": "all"})
    left = agent_node("left")
    right = agent_node("right")
    bypass = agent_node("bypass")
    out_a = output_node("out-a")
    out_b = output_node("out-b")
    result = run(
        [IN, parallel, left, right, bypass, merge, out_a, out_b],
        [
            raw_edge("e1", "input", "p"),
            raw_edge("e2", "p", "left"),
            raw_edge("e3", "p", "right"),
            raw_edge("e4", "p", "bypass"),
            raw_edge("e5", "left", "m"),
            raw_edge("e6", "right", "m"),
            raw_edge("e7", "m", "out-a"),
            raw_edge("e8", "bypass", "out-b"),
        ],
        agents={"agent-1": agent()},
    )
    assert "INVALID_PARALLEL_MERGE_STRUCTURE" in codes_of(result)
