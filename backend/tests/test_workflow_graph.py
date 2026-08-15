import pytest

from app.core.errors import RelayviaError
from app.domain.workflows.context_reference import extract_node_references, parse_context_reference
from app.domain.workflows.graph import parse_workflow_graph


def agent_payload(server: str, name: str = "Planner Agent") -> dict:
    return {
        "name": name,
        "endpoint": f"{server}/agent",
        "health_check_url": f"{server}/health",
    }


def graph_payload(agent_id: str, service_id: str | None = None, action_id: str | None = None) -> dict:
    nodes = [
        {
            "id": "input",
            "type": "data",
            "subtype": "input",
            "name": "Requirement",
            "position": {"x": 0, "y": 100},
            "config": {"schema": {"type": "object", "properties": {"requirement": {"type": "string"}}}},
            "input_mapping": {},
            "metadata": {"surface": "contract-test"},
        },
        {
            "id": "planner",
            "type": "agent",
            "subtype": "agent",
            "name": "Planner",
            "position": {"x": 300, "y": 100},
            "config": {"agent_id": agent_id, "role": "planner", "timeout_seconds": 600},
            "input_mapping": {"task": "{{workflow.input.requirement}}"},
            "metadata": {},
        },
    ]
    if service_id and action_id:
        nodes.append(
            {
                "id": "service-call",
                "type": "service",
                "subtype": "http",
                "name": "Service Call",
                "position": {"x": 600, "y": 100},
                "config": {"service_id": service_id, "service_action_id": action_id},
                "input_mapping": {"task": "{{nodes.planner.output.result}}"},
                "metadata": {},
            }
        )
    edges = [
        {
            "id": "edge-input-planner",
            "source": "input",
            "target": "planner",
            "source_handle": None,
            "target_handle": None,
            "label": None,
            "condition": None,
            "metadata": {},
        }
    ]
    if service_id and action_id:
        edges.append(
            {
                "id": "edge-planner-service",
                "source": "planner",
                "target": "service-call",
                "source_handle": None,
                "target_handle": None,
                "label": None,
                "condition": None,
                "metadata": {},
            }
        )
    return {"schema_version": "1.0", "nodes": nodes, "edges": edges, "variables": {}, "metadata": {}}


def create_registry_refs(client, http_test_server):
    agent = client.post("/api/agents", json=agent_payload(http_test_server)).json()
    service = client.post(
        "/api/services",
        json={"name": "Training Service", "base_url": http_test_server, "health_check_url": f"{http_test_server}/health"},
    ).json()
    action = client.post(
        f"/api/services/{service['id']}/actions",
        json={"name": "Start Training", "method": "POST", "path": "/training/jobs"},
    ).json()
    return agent, service, action


def test_context_reference_parse_and_dependency_extraction():
    reference = parse_context_reference("{{nodes.agent_a.output.customer_id}}")
    assert reference.scope == "nodes.agent_a.output"
    assert reference.node_id == "agent_a"
    assert reference.path == "customer_id"
    assert extract_node_references({"a": "{{nodes.agent_a.output.customer_id}}", "b": ["{{nodes.agent_b.output.value}}"]}) == ["agent_a", "agent_b"]

    with pytest.raises(RelayviaError) as error:
        parse_context_reference("{{nodes.agent_a.input.customer_id}}")
    assert error.value.code == "INVALID_CONTEXT_REFERENCE"


def test_all_phase3_node_contracts_validate():
    nodes = []
    definitions = [
        ("agent", "agent", {"agent_id": "agent-1"}),
        ("service", "service", "http", {"service_id": "service-1", "service_action_id": "action-1"}),
        ("shell", "tool", "shell", {"command": "pytest"}),
        ("git", "tool", "git", {"command": "git status"}),
        ("test-command", "tool", "test_command", {"command": "pytest"}),
        ("condition", "logic", "condition", {"expression": {"left": "{{workflow.input.ok}}", "operator": "==", "right": True}}),
        ("parallel", "logic", "parallel", {}),
        ("merge", "logic", "merge", {"strategy": "all"}),
        ("router", "logic", "router", {}),
        ("wait", "logic", "wait", {"mode": "duration", "duration_seconds": 60}),
        ("approval", "human", "approval", {"title": "Approve?"}),
        ("human-input", "human", "input", {"form_schema": {"type": "object"}}),
        ("data-input", "data", "input", {"schema": {"type": "object"}}),
        ("transform", "data", "transform", {"mappings": {"value": "{{nodes.agent.output.result}}"}}),
        ("output", "data", "output", {"output_mapping": {"value": "{{nodes.agent.output.result}}"}}),
    ]
    for item in definitions:
        if len(item) == 3:
            node_id, node_type, config = item
            subtype = node_type
        else:
            node_id, node_type, subtype, config = item
        nodes.append({"id": node_id, "type": node_type, "subtype": subtype, "name": node_id, "position": {"x": 0, "y": 0}, "config": config, "input_mapping": {}, "metadata": {}})
    graph = parse_workflow_graph({"schema_version": "1.0", "nodes": nodes, "edges": [], "variables": {}, "metadata": {}})
    assert len(graph.nodes) == 15


