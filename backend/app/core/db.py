"""Database connection infrastructure (SQLAlchemy 2.0).

PostgreSQL via the ``psycopg`` v3 driver is the production database.
SQLite is supported only as a local/test convenience (e.g. pytest without
a live Postgres). The engine/session factory is created lazily so importing
this module never opens a connection.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base class for all ORM models (Phase 1.2+).

    All models in the system inherit from this base so Alembic can discover
    them via ``Base.metadata``.
    """


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        if url.startswith("sqlite"):
            # SQLite: allow cross-thread use (TestClient runs handlers in a
            # worker thread) and keep a single connection for in-memory DBs.
            _engine = create_engine(
                url,
                future=True,
                connect_args={"check_same_thread": False},
            )
        else:
            _engine = create_engine(
                url,
                future=True,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_timeout=settings.database_pool_timeout,
                pool_pre_ping=True,
            )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory, creating it on first use."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped database session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager yielding a session that commits/rolls back on exit.

    Used by application services (never by route handlers directly) for
    multi-statement transactional work such as financial operations.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connection() -> bool:
    """Return True when a trivial SELECT succeeds, False otherwise.

    Never raises — callers (readiness endpoint) translate the result into
    HTTP status. Used by ``GET /health/ready``.
    """
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def reset_engine() -> None:
    """Dispose the cached engine/session factory (test support only)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
