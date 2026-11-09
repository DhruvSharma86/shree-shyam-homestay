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
    """PostgreSQL has users, sessions, audit_log, guests, bookings + key columns."""
    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())
    assert {"users", "sessions", "audit_log", "guests", "bookings"} <= tables

    user_columns = {c["name"] for c in inspector.get_columns("users")}
    assert {"id", "username", "password_hash", "role", "is_active", "created_at"} <= user_columns

    guest_columns = {c["name"] for c in inspector.get_columns("guests")}
    assert {
        "id",
        "full_name",
        "phone",
        "is_active",
        "created_by",
        "created_at",
        "updated_at",
    } <= guest_columns

    indexes = {ix["name"] for ix in inspector.get_indexes("guests")}
    assert "ix_guests_phone_name_active" in indexes

    booking_columns = {c["name"] for c in inspector.get_columns("bookings")}
    assert {
        "id",
        "booking_ref",
        "guest_id",
        "room_id",
        "status",
        "source",
        "check_in_date",
        "check_out_date",
        "nights",
        "night_rate_snapshot",
        "room_subtotal",
        "total_amount",
    } <= booking_columns
    # Exclusion constraint exists when the DB was created by Alembic
    # (create_all alone does not add it — CI migrates first).
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'bookings'::regclass "
                "AND conname = 'excl_bookings_room_daterange'"
            )
        ).fetchone()
        assert row is not None, "missing excl_bookings_room_daterange (run alembic upgrade head)"


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


def test_postgres_guest_flow(pg_client) -> None:
    """Guest registration + duplicate guard work on PostgreSQL."""
    from app.core.db import get_session_factory
    from app.models.user import UserRole
    from tests.factories import (
        ADMIN_PASSWORD,
        create_user,
        csrf_headers,
        login,
    )

    db = get_session_factory()()
    try:
        # Clean prior run data if any (module reuses tables).
        from sqlalchemy import text as _t

        db.execute(_t("DELETE FROM guests"))
        db.execute(_t("DELETE FROM users WHERE username = 'pgguestadmin'"))
        create_user(db, username="pgguestadmin", password=ADMIN_PASSWORD, role=UserRole.ADMIN.value)
        db.commit()
    finally:
        db.close()

    assert login(pg_client, "pgguestadmin", ADMIN_PASSWORD).status_code == 200
    headers = csrf_headers(pg_client)
    created = pg_client.post(
        "/api/v1/guests", json={"full_name": "Pg Guest", "phone": "9876500099"}, headers=headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["phone"] == "+919876500099"
    dup = pg_client.post(
        "/api/v1/guests", json={"full_name": "pg guest", "phone": "+919876500099"}, headers=headers
    )
    assert dup.status_code == 409
    listed = pg_client.get("/api/v1/guests?q=pg+guest")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def _pg_booking_setup(pg_client):
    """Create admin-sourced room/type/rate/guest on PostgreSQL; return ids."""
    import uuid as _uuid
    from datetime import UTC, datetime, timedelta

    from app.core.db import get_session_factory
    from app.models.user import UserRole
    from tests.factories import (
        ADMIN_PASSWORD,
        create_user,
        csrf_headers,
        login,
    )

    today = datetime.now(UTC).date()
    db = get_session_factory()()
    try:
        db.execute(text("DELETE FROM bookings"))
        db.execute(text("DELETE FROM users WHERE username = 'pgbookadmin'"))
        create_user(db, username="pgbookadmin", password=ADMIN_PASSWORD, role=UserRole.ADMIN.value)
        db.commit()
    finally:
        db.close()
    assert login(pg_client, "pgbookadmin", ADMIN_PASSWORD).status_code == 200
    headers = csrf_headers(pg_client)
    rt = pg_client.post("/api/v1/admin/room-types", json={"name": "PG Deluxe"}, headers=headers)
    assert rt.status_code == 201, rt.text
    room_type_id = rt.json()["id"]
    room = pg_client.post(
        "/api/v1/admin/rooms",
        json={"room_number": "PG101", "room_type_id": room_type_id},
        headers=headers,
    )
    assert room.status_code == 201, room.text
    room_id = room.json()["id"]
    rate = pg_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": "3000.00",
            "valid_from": today.isoformat(),
            "valid_until": (today + timedelta(days=400)).isoformat(),
        },
        headers=headers,
    )
    assert rate.status_code == 201, rate.text
    guest = pg_client.post(
        "/api/v1/guests", json={"full_name": "PG Booker", "phone": "9876500777"}, headers=headers
    )
    assert guest.status_code == 201, guest.text
    guest_id = guest.json()["id"]
    me = pg_client.get("/api/v1/auth/me")
    actor_id = _uuid.UUID(me.json()["user"]["id"])
    check_in = today + timedelta(days=1)
    check_out = today + timedelta(days=4)
    return room_id, room_type_id, guest_id, actor_id, check_in, check_out


def test_postgres_booking_flow(pg_client) -> None:
    """Booking create/overlap/cancel works on PostgreSQL (exclusion + service)."""
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    payload = {
        "guest_id": guest_id,
        "room_id": room_id,
        "source": "PHONE",
        "check_in_date": check_in.isoformat(),
        "check_out_date": check_out.isoformat(),
        "number_of_guests": 1,
    }
    created = pg_client.post("/api/v1/bookings", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["nights"] == 3
    assert created.json()["room_subtotal"] == "9000.00"
    # Overlapping re-book → 409.
    dup = pg_client.post("/api/v1/bookings", json=payload, headers=headers)
    assert dup.status_code == 409, dup.text
    # Cancel releases the room; re-book succeeds.
    booking_id = created.json()["id"]
    cancel = pg_client.post(
        f"/api/v1/bookings/{booking_id}/cancel", json={"reason": "pg test"}, headers=headers
    )
    assert cancel.status_code == 200
    again = pg_client.post("/api/v1/bookings", json=payload, headers=headers)
    assert again.status_code == 201, again.text


def test_postgres_booking_concurrent_overlap(pg_client) -> None:
    """Two simultaneous overlapping creates — at most one succeeds (PG proof)."""
    import threading
    import uuid as _uuid

    from app.bookings.service import BookingOverlapError, create_booking
    from app.core.db import get_session_factory

    (
        room_id,
        _rt,
        guest_id,
        actor_id,
        check_in,
        check_out,
    ) = _pg_booking_setup(pg_client)
    room_uuid = _uuid.UUID(room_id)
    guest_uuid = _uuid.UUID(guest_id)
    results: list[str] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        barrier.wait(timeout=10)
        db = get_session_factory()()
        try:
            create_booking(
                db,
                guest_id=guest_uuid,
                room_id=room_uuid,
                source="PHONE",
                check_in_date=check_in,
                check_out_date=check_out,
                number_of_guests=1,
                notes=None,
                actor_user_id=actor_id,
            )
            db.commit()
            results.append("ok")
        except BookingOverlapError:
            db.rollback()
            results.append("conflict")
        except Exception:
            db.rollback()
            results.append("error")
        finally:
            db.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results) == ["conflict", "ok"], results
