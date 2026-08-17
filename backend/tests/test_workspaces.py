"""Phase 15: Workspace Manager (local repository + Git worktree isolation) tests."""

import asyncio
import subprocess
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workspaces.models import Workspace
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.default import DefaultNodeExecutor
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.runners.runner import WorkspaceError, execute_task, prepare_workspace
from app.workers.workflow_worker import _process_task


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@relayvia")
    git(path, "config", "user.name", "Test")
    (path / "base.txt").write_text("base\n")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "init")


def parallel_workspace_graph(repo: str, a_command: str, b_command: str) -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "parallel", "type": "logic", "subtype": "parallel", "name": "Parallel", "position": {"x": 100, "y": 0}, "config": {}, "input_mapping": {}, "metadata": {}},
            {"id": "a", "type": "tool", "subtype": "shell", "name": "Frontend", "position": {"x": 200, "y": -80}, "config": {"command": a_command, "workspace": {"repository": repo, "strategy": "worktree"}}, "input_mapping": {}, "metadata": {}},
            {"id": "b", "type": "tool", "subtype": "shell", "name": "Backend", "position": {"x": 200, "y": 80}, "config": {"command": b_command, "workspace": {"repository": repo, "strategy": "worktree"}}, "input_mapping": {}, "metadata": {}},
            {"id": "merge", "type": "logic", "subtype": "merge", "name": "Merge", "position": {"x": 300, "y": 0}, "config": {"strategy": "all"}, "input_mapping": {}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 400, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "parallel", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "parallel", "target": "a", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "parallel", "target": "b", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e4", "source": "a", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e5", "source": "b", "target": "merge", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e6", "source": "merge", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def make_run(db, graph: dict):
    workflow = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
    db.add(workflow)
    db.flush()
    version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json=graph)
    db.add(version)
    db.flush()
    run = WorkflowRun(
        workflow_id=workflow.id, workflow_version_id=version.id, version_number=1,
        status=WorkflowRunStatus.RUNNING.value, graph_schema_version="1.0", graph_snapshot_json=graph,
        execution_snapshot_json={"schema_version": "2"}, input_json={}, variables_json={},
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


# --- Unit: workspace preparation ---


def test_prepare_worktree_and_branch(tmp_path):
    repo = tmp_path / "repo"
    make_git_repo(repo)
    ws = {"repository": str(repo), "strategy": "worktree", "branch": "relayvia/run-1/a", "base_branch": None}
    path, branch, is_worktree = asyncio.run(prepare_workspace(ws, tmp_path))
    assert is_worktree is True
    assert branch == "relayvia/run-1/a"
    assert Path(path).is_relative_to(tmp_path)
    assert Path(path).exists()
    # branch exists and checkout works
    git(repo, "rev-parse", "refs/heads/relayvia/run-1/a")


def test_prepare_local_repository(tmp_path):
    repo = tmp_path / "repo"
    make_git_repo(repo)
    path, branch, is_worktree = asyncio.run(prepare_workspace({"repository": str(repo), "strategy": "local", "branch": None}, tmp_path))
    assert is_worktree is False
    assert Path(path) == repo.resolve()


def test_prepare_rejects_invalid_repository_and_escape(tmp_path):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    try:
        asyncio.run(prepare_workspace({"repository": str(not_a_repo), "strategy": "worktree", "branch": "x"}, tmp_path))
        assert False, "expected WorkspaceError"
    except WorkspaceError:
        pass

    outside = tmp_path.parent / f"outside-{uuid.uuid4().hex[:6]}"
    outside.mkdir(exist_ok=True)
    try:
        asyncio.run(prepare_workspace({"repository": str(outside), "strategy": "worktree", "branch": "x"}, tmp_path))
        assert False, "expected WorkspaceError"
    except WorkspaceError:
        pass


def test_execute_task_in_worktree_emits_patch_artifact(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    make_git_repo(repo)
    monkeypatch.setattr("app.runners.runner.get_settings", lambda: Settings(runner_root=str(tmp_path), backend_url="http://x", _env_file=None))
    task = {
        "workspace": {"repository": str(repo), "strategy": "worktree", "branch": "relayvia/r1/frontend"},
        "config": {"command": "echo frontend >> frontend.txt", "timeout_seconds": 30},
    }
    result = asyncio.run(execute_task(task))
    assert result["ok"] is True
    assert result["metadata"]["workspace_path"]
    assert result["metadata"]["workspace_branch"] == "relayvia/r1/frontend"
    patch = next((a for a in result["artifacts"] if a["type"] == "patch"), None)
    assert patch is not None
    import base64
    assert b"frontend.txt" in base64.b64decode(patch["content"])


# --- End-to-end: parallel workspaces isolate modifications ---


def test_parallel_workspaces_isolate_modifications(client, memory_db, tmp_path, monkeypatch):
    from app.core.config import Settings as S

    repo = tmp_path / "repo"
    make_git_repo(repo)
    monkeypatch.setattr("app.runners.runner.get_settings", lambda: S(runner_root=str(tmp_path), backend_url="http://x", _env_file=None))

    _, factory = memory_db
    graph = parallel_workspace_graph(str(repo), "echo frontend >> frontend.txt", "echo backend >> backend.txt")
    scheduler = WorkflowScheduler(default_max_attempts=1)
    with factory() as db:
        run = make_run(db, graph)
        run_id = run.id
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive_worker(factory, scheduler)  # runs the Parallel node -> schedules branch workspaces

    runner = client.post("/api/runners/register", json={"name": "ws", "hostname": "h", "platform": "t", "capabilities": ["shell"], "metadata": {}}).json()
    headers = {"X-Relayvia-Runner-Token": runner["enrollment_token"]}
    while True:
        claimed = client.post(f"/api/runners/{runner['id']}/claim", headers=headers).json()
        if claimed is None:
            break
        assert claimed["workspace"] is not None
        result = asyncio.run(execute_task({"workspace": claimed["workspace"], "config": claimed["config"]}))
        submitted = client.post(
            f"/api/runners/{runner['id']}/submit-result",
            json={"task_id": claimed["task_id"], "lease_token": claimed["lease_token"], "result": result},
            headers=headers,
        )
        assert submitted.status_code == 200

    drive_worker(factory, scheduler)  # Merge + Output
    with factory() as db:
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value
        workspaces = db.scalars(select(Workspace).where(Workspace.workflow_run_id == run_id)).all()
        assert len(workspaces) == 2
        paths = {ws.path for ws in workspaces}
        branches = {ws.branch for ws in workspaces}
        assert len(paths) == 2  # isolated worktrees
        assert len(branches) == 2  # unique branches
        assert all(ws.status == "released" for ws in workspaces)
        for ws in workspaces:
            assert ws.path is not None
            assert Path(ws.path).is_relative_to(tmp_path)
            assert ws.path != str(repo)
    # The base repository must be untouched by the parallel modifications.
    assert (repo / "frontend.txt").exists() is False
    assert (repo / "backend.txt").exists() is False
