"""P0 regression coverage for control-plane, SSRF and Runner boundaries."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import RelayviaError
from app.infrastructure.security.url_policy import validate_http_url
from app.runners.runner import execute_task


def test_control_plane_rejects_anonymous_access(client):
    response = client.get(
        "/api/agents",
        headers={"Authorization": "Bearer wrong-token", "Origin": "http://localhost:5173"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "CONTROL_PLANE_AUTH_REQUIRED"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_health_remains_available_without_control_plane_token():
    from app.main import create_app

    with TestClient(create_app()) as anonymous_client:
        assert anonymous_client.get("/api/health").status_code == 200


def test_initial_runner_enrollment_requires_bootstrap_or_control_token(memory_db):
    from app.infrastructure.database.session import get_db
    from app.main import create_app

    _, factory = memory_db
    app = create_app()

    def override_get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as anonymous_client:
        response = anonymous_client.post(
            "/api/runners/register",
            json={"name": "unauthorized", "hostname": "host", "platform": "test", "capabilities": [], "metadata": {}},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "RUNNER_ENROLLMENT_REQUIRED"

    with TestClient(app) as bootstrap_client:
        enrolled = bootstrap_client.post(
            "/api/runners/register",
            json={"name": "bootstrap", "hostname": "host", "platform": "test", "capabilities": [], "metadata": {}},
            headers={"X-Relayvia-Runner-Enrollment-Token": "test-runner-enrollment-token"},
        )
    app.dependency_overrides.clear()
    assert enrolled.status_code == 201


def test_url_policy_rejects_private_targets_without_explicit_opt_in():
    for target in ("http://127.0.0.1:8000", "http://localhost:8000", "http://169.254.169.254/latest/meta-data"):
        with pytest.raises(RelayviaError) as raised:
            validate_http_url(target, field="endpoint", allow_private_network_urls=False)
        assert raised.value.code == "URL_PRIVATE_NETWORK_FORBIDDEN"


def test_runner_refuses_unsandboxed_execution_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.runners.runner.get_settings",
        lambda: Settings(runner_root=str(tmp_path), runner_allow_unsandboxed_execution=False, runner_sandbox_command=None, _env_file=None),
    )
    result = asyncio.run(execute_task({"config": {"command": "echo unsafe", "timeout_seconds": 5}}))
    assert result["ok"] is False
    assert result["error"]["code"] == "RUNNER_SANDBOX_REQUIRED"