def test_workflow_draft_version_round_trip_and_immutability(client, http_test_server):
    agent, service, action = create_registry_refs(client, http_test_server)
    created = client.post("/api/workflows", json={"name": "Coding Showcase", "description": "Graph contract"})
    assert created.status_code == 201
    workflow = created.json()
    assert workflow["status"] == "draft"
    assert workflow["draft_graph"]["schema_version"] == "1.0"

    graph_a = graph_payload(agent["id"], service["id"], action["id"])
    saved = client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph_a})
    assert saved.status_code == 200
    assert saved.json()["graph"] == graph_a

    version_one = client.post(f"/api/workflows/{workflow['id']}/versions", json={"change_note": "initial graph"})
    assert version_one.status_code == 201
    assert version_one.json()["version"] == 1
    assert version_one.json()["graph"] == graph_a

    graph_b = graph_payload(agent["id"])
    graph_b["nodes"][1]["name"] = "Reviewer"
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph_b}).status_code == 200
    historical = client.get(f"/api/workflows/{workflow['id']}/versions/1")
    assert historical.status_code == 200
    assert historical.json()["graph"]["nodes"][1]["name"] == "Planner"

    version_two = client.post(f"/api/workflows/{workflow['id']}/versions", json={"change_note": "reviewer graph"})
    assert version_two.status_code == 201
    assert version_two.json()["version"] == 2
    assert client.get(f"/api/workflows/{workflow['id']}/versions").json()[0]["version"] == 2
    assert client.put(f"/api/workflows/{workflow['id']}/versions/1", json={"change_note": "no-op"}).status_code == 405
    assert client.delete(f"/api/workflows/{workflow['id']}").status_code == 204
    assert client.get(f"/api/workflows/{workflow['id']}").json()["status"] == "archived"
    assert workflow["id"] not in {item["id"] for item in client.get("/api/workflows").json()}


def test_graph_contract_rejects_invalid_structure_and_references(client, http_test_server):
    agent, _, _ = create_registry_refs(client, http_test_server)
    workflow = client.post("/api/workflows", json={"name": "Invalid Graph Cases"}).json()
    graph = graph_payload(agent["id"])
    graph["nodes"].append(graph["nodes"][1].copy())
    invalid = client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph})
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "DUPLICATE_NODE_ID"

    graph = graph_payload(agent["id"])
    graph["edges"][0]["target"] = "missing"
    invalid_edge = client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph})
    assert invalid_edge.status_code == 400
    assert invalid_edge.json()["error"]["code"] == "INVALID_NODE_REFERENCE"

    graph = graph_payload("missing-agent")
    invalid_agent = client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph})
    assert invalid_agent.status_code == 400
    assert invalid_agent.json()["error"]["code"] == "INVALID_AGENT_REFERENCE"

    unsupported = dict(graph_payload(agent["id"]))
    unsupported["schema_version"] = "2.0"
    response = client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": unsupported})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_GRAPH_SCHEMA_VERSION"


def test_service_action_reference_must_match_parent_service(client, http_test_server):
    agent, service, action = create_registry_refs(client, http_test_server)
    other = client.post(
        "/api/services",
        json={"name": "Other Service", "base_url": http_test_server},
    ).json()
    workflow = client.post("/api/workflows", json={"name": "Reference Protection"}).json()
    valid_graph = graph_payload(agent["id"], service["id"], action["id"])
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": valid_graph}).status_code == 200

    blocked = client.delete(f"/api/agents/{agent['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "RESOURCE_IN_USE"

    mismatch_workflow = client.post("/api/workflows", json={"name": "Mismatched Action Reference"}).json()
    graph = graph_payload(agent["id"], other["id"], action["id"])
    response = client.put(f"/api/workflows/{mismatch_workflow['id']}/graph", json={"graph": graph})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SERVICE_ACTION_REFERENCE"
