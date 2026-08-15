def test_credential_is_encrypted_and_not_returned(client, db_session):
    response = client.post(
        "/api/credentials",
        json={"name": "Review API", "type": "bearer_token", "value": "top-secret"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["has_secret"] is True
    assert "value" not in body
    assert "encrypted_payload" not in body
    credential = db_session.query(__import__("app.domain.credentials.model", fromlist=["Credential"]).Credential).one()
    assert credential.encrypted_payload != "top-secret"
    assert "top-secret" not in credential.encrypted_payload
    assert client.get("/api/credentials").json()[0].get("value") is None


def test_agent_crud_duplicate_name_and_schema_validation(client, http_test_server):
    payload = {
        "name": "Code Review Agent",
        "description": "Existing HTTP agent",
        "connector_type": "http",
        "endpoint": f"{http_test_server}/agent",
        "health_check_url": f"{http_test_server}/health",
        "capabilities": [{"name": "code_review", "description": "Review source code"}],
        "input_schema": {"type": "object", "properties": {"task": {"type": "string"}}},
        "output_schema": {"type": "object"},
    }
    created = client.post("/api/agents", json=payload)
    assert created.status_code == 201
    agent = created.json()
    assert agent["id"]
    assert agent["status"] == "unknown"
    assert agent["connector_type"] == "http"

    duplicate = client.post("/api/agents", json=payload)
    assert duplicate.status_code == 400
    assert duplicate.json()["error"]["code"] == "DUPLICATE_NAME"

    invalid_schema = client.post(
        "/api/agents",
        json={
            "name": "Invalid Schema Agent",
            "endpoint": f"{http_test_server}/agent",
            "input_schema": {"type": "not-a-json-schema-type"},
        },
    )
    assert invalid_schema.status_code == 400
    assert invalid_schema.json()["error"]["code"] == "INVALID_SCHEMA"

    secret_in_metadata = client.post(
        "/api/agents",
        json={
            "name": "Secret Metadata Agent",
            "endpoint": f"{http_test_server}/agent",
            "metadata": {"api_token": "should-not-be-stored"},
        },
    )
    assert secret_in_metadata.status_code == 400
    assert secret_in_metadata.json()["error"]["code"] == "SECRET_IN_CONFIG"

    updated = client.put(f"/api/agents/{agent['id']}", json={"enabled": False, "name": "Code Review Agent v2"})
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["name"] == "Code Review Agent v2"

    assert client.get(f"/api/agents/{agent['id']}").status_code == 200
    missing = client.get("/api/agents/not-found")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "AGENT_NOT_FOUND"


def test_agent_connection_test_updates_health(client, http_test_server):
    created = client.post(
        "/api/agents",
        json={
            "name": "Healthy Agent",
            "endpoint": f"{http_test_server}/agent",
            "health_check_url": f"{http_test_server}/health",
        },
    ).json()

    result = client.post(f"/api/agents/{created['id']}/test")
    assert result.status_code == 200
    assert result.json()["status"] == "healthy"
    assert result.json()["latency_ms"] is not None
    assert client.get(f"/api/agents/{created['id']}").json()["status"] == "healthy"

    failing = client.post(
        "/api/agents",
        json={
            "name": "Failing Agent",
            "endpoint": f"{http_test_server}/agent",
            "health_check_url": f"{http_test_server}/fail",
        },
    ).json()
    failed_result = client.post(f"/api/agents/{failing['id']}/test")
    assert failed_result.json()["status"] == "unhealthy"
    assert failed_result.json()["error_code"] == "HTTP_503"


def test_service_actions_and_connection_test(client, http_test_server):
    service = client.post(
        "/api/services",
        json={
            "name": "YoloWebAgent",
            "base_url": f"{http_test_server}/api",
            "health_check_url": f"{http_test_server}/api/health",
        },
    )
    assert service.status_code == 201
    service_id = service.json()["id"]
    assert service.json()["actions_count"] == 0

    action = client.post(
        f"/api/services/{service_id}/actions",
        json={
            "name": "Get Training Status",
            "method": "GET",
            "path": "training/jobs/{job_id}",
            "path_schema": {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
            "output_schema": {"type": "object"},
            "retry_policy": {"max_retries": 2, "backoff_seconds": 5, "retry_on_status": [429, 503]},
        },
    )
    assert action.status_code == 201
    assert action.json()["path"] == "/training/jobs/{job_id}"
    action_id = action.json()["id"]

    assert client.get(f"/api/services/{service_id}/actions").json()[0]["id"] == action_id
    assert client.post(f"/api/services/{service_id}/test").json()["status"] == "healthy"
    detail = client.get(f"/api/services/{service_id}").json()
    assert detail["status"] == "healthy"
    assert detail["actions_count"] == 1

    invalid_action = client.post(
        f"/api/services/{service_id}/actions",
        json={"name": "Bad", "path": "https://example.com/unsafe", "input_schema": {"type": "invalid"}},
    )
    assert invalid_action.status_code == 400
    assert invalid_action.json()["error"]["code"] == "INVALID_PATH"

    assert client.delete(f"/api/services/{service_id}/actions/{action_id}").status_code == 204
    assert client.delete(f"/api/services/{service_id}").status_code == 204
    assert client.get(f"/api/services/{service_id}").status_code == 404


def test_credential_in_use_cannot_be_deleted(client, http_test_server):
    credential = client.post(
        "/api/credentials",
        json={"name": "Protected Token", "type": "api_key", "value": "secret"},
    ).json()
    service = client.post(
        "/api/services",
        json={
            "name": "Protected Service",
            "base_url": http_test_server,
            "credential_id": credential["id"],
        },
    ).json()

    blocked = client.delete(f"/api/credentials/{credential['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "CREDENTIAL_IN_USE"

    assert client.delete(f"/api/services/{service['id']}").status_code == 204
    assert client.delete(f"/api/credentials/{credential['id']}").status_code == 204
