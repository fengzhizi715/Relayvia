"""Phase 12: Artifact Entity + LocalArtifactStorage + reference + end-to-end."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.errors import RelayviaError
from app.domain.artifacts.models import Artifact
from app.domain.artifacts.reference import artifact_uri, is_artifact_uri, parse_artifact_uri
from app.domain.artifacts.service import get_artifact, register_artifact_bytes, register_artifact_candidates, register_external_artifact
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.artifact_storage import LocalArtifactStorage
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.runtime.executor.base import NodeExecutionContext, NodeExecutionResult, NodeExecutor
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.workers.workflow_worker import _process_task


@pytest.fixture()
def storage(tmp_path):
    return LocalArtifactStorage(tmp_path / "artifacts")


def make_run(db, graph: dict, snapshot: dict):
    workflow = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}", status="active", draft_graph_json={}, graph_schema_version="1.0", current_version=1)
    db.add(workflow)
    db.flush()
    version = WorkflowVersion(workflow_id=workflow.id, version=1, graph_schema_version="1.0", graph_json=graph)
    db.add(version)
    db.flush()
    run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        version_number=1,
        status=WorkflowRunStatus.RUNNING.value,
        graph_schema_version="1.0",
        graph_snapshot_json=graph,
        execution_snapshot_json=snapshot,
        input_json={},
        variables_json={},
    )
    db.add(run)
    db.flush()
    for node in graph["nodes"]:
        is_input = node["type"] == "data" and node["subtype"] == "input"
        db.add(
            NodeRun(
                workflow_run_id=run.id,
                node_id=node["id"],
                node_type=node["type"],
                node_subtype=node["subtype"],
                node_name_snapshot=node["name"],
                status=NodeRunStatus.COMPLETED.value if is_input else NodeRunStatus.PENDING.value,
                output_json={} if is_input else None,
                attempt=0,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def chain_graph() -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "tool_a", "type": "agent", "subtype": "agent", "name": "Tool A", "position": {"x": 100, "y": 0}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}},
            {"id": "tool_b", "type": "agent", "subtype": "agent", "name": "Tool B", "position": {"x": 200, "y": 0}, "config": {"agent_id": "agent-1"}, "input_mapping": {"report": "{{nodes.tool_a.output.report}}"}, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 300, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "tool_a", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "tool_a", "target": "tool_b", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "tool_b", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


# --- Reference / Storage units ---


def test_artifact_reference_parse():
    assert artifact_uri("abc-123") == "artifact://abc-123"
    assert is_artifact_uri("artifact://abc")
    assert parse_artifact_uri("artifact://abc-123") == "abc-123"
    with pytest.raises(RelayviaError):
        parse_artifact_uri("file:///etc/passwd")
    with pytest.raises(RelayviaError):
        parse_artifact_uri("artifact://")


def test_local_storage_save_open_exists(storage):
    assert storage.save_bytes("key-1", b"hello") == 5
    assert storage.exists("key-1")
    assert storage.open("key-1").read() == b"hello"
    assert storage.exists("missing") is False
    with pytest.raises(FileNotFoundError):
        storage.open("missing")


def test_local_storage_rejects_path_traversal(storage, tmp_path):
    with pytest.raises(RelayviaError):
        storage.save_bytes("../evil", b"x")
    with pytest.raises(RelayviaError):
        storage.open("../../etc/passwd")
    with pytest.raises(RelayviaError):
        storage.save_bytes("a/b", b"x")
    assert storage.exists("../evil") is False
    assert not (tmp_path / "artifacts").parent.joinpath("evil").exists()


def test_register_artifact_creates_entity_and_storage_file(memory_db, storage):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, chain_graph(), {"schema_version": "2"})
        node_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run.id, NodeRun.node_id == "tool_a"))
        artifact = register_artifact_bytes(
            db,
            workflow_run_id=run.id,
            producer_node_run_id=node_run.id,
            name="report.txt",
            artifact_type="report",
            content_type="text/plain",
            content=b"report-content",
            metadata={"task": "test"},
            storage=storage,
        )
        db.commit()
        run_id, node_run_id, artifact_id = run.id, node_run.id, artifact.id

    with factory() as db:
        row = get_artifact(db, artifact_id)
        assert row.workflow_run_id == run_id
        assert row.producer_node_run_id == node_run_id
        assert row.name == "report.txt"
        assert row.type == "report"
        assert row.size == 14
        assert row.uri == f"artifact://{artifact_id}"
    assert storage.exists(artifact_id)
    assert storage.open(artifact_id).read() == b"report-content"


def test_register_candidates_bytes_external_and_same_run_reference(memory_db, storage):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, chain_graph(), {"schema_version": "2"})
        node_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run.id, NodeRun.node_id == "tool_a"))
        existing = register_artifact_bytes(
            db,
            workflow_run_id=run.id,
            producer_node_run_id=node_run.id,
            name="existing.txt",
            artifact_type="report",
            content_type="text/plain",
            content=b"existing",
            metadata={},
            storage=storage,
        )
        existing_uri = existing.uri
        refs, output_map = register_artifact_candidates(
            db,
            workflow_run_id=run.id,
            producer_node_run_id=node_run.id,
            candidates=[
                {"name": "patch.diff", "type": "patch", "content_type": "text/plain", "content": b"patch-content", "output_key": "patch"},
                {"name": "model", "type": "model", "uri": "https://example.com/model.onnx", "output_key": "model"},
                {"name": "existing", "type": "report", "uri": existing_uri},
            ],
            storage=storage,
            max_bytes=1024,
        )
        db.commit()
        run_id, node_run_id = run.id, node_run.id

    assert output_map["patch"].startswith("artifact://")
    # External URI artifacts keep their external reference (directly usable).
    assert output_map["model"] == "https://example.com/model.onnx"
    assert any(ref["uri"] == existing_uri for ref in refs)
    assert len(refs) == 3
    with factory() as db:
        artifacts = db.scalars(select(Artifact)).all()
        assert len(artifacts) == 3  # existing + external + bytes registered
        patch_artifact = next(artifact for artifact in artifacts if artifact.type == "patch")
        assert patch_artifact.uri == output_map["patch"]
        assert storage.open(patch_artifact.id).read() == b"patch-content"


def test_register_candidates_rejects_local_path_and_oversized_content(memory_db, storage, tmp_path):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, chain_graph(), {"schema_version": "2"})
        node_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run.id, NodeRun.node_id == "tool_a"))
        with pytest.raises(RelayviaError, match="local_path"):
            register_artifact_candidates(
                db, workflow_run_id=run.id, producer_node_run_id=node_run.id,
                candidates=[{"local_path": str(tmp_path / "outside.txt")}], storage=storage, max_bytes=1024,
            )
        with pytest.raises(RelayviaError, match="size limit"):
            register_artifact_candidates(
                db, workflow_run_id=run.id, producer_node_run_id=node_run.id,
                candidates=[{"content": b"x" * 4}], storage=storage, max_bytes=3,
            )


def test_register_external_artifact_has_no_local_content(memory_db, storage):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, chain_graph(), {"schema_version": "2"})
        node_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run.id, NodeRun.node_id == "tool_a"))
        artifact = register_external_artifact(db, workflow_run_id=run.id, producer_node_run_id=node_run.id, name="model", artifact_type="model", uri="https://cdn/model.onnx", content_type=None, metadata={})
        db.commit()
        assert artifact.size is None
        assert storage.exists(artifact.id) is False


def test_external_artifact_uri_can_be_reused(memory_db):
    _, factory = memory_db
    with factory() as db:
        first_run = make_run(db, chain_graph(), {"schema_version": "2"})
        second_run = make_run(db, chain_graph(), {"schema_version": "2"})
        first_node = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == first_run.id, NodeRun.node_id == "tool_a"))
        second_node = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == second_run.id, NodeRun.node_id == "tool_a"))
        first = register_external_artifact(db, workflow_run_id=first_run.id, producer_node_run_id=first_node.id, name="model", artifact_type="model", uri="https://cdn.example/model.onnx", content_type=None, metadata={})
        second = register_external_artifact(db, workflow_run_id=second_run.id, producer_node_run_id=second_node.id, name="model", artifact_type="model", uri="https://cdn.example/model.onnx", content_type=None, metadata={})
        db.commit()
        assert first.id != second.id


# --- End-to-end: produce -> register -> reference -> consume ---


class ArtifactChainExecutor(NodeExecutor):
    def __init__(self, storage, tmp_path) -> None:
        self.storage = storage
        self.tmp_path = tmp_path
        self.consumed: str | None = None

    async def execute(self, ctx: NodeExecutionContext) -> NodeExecutionResult:
        if ctx.node_id == "tool_a":
            return NodeExecutionResult(
                ok=True,
                output={},
                artifacts=[
                    {"name": "report.txt", "type": "report", "content_type": "text/plain", "content": b"report-content", "output_key": "report"}
                ],
            )
        if ctx.node_id == "tool_b":
            reference = ctx.resolved_input.get("report")
            assert isinstance(reference, str) and reference.startswith("artifact://")
            artifact_id = parse_artifact_uri(reference)
            content = self.storage.open(artifact_id).read().decode()
            self.consumed = content
            return NodeExecutionResult(ok=True, output={"consumed": content})
        return NodeExecutionResult(ok=True, output={})


def test_artifact_end_to_end_produce_reference_consume(memory_db, storage, tmp_path):
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, chain_graph(), {"schema_version": "2"})
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    backend = MySQLExecutionBackend(factory)
    executor = ArtifactChainExecutor(storage, tmp_path)

    async def drive():
        while True:
            task = await backend.claim("artifact-worker")
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="artifact-worker", renew_interval=60.0, storage=storage)

    asyncio.run(drive())

    with factory() as db:
        assert db.get(WorkflowRun, run_id).status == WorkflowRunStatus.COMPLETED.value
        tool_a = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "tool_a"))
        artifact = db.scalar(select(Artifact).where(Artifact.producer_node_run_id == tool_a.id))
        assert tool_a.output_json["report"] == artifact.uri
        assert tool_a.artifact_refs_json == [{"uri": artifact.uri, "type": "report", "name": "report.txt"}]
    assert executor.consumed == "report-content"
    assert storage.open(artifact.id).read() == b"report-content"


def test_artifact_survives_worker_restart(memory_db, storage, tmp_path):
    """Artifact metadata + file remain available to a fresh worker (new
    storage instance over the same directory)."""
    _, factory = memory_db
    with factory() as db:
        run = make_run(db, chain_graph(), {"schema_version": "2"})
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    backend = MySQLExecutionBackend(factory)
    executor = ArtifactChainExecutor(storage, tmp_path)
    asyncio.run(
        (lambda: _drive_until_done(backend, scheduler, factory, executor, storage))()
    )
    with factory() as db:
        artifact = db.scalar(select(Artifact).where(Artifact.workflow_run_id == run_id))
    # A "restarted" worker (fresh storage instance over the same directory).
    restarted = LocalArtifactStorage(storage.root)
    assert restarted.exists(artifact.id)
    assert restarted.open(artifact.id).read() == b"report-content"


def test_artifact_api(client, db_session, storage, monkeypatch):
    monkeypatch.setattr("app.api.routes.artifacts.get_artifact_storage", lambda: storage)
    run = make_run(db_session, chain_graph(), {"schema_version": "2"})
    node_run = db_session.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run.id, NodeRun.node_id == "tool_a"))
    artifact = register_artifact_bytes(
        db_session, workflow_run_id=run.id, producer_node_run_id=node_run.id, name="report.txt",
        artifact_type="report", content_type="text/plain", content=b"api-content", metadata={}, storage=storage,
    )
    external = register_external_artifact(
        db_session, workflow_run_id=run.id, producer_node_run_id=node_run.id, name="model",
        artifact_type="model", uri="https://x/y", content_type=None, metadata={},
    )
    db_session.commit()
    artifact_id, external_id = artifact.id, external.id

    detail = client.get(f"/api/artifacts/{artifact_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "report.txt"
    assert body["uri"] == f"artifact://{artifact_id}"
    assert body["size"] == 11

    content = client.get(f"/api/artifacts/{artifact_id}/content")
    assert content.status_code == 200
    assert content.content == b"api-content"

    assert client.get("/api/artifacts/not-real").status_code == 404
    # External artifacts have no local content.
    assert client.get(f"/api/artifacts/{external_id}/content").status_code == 404


async def _drive_until_done(backend, scheduler, factory, executor, storage):
    while True:
        task = await backend.claim("restart-worker")
        if task is None:
            break
        await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="restart-worker", renew_interval=60.0, storage=storage)
