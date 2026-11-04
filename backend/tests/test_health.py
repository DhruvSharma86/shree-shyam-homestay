"""Tests for the health endpoints."""

from fastapi.testclient import TestClient


def test_liveness_returns_ok(client: TestClient) -> None:
    """GET /health/live returns 200 without touching the database."""
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_database_ok_with_sqlite(client: TestClient) -> None:
    """GET /health/ready returns 200 when the test DB answers SELECT 1."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"


def test_health_aggregate_ok(client: TestClient) -> None:
    """GET /health returns the aggregate payload when the DB is reachable."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert "environment" in body


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    """Unknown routes return the standard {error:{code,message}} envelope."""
    response = client.get("/does/not/exist")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"]
