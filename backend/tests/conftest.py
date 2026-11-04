"""Shared pytest fixtures for the backend test suite.

Tests run against an in-memory SQLite database by default so the suite
passes without a live PostgreSQL. Set the ``DATABASE_URL`` env var to a
PostgreSQL URL to run against a real database instead (e.g. in CI with the
docker-compose ``db`` service).
"""

import os

# Must be set BEFORE importing app modules so settings/engine pick it up.
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient

from app.core.db import reset_engine
from app.main import create_app


@pytest.fixture(scope="session", autouse=True)
def _reset_engine_after_session():
    """Dispose the cached test engine once the whole session is done."""
    yield
    reset_engine()


@pytest.fixture()
def client() -> TestClient:
    """Return a FastAPI TestClient bound to a fresh app instance."""
    reset_engine()
    return TestClient(create_app())
