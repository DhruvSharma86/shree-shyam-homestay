"""Operational config + health tests (Priority 6)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings


def _valid_production_kwargs(**overrides):
    base = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://hotel_app:s3cret-prod-pw@db:5432/shree_shyam",
        "session_secret": "production-secret-value-0123456789abcdef",
        "cors_origins": "https://stay.example.com",
        "app_debug": False,
    }
    base.update(overrides)
    return base


def test_valid_production_config_passes():
    """A fully-specified production config boots (guard permits it)."""
    s = Settings(**_valid_production_kwargs())
    assert s.is_production is True
    assert s.cors_origin_list == ["https://stay.example.com"]


def test_production_rejects_debug():
    with pytest.raises(ValueError):
        Settings(**_valid_production_kwargs(app_debug=True))


def test_production_rejects_dev_session_secret():
    with pytest.raises(ValueError):
        Settings(**_valid_production_kwargs(session_secret="dev-only-insecure-secret-change-me"))


def test_production_rejects_placeholder_database_password():
    with pytest.raises(ValueError):
        Settings(
            **_valid_production_kwargs(
                database_url="postgresql+psycopg://hotel_app:change_me@localhost:5432/shree_shyam"
            )
        )


def test_production_rejects_sqlite():
    with pytest.raises(ValueError):
        Settings(**_valid_production_kwargs(database_url="sqlite:///./prod.db"))


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValueError):
        Settings(**_valid_production_kwargs(cors_origins="*"))


def test_development_defaults_still_boot():
    """Dev (default) config has no production guards (convenient locally)."""
    s = Settings(app_env="development")
    assert s.is_production is False
    assert s.cors_origin_list == ["http://localhost:3000"]


def test_health_liveness_needs_no_database(client):
    """Liveness returns ok even without any database (no writes)."""
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ready_reflects_database(client, db_session):
    """Readiness returns ready when the DB answers (no secrets in body)."""
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "ok"
    blob = str(body)
    assert "password" not in blob.lower() and "postgresql" not in blob.lower()


def test_health_ready_reports_unavailable_without_database(db_session, monkeypatch):
    """With a broken database, readiness is 503 (never a fake healthy)."""
    import app.api.health as health_mod
    from app.core.db import get_db
    from app.main import create_app


    monkeypatch.setattr(health_mod, "check_database_connection", lambda: False)
    app = create_app()

    def _broken():
        yield db_session

    app.dependency_overrides[get_db] = _broken
    r = TestClient(app).get("/health/ready")
    assert r.status_code == 503
    assert "password" not in r.text.lower()
