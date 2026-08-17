"""Phase 16: Coding Agent Adapter tests.

A fake-but-real `codex` CLI (an executable shell script) drives the end-to-end
path: Runner claims a coding-agent task, the adapter's command runs inside a
Git worktree, the file change is confirmed via `git diff`, a patch Artifact is
registered, and the Workflow completes.
"""

import asyncio
import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.connectors.agents.coding import CodexConnector, detect_coding_agent_capabilities
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workspaces.models import Workspace
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.default import DefaultNodeExecutor
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.runners.runner import execute_task
from app.workers.workflow_worker import _process_task


def git(repo: Path, *args: str) -> None:
    import subprocess

    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@relayvia")
    git(path, "config", "user.name", "Test")
    (path / "base.txt").write_text("base\n")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "init")


FAKE_CODEX = """#!/bin/sh
# A real, executable stand-in for `codex exec --json <task>`.
echo "codeworker starting" >&2
printf 'changed by codex\\n' >> generated.txt
echo '{"summary": "implemented", "status": "done"}'
"""


def write_fake_codex(root: Path) -> str:
    path = root / "fake-codex"
    path.write_text(FAKE_CODEX)
    path.chmod(0o755)
    return str(path)


def coding_graph(repo: str, task_template: str, executable: str) -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "coder", "type": "agent", "subtype": "agent", "name": "Codex", "position": {"x": 100, "y": 0}, "config": {"agent_id": "codex-1", "task_template": task_template, "timeout_seconds": 60, "workspace": {"repository": repo, "strategy": "worktree"}}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 200, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "coder", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "coder", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def snapshot_with(executable: str) -> dict:
    return {
        "schema_version": "2",
        "agents": {
            "codex-1": {"connector_type": "codex", "endpoint": None, "http_method": "POST", "headers": {}, "timeout_seconds": 60, "credential_id": None, "input_schema": {}, "output_schema": {}, "executable": executable},
        },
        "services": {},
        "service_actions": {},
    }


def make_run(db, graph: dict, snapshot: dict):
    workflow = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
    db.add(workflow)
    db.flush()
    version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json=graph)
    db.add(version)
    db.flush()
    run = WorkflowRun(
        workflow_id=workflow.id, workflow_version_id=version.id, version_number=1,
        status=WorkflowRunStatus.RUNNING.value, graph_schema_version="1.0", graph_snapshot_json=graph,
        execution_snapshot_json=snapshot, input_json={}, variables_json={},
    )
    db.add(run)
    db.flush()
    for node in graph["nodes"]:
        is_input = node["type"] == "data" and node["subtype"] == "input"
        db.add(
            NodeRun(workflow_run_id=run.id, node_id=node["id"], node_type=node["type"], node_subtype=node["subtype"],
                    node_name_snapshot=node["name"], status=NodeRunStatus.COMPLETED.value if is_input else NodeRunStatus.PENDING.value,
                    output_json={} if is_input else None, attempt=0)
        )
    db.commit()
    db.refresh(run)
    return run


def drive_worker(factory, scheduler):
    backend = MySQLExecutionBackend(factory)
    executor = DefaultNodeExecutor(factory)

    async def _drive():
        while True:
            task = await backend.claim("worker")
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="worker", renew_interval=60.0)

    asyncio.run(_drive())


def test_codex_build_command():
    command = CodexConnector().build_command(task="implement the API", timeout_seconds=60)
    assert command.startswith("codex exec --json 'implement the API'")
    custom = CodexConnector().build_command(task="hello world", timeout_seconds=60, executable="/tmp/codex-bin")
    assert custom.startswith("/tmp/codex-bin exec --json 'hello world'")


def test_capability_detection_reports_only_installed_clis(tmp_path):
    # No codex in PATH on CI typically -> [] (no false positives).
    detected = detect_coding_agent_capabilities()
    assert isinstance(detected, list)
    if shutil.which("codex"):
        assert "codex" in detected
    else:
        assert "codex" not in detected


def test_coding_agent_end_to_end(client, memory_db, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    make_git_repo(repo)
    fake_codex = write_fake_codex(tmp_path)
    monkeypatch.setattr("app.runners.runner.get_settings", lambda: Settings(runner_root=str(tmp_path), backend_url="http://x", _env_file=None))

    _, factory = memory_db
    graph = coding_graph(str(repo), "Implement the feature in generated.txt", fake_codex)
    scheduler = WorkflowScheduler(default_max_attempts=1)
    with factory() as db:
        run = make_run(db, graph, snapshot_with(fake_codex))
        run_id = run.id
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    runner = client.post("/api/runners/register", json={"name": "coder", "hostname": "h", "platform": "t", "capabilities": ["codex"], "metadata": {}}).json()
    headers = {"X-Relayvia-Runner-Token": runner["enrollment_token"]}
    claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=headers).json()
    assert claimed is not None
    assert claimed["execution_type"] == "coding_agent"
    assert claimed["config"]["command"].startswith(fake_codex)
    assert claimed["workspace"] is not None

    result = asyncio.run(execute_task({"workspace": claimed["workspace"], "config": claimed["config"]}))
    assert result["ok"] is True
    patch = next((a for a in result["artifacts"] if a["type"] == "patch"), None)
    assert patch is not None

    submitted = client.post(
        f"/api/runners/{runner['id']}/submit-result",
        json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": result},
        headers=headers,
    )
    assert submitted.status_code == 200

    drive_worker(factory, scheduler)
    with factory() as db:
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value
        coder_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "coder"))
        assert coder_run.status == NodeRunStatus.COMPLETED.value
        assert coder_run.output_json["patch"].startswith("artifact://")
        workspace = db.scalar(select(Workspace).where(Workspace.node_run_id == coder_run.id))
        assert workspace.status == "released"
        # The file change is real: the worktree contains the modification.
        import base64
        artifact_id = coder_run.output_json["patch"][len("artifact://"):]
        from app.domain.artifacts.models import Artifact

        artifact = db.get(Artifact, artifact_id)
        assert artifact is not None
        patch_bytes = base64.b64decode(patch["content"])
        assert b"generated.txt" in patch_bytes
    # The base repository itself is untouched.
    assert (repo / "generated.txt").exists() is False
