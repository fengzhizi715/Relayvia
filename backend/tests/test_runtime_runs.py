def agent_payload(server: str, name: str = "Planner Agent") -> dict:
    return {"name": name, "endpoint": f"{server}/agent", "health_check_url": f"{server}/health"}


def graph_payload(agent_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object", "properties": {"requirement": {"type": "string"}}, "required": ["requirement"]}}, "input_mapping": {}, "metadata": {}},
            {"id": "planner", "type": "agent", "subtype": "agent", "name": "Planner", "position": {"x": 100, "y": 0}, "config": {"agent_id": agent_id}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 200, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "planner", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "planner", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {"threshold": {"type": "number", "default": 0.8, "description": "min"}},
        "metadata": {},
    }


def setup_version(client, http_test_server):
    agent = client.post("/api/agents", json=agent_payload(http_test_server)).json()
    workflow = client.post("/api/workflows", json={"name": "Run Me"}).json()
    graph = graph_payload(agent["id"])
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": graph}).status_code == 200
    version = client.post(f"/api/workflows/{workflow['id']}/versions", json={"change_note": "v1"}).json()
    return agent, workflow, version, graph


def create_run(client, workflow_id, run_input=None):
    return client.post(f"/api/workflows/{workflow_id}/runs", json={"input": run_input or {"requirement": "build a parser"}})


def test_create_run_initializes_node_runs_and_snapshots(client, http_test_server):
    agent, workflow, version, _ = setup_version(client, http_test_server)
    response = create_run(client, workflow["id"])
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "created"
    assert run["workflow_version_id"] == version["id"]
    assert run["version"] == 1
    assert run["input"] == {"requirement": "build a parser"}
    assert run["variables"] == {"threshold": 0.8}

    nodes = {node_run["node_id"]: node_run for node_run in run["node_runs"]}
    assert set(nodes) == {"input", "planner", "output"}
    assert nodes["input"]["status"] == "completed"
    assert nodes["input"]["output"] == {"requirement": "build a parser"}
    assert nodes["planner"]["status"] == "pending"
    assert nodes["output"]["status"] == "pending"

    assert run["execution_snapshot"]["agents"][agent["id"]]["endpoint"] == agent["endpoint"]
    assert "credential_id" in run["execution_snapshot"]["agents"][agent["id"]]


def test_run_snapshot_immutable_after_registry_and_draft_changes(client, http_test_server):
    agent, workflow, version, graph = setup_version(client, http_test_server)
    run = create_run(client, workflow["id"]).json()
    snapshot = run["execution_snapshot"]["agents"][agent["id"]]

    assert client.put(f"/api/agents/{agent['id']}", json={"endpoint": "http://moved.example.com/agent"}).status_code == 200

    changed_graph = graph_payload(agent["id"])
    changed_graph["nodes"][1]["name"] = "Reviewer"
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": changed_graph}).status_code == 200

    reloaded = client.get(f"/api/workflow-runs/{run['id']}").json()
    assert reloaded["execution_snapshot"]["agents"][agent["id"]]["endpoint"] == snapshot["endpoint"]
    assert reloaded["graph_snapshot"]["nodes"][1]["name"] == "Planner"


def test_run_requires_version(client, http_test_server):
    workflow = client.post("/api/workflows", json={"name": "No Version"}).json()
    response = create_run(client, workflow["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "WORKFLOW_HAS_NO_VERSION"


def test_invalid_run_input_rejected(client, http_test_server):
    _, workflow, _, _ = setup_version(client, http_test_server)
    response = client.post(f"/api/workflows/{workflow['id']}/runs", json={"input": {"unrelated": 1}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_WORKFLOW_INPUT"


def test_run_readiness_blocks_disabled_agent(client, http_test_server):
    agent, workflow, _, _ = setup_version(client, http_test_server)
    assert create_run(client, workflow["id"]).status_code == 201

    assert client.put(f"/api/agents/{agent['id']}", json={"enabled": False}).status_code == 200
    response = create_run(client, workflow["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUN_READINESS_FAILED"


def test_run_version_reference(client, http_test_server):
    _, workflow, version, _ = setup_version(client, http_test_server)
    response = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        json={"workflow_version_id": version["id"], "input": {"requirement": "x"}},
    )
    assert response.status_code == 201
    assert response.json()["version"] == 1


def test_start_pause_resume_cancel_lifecycle(client, http_test_server):
    _, workflow, _, _ = setup_version(client, http_test_server)
    run_id = create_run(client, workflow["id"]).json()["id"]

    started = client.post(f"/api/workflow-runs/{run_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "running"
    assert started.json()["started_at"] is not None

    paused = client.post(f"/api/workflow-runs/{run_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert paused.json()["paused_at"] is not None

    resumed = client.post(f"/api/workflow-runs/{run_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"

    cancelled = client.post(f"/api/workflow-runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    node_statuses = {node_run["node_id"]: node_run["status"] for node_run in cancelled.json()["node_runs"]}
    assert node_statuses["input"] == "completed"
    assert node_statuses["planner"] == "cancelled"
    assert node_statuses["output"] == "cancelled"


def test_invalid_transitions_return_409(client, http_test_server):
    _, workflow, _, _ = setup_version(client, http_test_server)
    run_id = create_run(client, workflow["id"]).json()["id"]

    assert client.post(f"/api/workflow-runs/{run_id}/start").status_code == 200
    assert client.post(f"/api/workflow-runs/{run_id}/start").status_code == 409
    assert client.post(f"/api/workflow-runs/{run_id}/cancel").status_code == 200

    terminal = client.post(f"/api/workflow-runs/{run_id}/start")
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "INVALID_WORKFLOW_RUN_TRANSITION"

    already = client.post(f"/api/workflow-runs/{run_id}/cancel")
    assert already.status_code == 409
    assert already.json()["error"]["code"] == "RUN_ALREADY_TERMINAL"


def test_list_and_node_run_apis(client, http_test_server):
    _, workflow, _, _ = setup_version(client, http_test_server)
    run_id = create_run(client, workflow["id"]).json()["id"]

    listed = client.get("/api/workflow-runs").json()
    assert any(item["id"] == run_id and item["workflow_name"] == "Run Me" for item in listed)

    filtered = client.get(f"/api/workflow-runs?workflow_id={workflow['id']}&status=created").json()
    assert [item["id"] for item in filtered] == [run_id]

    nodes = client.get(f"/api/workflow-runs/{run_id}/nodes").json()
    assert len(nodes) == 3
    detail = client.get(f"/api/workflow-runs/{run_id}/nodes/{nodes[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["node_id"] in {"input", "planner", "output"}

    missing = client.get("/api/workflow-runs/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "WORKFLOW_RUN_NOT_FOUND"
