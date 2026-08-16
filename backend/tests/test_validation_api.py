def agent_payload(server: str, name: str = "Planner Agent") -> dict:
    return {"name": name, "endpoint": f"{server}/agent", "health_check_url": f"{server}/health"}


def graph_payload(agent_id: str, service_id: str | None = None, action_id: str | None = None, *, include_output: bool = True) -> dict:
    nodes = [
        {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object", "properties": {}}}, "input_mapping": {}, "metadata": {}},
        {"id": "planner", "type": "agent", "subtype": "agent", "name": "Planner", "position": {"x": 100, "y": 0}, "config": {"agent_id": agent_id}, "input_mapping": {}, "metadata": {}},
    ]
    if service_id and action_id:
        nodes.append({"id": "service-call", "type": "service", "subtype": "http", "name": "Service Call", "position": {"x": 200, "y": 0}, "config": {"service_id": service_id, "service_action_id": action_id}, "input_mapping": {}, "metadata": {}})
    if include_output:
        nodes.append({"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 300, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}})

    edges = [{"id": "e1", "source": "input", "target": "planner", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}}]
    if service_id and action_id:
        edges.append({"id": "e2", "source": "planner", "target": "service-call", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}})
        if include_output:
            edges.append({"id": "e3", "source": "service-call", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}})
    elif include_output:
        edges.append({"id": "e2b", "source": "planner", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}})
    return {"schema_version": "1.0", "nodes": nodes, "edges": edges, "variables": {}, "metadata": {}}


def create_registry_refs(client, http_test_server):
    agent = client.post("/api/agents", json=agent_payload(http_test_server)).json()
    service = client.post("/api/services", json={"name": "Training Service", "base_url": http_test_server}).json()
    action = client.post(f"/api/services/{service['id']}/actions", json={"name": "Start Training", "method": "POST", "path": "/training/jobs"}).json()
    return agent, service, action


def test_validate_current_draft(client, http_test_server):
    agent, service, action = create_registry_refs(client, http_test_server)
    workflow = client.post("/api/workflows", json={"name": "Validate Draft"}).json()
    graph = graph_payload(agent["id"], service["id"], action["id"])
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph}).status_code == 200

    result = client.post(f"/api/workflows/{workflow['id']}/validate").json()
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["warnings"] == []


def test_validate_supplied_unsaved_graph(client, http_test_server):
    agent, service, action = create_registry_refs(client, http_test_server)
    workflow = client.post("/api/workflows", json={"name": "Validate Supplied"}).json()
    graph = graph_payload(agent["id"], service["id"], action["id"])
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph}).status_code == 200

    bad = graph_payload(agent["id"], service["id"], action["id"], include_output=False)
    result = client.post(f"/api/workflows/{workflow['id']}/validate", json={"graph": bad})
    assert result.status_code == 200
    body = result.json()
    assert body["valid"] is False
    assert any(issue["code"] == "MISSING_OUTPUT_NODE" for issue in body["errors"])

    # The supplied graph is NOT persisted: the draft is still valid.
    result = client.post(f"/api/workflows/{workflow['id']}/validate").json()
    assert result["valid"] is True


def test_validate_reports_structured_issues(client, http_test_server):
    agent, service, action = create_registry_refs(client, http_test_server)
    workflow = client.post("/api/workflows", json={"name": "Structured Issues"}).json()

    graph = graph_payload(agent["id"], service["id"], action["id"], include_output=False)
    graph["nodes"][1]["config"]["agent_id"] = "ghost-agent"
    result = client.post(f"/api/workflows/{workflow['id']}/validate", json={"graph": graph}).json()

    assert result["valid"] is False
    missing_output = next(issue for issue in result["errors"] if issue["code"] == "MISSING_OUTPUT_NODE")
    assert missing_output["severity"] == "error"
    assert missing_output["node_id"] is None

    missing_agent = next(issue for issue in result["errors"] if issue["code"] == "AGENT_NOT_FOUND")
    assert missing_agent["node_id"] == "planner"
    assert missing_agent["field"] == "config.agent_id"


def test_validate_rejects_non_contract_graph(client, http_test_server):
    workflow = client.post("/api/workflows", json={"name": "Contract Reject"}).json()
    response = client.post(f"/api/workflows/{workflow['id']}/validate", json={"graph": {"schema_version": "2.0", "nodes": [], "edges": []}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_GRAPH_SCHEMA_VERSION"


def test_create_version_blocked_on_invalid_draft(client, http_test_server):
    agent, service, action = create_registry_refs(client, http_test_server)
    workflow = client.post("/api/workflows", json={"name": "Invalid Version"}).json()
    graph = graph_payload(agent["id"], service["id"], action["id"], include_output=False)
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph}).status_code == 200

    response = client.post(f"/api/workflows/{workflow['id']}/versions", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert any(issue["code"] == "MISSING_OUTPUT_NODE" for issue in response.json()["error"]["details"]["errors"])
    assert client.get(f"/api/workflows/{workflow['id']}/versions").json() == []


def test_create_version_allowed_with_warnings(client, http_test_server):
    unhealthy = client.post("/api/agents", json={"name": "Unhealthy Agent", "endpoint": f"{http_test_server}/agent", "health_check_url": f"{http_test_server}/fail"}).json()
    assert client.post(f"/api/agents/{unhealthy['id']}/test").status_code == 200
    service = client.post("/api/services", json={"name": "Warning Service", "base_url": http_test_server}).json()
    action = client.post(f"/api/services/{service['id']}/actions", json={"name": "Do It", "method": "POST", "path": "/do"}).json()
    workflow = client.post("/api/workflows", json={"name": "Warning Version"}).json()
    graph = graph_payload(unhealthy["id"], service["id"], action["id"])
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph}).status_code == 200

    validation = client.post(f"/api/workflows/{workflow['id']}/validate").json()
    assert validation["valid"] is True
    assert any(issue["code"] == "AGENT_UNHEALTHY" for issue in validation["warnings"])

    response = client.post(f"/api/workflows/{workflow['id']}/versions", json={"change_note": "warning ok"})
    assert response.status_code == 201
    assert response.json()["version"] == 1
