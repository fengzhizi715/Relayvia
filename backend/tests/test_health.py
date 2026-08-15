from fastapi.testclient import TestClient

from app.api.routes import health as health_route
from app.main import create_app


def test_health_reports_connected_database(monkeypatch):
    monkeypatch.setattr(health_route, "check_database", lambda: True)

    response = TestClient(create_app()).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "relayvia-api",
        "database": "connected",
    }


def test_health_degrades_without_database(monkeypatch):
    monkeypatch.setattr(health_route, "check_database", lambda: False)

    response = TestClient(create_app()).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "unavailable"

