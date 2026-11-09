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
    """Phase 1.2 + 2.1 + 3.1 + 3.2 + 4.1 + 4.3 + 5.1 + 5.2 registers all tables."""
    assert set(Base.metadata.tables) == {
        "users",
        "sessions",
        "audit_log",
        "hotel_info",
        "room_types",
        "rooms",
        "room_rates",
        "tax_settings",
        "restaurant_info",
        "menu_categories",
        "menu_items",
        "cab_info",
        "guests",
        "bookings",
        "folio_entries",
        "payments",
        "receipts",
        "guest_portal_tokens",
        "tour_packages",
        "local_info",
    }
