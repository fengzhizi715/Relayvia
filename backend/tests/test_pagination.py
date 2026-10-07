"""Pagination contract tests for list endpoints.

List endpoints keep returning JSON arrays; `limit` / `offset` select the page
and `X-Total-Count` reports the unpaginated total so the UI can render page
controls without a breaking response-shape change.
"""

import uuid

from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workspaces.models import Workspace, WorkspaceStatus, WorkspaceType
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus


def agent_graph(agent_id: str) -> dict:
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
        "variables": {},
        "metadata": {},
    }


def make_version(client, http_test_server, name: str):
    agent = client.post("/api/agents", json={"name": f"{name} Agent", "endpoint": f"{http_test_server}/agent"}).json()
    workflow = client.post("/api/workflows", json={"name": name}).json()
    assert client.put(f"/api/workflows/{workflow['id']}/graph", json={"graph": agent_graph(agent["id"])}).status_code == 200
    version = client.post(f"/api/workflows/{workflow['id']}/versions", json={}).json()
    return workflow, version


def seed_workspaces(db, count: int = 3) -> WorkflowRun:
    workflow = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
    db.add(workflow)
    db.flush()
    version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json={})
    db.add(version)
    db.flush()
    run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        version_number=1,
        status=WorkflowRunStatus.RUNNING.value,
        graph_schema_version="1.0",
        graph_snapshot_json={},
        execution_snapshot_json={},
        input_json={},
        variables_json={},
    )
    db.add(run)
    db.flush()
    for index in range(count):
        node = NodeRun(
            workflow_run_id=run.id,
            node_id=f"node-{index}",
            node_type="tool",
            node_subtype="shell",
            node_name_snapshot=f"Node {index}",
            status=NodeRunStatus.PENDING.value,
            output_json=None,
            attempt=0,
        )
        db.add(node)
        db.flush()
        db.add(
            Workspace(
                name=f"workspace-{index}",
                runner_id=None,
                repository="/repos/project",
                branch="relayvia/test",
                base_branch=None,
                workspace_type=WorkspaceType.WORKTREE.value,
                status=WorkspaceStatus.READY.value,
                workflow_run_id=run.id,
                node_run_id=node.id,
                metadata_json={},
            )
        )
    db.commit()
    db.refresh(run)
    return run


def test_workflows_pagination(client):
    for index in range(3):
        assert client.post("/api/workflows", json={"name": f"Page Workflow {index}"}).status_code == 201

    first = client.get("/api/workflows", params={"limit": 2, "offset": 0})
    assert first.status_code == 200
    assert first.headers["x-total-count"] == "3"
    assert len(first.json()) == 2

    second = client.get("/api/workflows", params={"limit": 2, "offset": 2})
    assert second.headers["x-total-count"] == "3"
    assert len(second.json()) == 1

    names = {item["name"] for item in first.json()} | {item["name"] for item in second.json()}
    assert names == {f"Page Workflow {index}" for index in range(3)}

    unbounded = client.get("/api/workflows")
    assert unbounded.headers["x-total-count"] == "3"
    assert len(unbounded.json()) == 3


def test_workflow_runs_pagination(client, http_test_server):
    workflow, _ = make_version(client, http_test_server, "Paged Runs")
    for _ in range(3):
        assert client.post(f"/api/workflows/{workflow['id']}/runs", json={"input": {"requirement": "x"}}).status_code == 201

    page = client.get("/api/workflow-runs", params={"limit": 2, "offset": 0})
    assert page.status_code == 200
    assert page.headers["x-total-count"] == "3"
    assert len(page.json()) == 2

    filtered = client.get("/api/workflow-runs", params={"workflow_id": workflow["id"], "limit": 50})
    assert filtered.headers["x-total-count"] == "3"
    assert len(filtered.json()) == 3


def test_runners_pagination(client):
    for index in range(3):
        response = client.post(
            "/api/runners/register",
            json={"name": f"runner-{index}", "hostname": "host", "platform": "test", "capabilities": [], "metadata": {}},
        )
        assert response.status_code == 201

    page = client.get("/api/runners", params={"limit": 2, "offset": 0})
    assert page.status_code == 200
    assert page.headers["x-total-count"] == "3"
    assert len(page.json()) == 2

    unbounded = client.get("/api/runners")
    assert unbounded.headers["x-total-count"] == "3"
    assert len(unbounded.json()) == 3


def test_workspaces_pagination(client, db_session):
    run = seed_workspaces(db_session, count=3)

    page = client.get("/api/workspaces", params={"limit": 2, "offset": 0})
    assert page.status_code == 200
    assert page.headers["x-total-count"] == "3"
    assert len(page.json()) == 2

    filtered = client.get("/api/workspaces", params={"run_id": run.id, "limit": 2, "offset": 2})
    assert filtered.headers["x-total-count"] == "3"
    assert len(filtered.json()) == 1

    unbounded = client.get("/api/workspaces", params={"run_id": run.id})
    assert unbounded.headers["x-total-count"] == "3"
    assert len(unbounded.json()) == 3
