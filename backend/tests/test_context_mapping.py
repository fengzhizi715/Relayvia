"""Phase 9: Context / Variable Mapping tests.

Covers direct refs, type preservation, nested mapping, NodeRun isolation,
resolved-input persistence, credential non-exposure and end-to-end
Agent-A output -> Service-B input.
"""

import asyncio
import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from sqlalchemy import select

from app.domain.credentials.model import Credential, CredentialType
from app.domain.runs.models import NodeRun, WorkflowRun
from app.domain.workflows.model import Workflow, WorkflowVersion
from app.infrastructure.execution_backend.mysql import MySQLExecutionBackend
from app.infrastructure.security.crypto import CredentialCrypto
from app.runtime.context import ContextResolver, UnresolvedContextReference
from app.runtime.executor.default import DefaultNodeExecutor
from app.runtime.scheduler.workflow_scheduler import WorkflowScheduler
from app.runtime.state_machine import NodeRunStatus, WorkflowRunStatus
from app.workers.workflow_worker import _process_task


@pytest.fixture()
def recording_server():
    recorder: dict = {"paths": [], "bodies": []}

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, body: bytes):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            recorder["paths"].append(self.path)
            self.respond(200, b'{"ok": true}')

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            recorder["bodies"].append(self.rfile.read(length))
            self.respond(200, b'{"customer_id": 123}')

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", recorder
    server.shutdown()
    thread.join(timeout=2)


def chain_graph(service_mapping: dict, agent_mapping: dict | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "input", "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}},
            {"id": "agent_a", "type": "agent", "subtype": "agent", "name": "Agent A", "position": {"x": 100, "y": 0}, "config": {"agent_id": "agent-1"}, "input_mapping": agent_mapping or {}, "metadata": {}},
            {"id": "service_b", "type": "service", "subtype": "http", "name": "Service B", "position": {"x": 200, "y": 0}, "config": {"service_id": "service-1", "service_action_id": "action-1"}, "input_mapping": service_mapping, "metadata": {}},
            {"id": "output", "type": "data", "subtype": "output", "name": "Output", "position": {"x": 300, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "agent_a", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e2", "source": "agent_a", "target": "service_b", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
            {"id": "e3", "source": "service_b", "target": "output", "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}},
        ],
        "variables": {},
        "metadata": {},
    }


def snapshot_for(server: str, agent_credential_id=None) -> dict:
    return {
        "schema_version": "2",
        "agents": {
            "agent-1": {
                "connector_type": "http",
                "endpoint": f"{server}/agent",
                "http_method": "POST",
                "headers": {},
                "timeout_seconds": 10,
                "credential_id": agent_credential_id,
                "input_schema": {},
                "output_schema": {},
            }
        },
        "services": {"service-1": {"name": "svc", "base_url": server, "health_check_url": None, "credential_id": None}},
        "service_actions": {
            "action-1": {
                "service_id": "service-1",
                "name": "GetCustomer",
                "method": "GET",
                "path": "/customer/{customer_id}",
                "headers": {},
                "timeout_seconds": 10,
                "input_schema": {},
                "output_schema": {},
                "query_schema": {},
                "path_schema": {},
                "retry_policy": {},
            }
        },
    }


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
        input_json={"repository": "demo"},
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
                output_json={"repository": "demo"} if is_input else None,
                attempt=0,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def drive(factory, scheduler):
    backend = MySQLExecutionBackend(factory)
    executor = DefaultNodeExecutor(factory)

    async def _drive():
        while True:
            task = await backend.claim("ctx-worker")
            if task is None:
                break
            await _process_task(task, backend=backend, scheduler=scheduler, session_factory=factory, executor=executor, worker_id="ctx-worker", renew_interval=60.0)

    asyncio.run(_drive())


def test_node_a_output_resolves_into_node_b_path(memory_db, recording_server):
    _, factory = memory_db
    server, recorder = recording_server
    mapping = {"path": {"customer_id": "{{nodes.agent_a.output.customer_id}}"}}
    with factory() as db:
        run = make_run(db, chain_graph(mapping), snapshot_for(server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)

    with factory() as db:
        refreshed = db.get(WorkflowRun, run_id)
        assert refreshed.status == WorkflowRunStatus.COMPLETED.value
        service_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "service_b"))
        assert service_run.status == NodeRunStatus.COMPLETED.value
        assert service_run.input_json == {"path": {"customer_id": 123}}
    assert "/customer/123" in recorder["paths"]


def test_resolved_input_persisted_without_credential(memory_db, recording_server):
    _, factory = memory_db
    server, recorder = recording_server
    with factory() as db:
        credential = Credential(
            name="ctx-secret",
            type=CredentialType.BEARER_TOKEN.value,
            encrypted_payload=CredentialCrypto().encrypt({"value": "ctx-top-secret"}),
        )
        db.add(credential)
        db.commit()
        credential_id = credential.id
    mapping = {"task": "{{workflow.input.repository}}"}
    with factory() as db:
        run = make_run(db, chain_graph({"path": {"customer_id": "1"}}, agent_mapping=mapping), snapshot_for(server, agent_credential_id=credential_id))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)

    with factory() as db:
        agent_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "agent_a"))
        assert agent_run.input_json == {"task": "demo"}
        serialized = json.dumps(agent_run.input_json)
        assert "ctx-top-secret" not in serialized
        assert "ctx-secret" not in serialized


