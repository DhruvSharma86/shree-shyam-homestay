"""Tests for database connection infrastructure."""

from app.core.db import Base, check_database_connection, get_engine


def test_engine_creation() -> None:
    """Engine is created lazily and is the same instance when reused."""
    first = get_engine()
    second = get_engine()
    assert first is second


def test_database_connection_check() -> None:
    """check_database_connection returns True against the test SQLite DB."""
    assert check_database_connection() is True


def test_base_metadata_contains_auth_tables() -> None:
    """Phase 1.2 registers users, sessions and audit_log on Base.metadata."""
    assert set(Base.metadata.tables) == {"users", "sessions", "audit_log"}
