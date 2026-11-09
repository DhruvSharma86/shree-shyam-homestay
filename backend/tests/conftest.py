"""Shared pytest fixtures for the backend test suite.

Default (local) mode: in-memory SQLite — the suite passes with no live
PostgreSQL. When ``DATABASE_URL`` points at PostgreSQL, tests run against
that database instead. PostgreSQL-only tests are marked
``@pytest.mark.postgres`` and skip cleanly when no database is reachable
(CI enforces they run — see ``.github/workflows/ci.yml`` and
``pytest.ini``'s ``REQUIRE_POSTGRES`` handling in
``tests/postgres_helpers.py``).
"""

import os

# Must be set BEFORE importing app modules so settings/engine pick it up.
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import Base, get_engine, reset_engine
from app.main import create_app


def _postgres_reachable() -> bool:
    """Return True when the configured database is PostgreSQL and reachable."""
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        return False
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def _reset_engine_after_session():
    """Dispose the cached test engine once the whole session is done."""
    yield
    reset_engine()


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Clear the in-process rate-limit store before each test.

    Portal budgets are per-IP; without this, failures from one test would
    exhaust the budget shared by the TestClient peer ("testclient") for the
    next test (300s sliding window). Every test starts with a clean budget.
    """
    from app.auth.rate_limit import _attempts

    _attempts.clear()
    yield
    _attempts.clear()


@pytest.fixture(scope="session")
def _schema():
    """Create all tables once per session; drop them at the end.

    Tests share one engine (required for in-memory SQLite). The
    ``db_session`` fixture truncates all tables before and after each test
    so rows committed by application code (login, bootstrap) never leak
    between tests.
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _truncate_all() -> None:
    """Delete every row from every table (autocommit — survives outer txns)."""
    from sqlalchemy import text as _text

    engine = get_engine()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(_text(f"DELETE FROM {table.name}"))


@pytest.fixture()
def db_session(_schema):
    """Yield a DB session with per-test isolation.

    The transaction is rolled back after each test. ``savepoint`` mode is
    deliberately NOT used: application code (login, bootstrap, etc.)
    issues its own COMMITs, which would release a SAVEPOINT and leak rows
    into later tests. Full rollback keeps every test hermetic.
    """
    from app.core.db import get_session_factory

    _truncate_all()
    connection = get_engine().connect()
    transaction = connection.begin()
    session = get_session_factory()(bind=connection)
    yield session
    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
    _truncate_all()


@pytest.fixture(autouse=True)
def _reset_login_rate_limits():
    """Clear the in-process login rate limiter between tests."""
    from app.auth.rate_limit import _attempts

    _attempts.clear()
    yield
    _attempts.clear()


@pytest.fixture()
def client(db_session) -> TestClient:
    """TestClient whose app uses the per-test transactional DB session."""
    from app.core.db import get_db

    app = create_app()

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


@pytest.fixture()
def postgres_available() -> bool:
    """True when PostgreSQL integration tests should run."""
    return _postgres_reachable()


def postgres_required() -> bool:
    """True when the CI environment demands PostgreSQL tests run."""
    return os.environ.get("REQUIRE_POSTGRES", "").lower() in ("1", "true", "yes")


def pytest_addoption(parser) -> None:
    """Add the --run-postgres-check flag used by CI."""
    parser.addoption(
        "--run-postgres-check",
        action="store_true",
        default=False,
        help="Fail if any postgres-marked test is skipped (CI enforcement).",
    )


def pytest_collection_finish(session) -> None:
    """Fail fast in CI mode when PostgreSQL tests would be skipped.

    Runs at collection time — before any test executes — so a misconfigured
    CI job (PostgreSQL service down) fails immediately instead of silently
    skipping the integration tests.
    """
    if not session.config.getoption("--run-postgres-check"):
        return
    for item in session.items:
        if "postgres" in [m.name for m in item.iter_markers()]:
            has_skip = any(marker.name in ("skip", "skipif") for marker in item.iter_markers())
            if has_skip and not _postgres_reachable():
                raise pytest.UsageError(
                    "PostgreSQL test would be skipped but "
                    "--run-postgres-check was given. Check the PostgreSQL "
                    "service in CI."
                )