def test_unresolved_reference_fails_without_calling_connector(memory_db, recording_server):
    _, factory = memory_db
    server, recorder = recording_server
    # `agent_a` exists and is an upstream dependency, but produces no
    # `missing_field` output -> runtime resolution failure only (not a
    # statically-visible Contract error).
    mapping = {"path": {"customer_id": "{{nodes.agent_a.output.missing_field}}"}}
    with factory() as db:
        run = make_run(db, chain_graph(mapping), snapshot_for(server))
        run_id = run.id
        scheduler = WorkflowScheduler(default_max_attempts=1)
        scheduler.schedule_ready_nodes(db, run.id)
        db.commit()

    drive(factory, scheduler)

    with factory() as db:
        service_run = db.scalar(select(NodeRun).where(NodeRun.workflow_run_id == run_id, NodeRun.node_id == "service_b"))
        assert service_run.status == NodeRunStatus.FAILED.value
        assert service_run.error_json["code"] == "UNRESOLVED_CONTEXT_REFERENCE"
    assert recorder["paths"] == []  # connector never called


def test_resolver_preserves_types_and_is_run_isolated():
    resolver_a = ContextResolver(node_outputs={"planner": {"count": 3, "ok": True, "label": "x", "nested": {"a": 1}}})
    resolver_b = ContextResolver(node_outputs={"planner": {"count": 99}})

    assert resolver_a.resolve("{{nodes.planner.output.count}}") == 3
    assert resolver_a.resolve("{{nodes.planner.output.ok}}") is True
    assert resolver_a.resolve("{{nodes.planner.output.nested.a}}") == 1
    assert resolver_a.resolve({"total": "{{nodes.planner.output.count}}", "tags": ["{{nodes.planner.output.label}}"]}) == {"total": 3, "tags": ["x"]}

    # Same reference, different run snapshot -> isolated value.
    assert resolver_b.resolve("{{nodes.planner.output.count}}") == 99

    with pytest.raises(UnresolvedContextReference):
        resolver_b.resolve("{{nodes.planner.output.nested.a}}")


def test_workflow_input_and_variables_references():
    resolver = ContextResolver(workflow_input={"repository": "demo"}, variables={"branch": "feature/x"}, run={"id": "run-9"})
    assert resolver.resolve("{{workflow.input.repository}}") == "demo"
    assert resolver.resolve("{{workflow.variables.branch}}") == "feature/x"
    assert resolver.resolve("branch={{workflow.variables.branch}}") == "branch=feature/x"
    assert resolver.resolve("{{run.id}}") == "run-9"
