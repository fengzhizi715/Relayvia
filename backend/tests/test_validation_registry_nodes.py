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

IN = input_node()
OUT = output_node()
A = agent_node("a")
B = agent_node("b")


def test_valid_agent():
    result = run([IN, A, OUT], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert result.valid is True


def test_missing_agent_reference():
    result = run([IN, agent_node("a", agent_id=""), OUT], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")])
    assert "MISSING_AGENT_REFERENCE" in codes_of(result)


def test_agent_not_found():
    result = run([IN, A, OUT], [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")])
    assert "AGENT_NOT_FOUND" in codes_of(result)


def test_agent_disabled_is_error():
    result = run(
        [IN, A, OUT],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")],
        agents={"agent-1": agent(enabled=False)},
    )
    assert "AGENT_DISABLED" in codes_of(result)
    assert result.valid is False


def test_agent_unhealthy_is_warning_not_error():
    result = run(
        [IN, A, OUT],
        [raw_edge("e1", "input", "a"), raw_edge("e2", "a", "output")],
        agents={"agent-1": agent(status="unhealthy")},
    )
    assert result.valid is True
    assert "AGENT_UNHEALTHY" in codes_of(result, severity="warning")


def test_missing_service_and_action_references():
    node = service_node("s", service_id="", action_id="")
    result = run([IN, node, OUT], [raw_edge("e1", "input", "s"), raw_edge("e2", "s", "output")])
    assert {"MISSING_SERVICE_REFERENCE", "MISSING_SERVICE_ACTION_REFERENCE"} <= codes_of(result)


def test_service_not_found_and_action_not_found():
    result = run([IN, service_node("s"), OUT], [raw_edge("e1", "input", "s"), raw_edge("e2", "s", "output")])
    assert "SERVICE_NOT_FOUND" in codes_of(result)
    assert "SERVICE_ACTION_NOT_FOUND" in codes_of(result)


def test_service_action_mismatch():
    result = run(
        [IN, service_node("s"), OUT],
        [raw_edge("e1", "input", "s"), raw_edge("e2", "s", "output")],
        services={"service-1": service()},
        actions={"action-1": action(service_id="other-service")},
    )
    assert "SERVICE_ACTION_MISMATCH" in codes_of(result)


def test_disabled_service_and_action():
    result = run(
        [IN, service_node("s"), OUT],
        [raw_edge("e1", "input", "s"), raw_edge("e2", "s", "output")],
        services={"service-1": service(enabled=False)},
        actions={"action-1": action(enabled=False)},
    )
    assert "SERVICE_DISABLED" in codes_of(result)
    assert "SERVICE_ACTION_DISABLED" in codes_of(result)


def test_service_unhealthy_is_warning():
    result = run(
        [IN, service_node("s"), OUT],
        [raw_edge("e1", "input", "s"), raw_edge("e2", "s", "output")],
        services={"service-1": service(status="unhealthy")},
        actions={"action-1": action()},
    )
    assert result.valid is True
    assert "SERVICE_UNHEALTHY" in codes_of(result, severity="warning")


def test_tool_requires_command():
    tool = raw_node("t", "tool", "shell", config={"command": "", "timeout_seconds": 600})
    result = run([IN, tool, OUT], [raw_edge("e1", "input", "t"), raw_edge("e2", "t", "output")])
    assert "MISSING_REQUIRED_CONFIG" in codes_of(result)


def test_condition_branches_true_and_false_required():
    condition = raw_node("c", "logic", "condition", config={"expression": {"left": "x", "operator": ">=", "right": 0}})
    result = run(
        [IN, condition, OUT],
        [raw_edge("e1", "input", "c"), raw_edge("e2", "c", "output", source_handle="true")],
    )
    codes = codes_of(result)
    assert "INVALID_CONDITION_BRANCH" in codes
    assert any(issue.code == "INVALID_CONDITION_BRANCH" and issue.details.get("branch") == "false" for issue in result.errors)


def test_condition_duplicate_true_branch():
    condition = raw_node("c", "logic", "condition", config={"expression": {"left": "x", "operator": ">=", "right": 0}})
    out_a = output_node("out-a")
    out_b = output_node("out-b")
    result = run(
        [IN, condition, out_a, out_b],
        [
            raw_edge("e1", "input", "c"),
            raw_edge("e2", "c", "out-a", source_handle="true"),
            raw_edge("e3", "c", "out-b", source_handle="true"),
            raw_edge("e4", "c", "out-a", source_handle="false"),
        ],
    )
    assert "INVALID_CONDITION_BRANCH" in codes_of(result)


def test_condition_invalid_operator():
    condition = raw_node("c", "logic", "condition", config={"expression": {"left": "x", "operator": "evil", "right": 1}})
    result = run(
        [IN, condition, OUT],
        [raw_edge("e1", "input", "c"), raw_edge("e2", "c", "output", source_handle="true"), raw_edge("e3", "c", "output", source_handle="false")],
    )
    assert "INVALID_CONDITION_OPERATOR" in codes_of(result)


def test_wait_duration_and_mode():
    wait = raw_node("w", "logic", "wait", config={"mode": "duration", "duration_seconds": 0})
    result = run([IN, wait, OUT], [raw_edge("e1", "input", "w"), raw_edge("e2", "w", "output")])
    assert "INVALID_WAIT_CONFIG" in codes_of(result)

    unsupported = raw_node("w2", "logic", "wait", config={"mode": "callback"})
    result = run([IN, unsupported, OUT], [raw_edge("e1", "input", "w2"), raw_edge("e2", "w2", "output")])
    assert "UNSUPPORTED_WAIT_MODE" in codes_of(result)


def test_approval_requires_title():
    approval = raw_node("h", "human", "approval", config={"title": ""})
    result = run([IN, approval, OUT], [raw_edge("e1", "input", "h"), raw_edge("e2", "h", "output")])
    assert "MISSING_REQUIRED_CONFIG" in codes_of(result)


def test_data_input_requires_object_schema():
    bad_input = input_node("in", schema={"type": "string"})
    result = run([bad_input, A, OUT], [raw_edge("e1", "in", "a"), raw_edge("e2", "a", "output")], agents={"agent-1": agent()})
    assert "INVALID_DATA_INPUT" in codes_of(result)
