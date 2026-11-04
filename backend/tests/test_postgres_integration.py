"""PostgreSQL integration tests.

These run against a REAL PostgreSQL database (the production database).
Locally they skip when PostgreSQL is unreachable; in CI they MUST run —
the workflow sets ``REQUIRE_POSTGRES=1`` and pytest is configured to fail
if these tests are skipped in that mode (see ``tests/postgres_helpers.py``
and the ``pytest_collection_modifyitems`` hook in ``conftest.py``).

Coverage here is deliberately small and high-signal: it proves the full
auth stack (login → /me → RBAC denial → logout) works on PostgreSQL, not
just SQLite. The SQLite suite covers the exhaustive behavioural matrix.
"""

import os

import pytest
from sqlalchemy import inspect, text

from app.core.db import Base, get_engine


def _postgres_ready() -> bool:
    """True when a PostgreSQL database is configured and reachable."""
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        return False
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not _postgres_ready(), reason="PostgreSQL not reachable (local run)"),
]


@pytest.fixture(scope="module", autouse=True)
def _pg_schema():
    """Create tables on PostgreSQL once per module; drop at the end."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def pg_client():
    """TestClient bound to the real PostgreSQL engine (no overrides)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


def test_postgres_schema_contains_auth_tables() -> None:
    """PostgreSQL has users, sessions, audit_log with expected columns."""
    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())
    assert {"users", "sessions", "audit_log"} <= tables

    user_columns = {c["name"] for c in inspector.get_columns("users")}
    assert {"id", "username", "password_hash", "role", "is_active", "created_at"} <= user_columns


def test_postgres_full_auth_flow(pg_client) -> None:
    """Login → /me → RBAC → logout all work on PostgreSQL."""
    from app.core.db import get_session_factory
    from app.models.user import UserRole
    from tests.factories import (
        ADMIN_PASSWORD,
        RECEPTIONIST_PASSWORD,
        create_user,
        csrf_headers,
        login,
    )

    db = get_session_factory()()
    try:
        create_user(db, username="pgadmin", password=ADMIN_PASSWORD, role=UserRole.ADMIN.value)
        create_user(
            db, username="pgrec", password=RECEPTIONIST_PASSWORD, role=UserRole.RECEPTIONIST.value
        )
        db.commit()
    finally:
        db.close()

    # ADMIN login + user creation works.
    resp = login(pg_client, "pgadmin", ADMIN_PASSWORD)
    assert resp.status_code == 200, resp.text
    assert pg_client.get("/api/v1/auth/me").status_code == 200

    # RECEPTIONIST session: fresh client (cookies are per-client).
    from fastapi.testclient import TestClient

    from app.main import create_app

    rec_client = TestClient(create_app())
    resp2 = login(rec_client, "pgrec", RECEPTIONIST_PASSWORD)
    assert resp2.status_code == 200, resp2.text
    denied = rec_client.post(
        "/api/v1/users",
        json={
            "username": "shouldfail",
            "password": RECEPTIONIST_PASSWORD,
            "full_name": "Should Fail",
            "role": "ADMIN",
        },
        headers=csrf_headers(rec_client),
    )
    assert denied.status_code == 403

    # Logout revokes the session.
    out = pg_client.post("/api/v1/auth/logout", headers=csrf_headers(pg_client))
    assert out.status_code == 200
    assert pg_client.get("/api/v1/auth/me").status_code == 401
