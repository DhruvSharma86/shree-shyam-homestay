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


def test_base_metadata_is_empty_without_models() -> None:
    """Phase 1.1 ships no ORM tables — metadata must be empty.

    Guards against accidentally adding models in this milestone; real
    tables arrive in Phase 1.2.
    """
    assert len(Base.metadata.tables) == 0
