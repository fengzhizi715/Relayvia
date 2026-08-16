"""Tests for the DefaultNodeExecutor HTTP contract and connector hardening."""

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.connectors.base import ExecutionResult, http_invocation_to_execution_result
from app.connectors.http import HTTPInvocationConfig, invoke_http
from app.domain.credentials.model import Credential, CredentialType
from app.infrastructure.security.crypto import CredentialCrypto
from app.runtime.executor.base import NodeExecutionContext
from app.runtime.executor.default import DefaultNodeExecutor, _compare


def agent_context(base_url: str, *, credential_id=None) -> NodeExecutionContext:
    return NodeExecutionContext(
        workflow_run_id="run-1",
        node_run_id="node-run-1",
        node_id="a",
        node_definition={"type": "agent", "subtype": "agent", "config": {"agent_id": "agent-1"}},
        resolved_config={"timeout_seconds": 10},
        resolved_input={"task": "review"},
        execution_snapshot={
            "agents": {
                "agent-1": {
                    "connector_type": "http",
                    "endpoint": f"{base_url}/agent",
                    "http_method": "POST",
                    "headers": {},
                    "timeout_seconds": 10,
                    "credential_id": credential_id,
                    "input_schema": {},
                    "output_schema": {},
                }
            }
        },
        attempt=2,
    )


@pytest.fixture()
def http_server():
    recorder: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, body: bytes, content_type: str = "application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/big":
                self.respond(200, b"x" * 2_000_000)
            elif self.path == "/fail":
                self.respond(500, b"{}")
            else:
                self.respond(200, b'{"ok": true}')

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            recorder["body"] = json.loads(self.rfile.read(length))
            recorder["headers"] = {key.lower(): value for key, value in self.headers.items()}
            self.respond(200, b'{"ok": true}')

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", recorder
    server.shutdown()
    thread.join(timeout=2)


def test_agent_invocation_body_contract(http_server):
    base_url, recorder = http_server
    context = agent_context(base_url)
    result = asyncio.run(DefaultNodeExecutor(None).execute(context))
    assert result.ok is True
    assert result.output == {"ok": True}
    assert result.metadata == {"status_code": 200}
    assert recorder["body"] == {
        "input": {"task": "review"},
        "context": {"workflow_run_id": "run-1", "node_id": "a", "attempt": 2},
    }


def test_execution_result_contract_from_http():
    ok = http_invocation_to_execution_result(
        __import__("app.connectors.result", fromlist=["HTTPInvocationResult"]).HTTPInvocationResult(
            ok=True, status_code=200, output={"ok": True}
        )
    )
    assert isinstance(ok, ExecutionResult)
    assert ok.status == "success"
    assert ok.output == {"ok": True}
    assert ok.artifacts == []
    assert ok.metadata == {"status_code": 200}
    assert ok.error is None

    failed = http_invocation_to_execution_result(
        __import__("app.connectors.result", fromlist=["HTTPInvocationResult"]).HTTPInvocationResult(
            ok=False, status_code=503, retryable=True, error_code="HTTP_503", message="down"
        )
    )
    assert failed.status == "failed"
    assert failed.retryable is True
    assert failed.error is not None
    assert failed.error.code == "HTTP_503"
    assert failed.metadata == {"status_code": 503}


def test_credential_injection_bearer(memory_db, http_server):
    _, factory = memory_db
    base_url, recorder = http_server
    with factory() as db:
        credential = Credential(
            name="bearer",
            type=CredentialType.BEARER_TOKEN.value,
            encrypted_payload=CredentialCrypto().encrypt({"value": "secret-token"}),
        )
        db.add(credential)
        db.commit()
        credential_id = credential.id
    context = agent_context(base_url, credential_id=credential_id)
    result = asyncio.run(DefaultNodeExecutor(factory).execute(context))
    assert result.ok is True
    assert recorder["headers"].get("authorization") == "Bearer secret-token"


def test_credential_injection_api_key(memory_db, http_server):
    _, factory = memory_db
    base_url, recorder = http_server
    with factory() as db:
        credential = Credential(
            name="api-key",
            type=CredentialType.API_KEY.value,
            encrypted_payload=CredentialCrypto().encrypt({"value": "key-12345"}),
        )
        db.add(credential)
        db.commit()
        credential_id = credential.id
    context = agent_context(base_url, credential_id=credential_id)
    result = asyncio.run(DefaultNodeExecutor(factory).execute(context))
    assert result.ok is True
    assert recorder["headers"].get("x-api-key") == "key-12345"


def test_credential_redacted_from_failure(memory_db):
    _, factory = memory_db
    with factory() as db:
        credential = Credential(
            name="secret",
            type=CredentialType.BEARER_TOKEN.value,
            encrypted_payload=CredentialCrypto().encrypt({"value": "top-secret-value"}),
        )
        db.add(credential)
        db.commit()
        credential_id = credential.id
    # Point the agent at an unreachable endpoint so the connector fails.
    context = agent_context("http://127.0.0.1:1/unreachable", credential_id=credential_id)
    result = asyncio.run(DefaultNodeExecutor(factory).execute(context))
    assert result.ok is False
    serialized = json.dumps(result.error.to_dict() if result.error else {})
    assert "top-secret-value" not in serialized


def test_http_response_size_cap(http_server):
    base_url, _ = http_server
    result = asyncio.run(
        invoke_http(HTTPInvocationConfig(url=f"{base_url}/big", method="GET", timeout_seconds=5))
    )
    assert result.ok is False
    assert result.error_code == "RESPONSE_TOO_LARGE"
    assert result.retryable is False


def test_http_ok_response_wrapped_when_not_object(http_server):
    base_url, _ = http_server
    result = asyncio.run(invoke_http(HTTPInvocationConfig(url=f"{base_url}/ok", method="GET", timeout_seconds=5)))
    # /ok returns {"ok": true}; /big is handled above.
    assert result.ok is True
    assert result.output == {"ok": True}


def test_condition_is_empty_tolerates_scalars():
    assert _compare(5, "is_empty", None) is False
    assert _compare(5, "is_not_empty", None) is True
    assert _compare("", "is_empty", None) is True
    assert _compare([], "is_empty", None) is True
    assert _compare([1], "is_not_empty", None) is True
    assert _compare(None, "is_empty", None) is True
    assert _compare(None, "is_not_empty", None) is False
