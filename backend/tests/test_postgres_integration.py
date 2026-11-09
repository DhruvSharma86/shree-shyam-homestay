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
from datetime import UTC

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
    assert {
        "users",
        "sessions",
        "audit_log",
        "guests",
        "bookings",
        "folio_entries",
        "payments",
        "receipts",
        "guest_portal_tokens",
    } <= tables

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
        "checked_in_at",
        "checked_in_by",
        "checked_out_at",
        "checked_out_by",
    } <= booking_columns
    folio_columns = {c["name"] for c in inspector.get_columns("folio_entries")}
    assert {
        "id",
        "booking_id",
        "entry_type",
        "description",
        "quantity",
        "amount",
        "is_initial",
        "reverses_entry_id",
        "created_by",
        "created_at",
    } <= folio_columns
    payment_columns = {c["name"] for c in inspector.get_columns("payments")}
    assert {
        "id",
        "booking_id",
        "amount",
        "mode",
        "payment_stage",
        "received_by",
        "received_at",
        "is_reversal",
        "reverses_payment_id",
    } <= payment_columns
    receipt_columns = {c["name"] for c in inspector.get_columns("receipts")}
    assert {
        "id",
        "booking_id",
        "receipt_ref",
        "kind",
        "content_hash",
        "pdf_content",
        "generated_by",
        "created_at",
    } <= receipt_columns
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
    # Unique suffix per call: room-type name, room number and guest phone
    # are unique in the DB (and the API rejects duplicates with 409), so
    # repeated setup in the same module would otherwise collide.
    suffix = _uuid.uuid4().hex[:8].upper()
    phone = f"98765{int(suffix, 16) % 100000:05d}"
    db = get_session_factory()()
    try:
        # TRUNCATE (not DELETE): the append-only triggers reject DELETE
        # on finance tables, but TRUNCATE bypasses row triggers and is a
        # clean test-isolation step. receipts is included because it
        # references bookings (FK RESTRICT), and so are guest_portal_tokens.
        db.execute(
            text("TRUNCATE guest_portal_tokens, receipts, payments, folio_entries, bookings")
        )
        db.execute(text("DELETE FROM users WHERE username = 'pgbookadmin'"))
        create_user(db, username="pgbookadmin", password=ADMIN_PASSWORD, role=UserRole.ADMIN.value)
        db.commit()
    finally:
        db.close()
    assert login(pg_client, "pgbookadmin", ADMIN_PASSWORD).status_code == 200
    headers = csrf_headers(pg_client)
    rt = pg_client.post(
        "/api/v1/admin/room-types", json={"name": f"PG Deluxe {suffix}"}, headers=headers
    )
    assert rt.status_code == 201, rt.text
    room_type_id = rt.json()["id"]
    room = pg_client.post(
        "/api/v1/admin/rooms",
        json={"room_number": f"PG{suffix[:6]}", "room_type_id": room_type_id},
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
        "/api/v1/guests", json={"full_name": "PG Booker", "phone": phone}, headers=headers
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

    from sqlalchemy.exc import IntegrityError

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
        except IntegrityError:
            # Exclusion-constraint backstop fires (e.g. under racing INSERTs);
            # the API maps this to 409 as well.
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


def test_postgres_folio_flow(pg_client) -> None:
    """Folio view, charge, discount and reversal work on PostgreSQL."""
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    created = pg_client.post(
        "/api/v1/bookings",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "source": "PHONE",
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "number_of_guests": 1,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    booking_id = created.json()["id"]
    folio = pg_client.get(f"/api/v1/bookings/{booking_id}/folio")
    assert folio.status_code == 200, folio.text
    body = folio.json()
    assert len(body["entries"]) == 1 and body["entries"][0]["is_initial"] is True
    assert body["total_charges"] == "9000.00"
    charge = pg_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "PG food", "quantity": "1", "unit_amount": "500.00"},
        headers=headers,
    )
    assert charge.status_code == 201, charge.text
    assert charge.json()["amount"] == "500.00"
    discount = pg_client.post(
        f"/api/v1/bookings/{booking_id}/folio/discounts",
        json={"amount": "100.00", "reason": "pg discount"},
        headers=headers,
    )
    assert discount.status_code == 201, discount.text
    reversal = pg_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": charge.json()["id"], "reason": "pg undo"},
        headers=headers,
    )
    assert reversal.status_code == 201, reversal.text
    final = pg_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    assert final["total_charges"] == "8900.00", final  # 9000+500-100-500


def test_postgres_finance_triggers(pg_client) -> None:
    """Append-only triggers reject UPDATE/DELETE but allow INSERT."""
    import pytest
    from sqlalchemy.exc import DBAPIError

    from app.core.db import get_engine
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    created = pg_client.post(
        "/api/v1/bookings",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "source": "PHONE",
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "number_of_guests": 1,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    booking_id = created.json()["id"]
    engine = get_engine()
    # Triggers must exist (migrated schema, not create_all-only).
    with engine.connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE tgrelid IN "
                    "('folio_entries'::regclass, 'payments'::regclass) AND NOT tgisinternal"
                )
            )
        }
        assert "trg_folio_entries_immutable" in names, names
        assert "trg_payments_immutable" in names, names
    entry_id = pg_client.get(f"/api/v1/bookings/{booking_id}/folio").json()["entries"][0]["id"]
    # NOTE: PG raises P0001 (raise_exception) which SQLAlchemy surfaces as
    # InternalError (a DBAPIError), not IntegrityError.
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE folio_entries SET amount = 1 WHERE id = :id"), {"id": entry_id}
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM folio_entries WHERE id = :id"), {"id": entry_id})
    # INSERT still allowed: API reversal succeeds afterwards.
    rev = pg_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": entry_id, "reason": "pg trigger check"},
        headers=headers,
    )
    assert rev.status_code == 201, rev.text


def test_postgres_receipts_immutable(pg_client) -> None:
    """Issued receipts reject UPDATE/DELETE on PostgreSQL (triggers protect bytes)."""
    import uuid

    import pytest
    from sqlalchemy.exc import DBAPIError

    from app.core.db import get_engine
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    booking_id = _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out)
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "3000.00", "mode": "UPI", "payment_stage": "CHECK_IN"},
        headers=headers,
    )
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "6000.00", "mode": "CASH", "payment_stage": "OTHER"},
        headers=headers,
    )
    checked = pg_client.post(
        f"/api/v1/bookings/{booking_id}/check-in", json={}, headers=headers
    )
    assert checked.status_code == 200, checked.text
    out = pg_client.post(
        f"/api/v1/bookings/{booking_id}/check-out", json={}, headers=headers
    )
    assert out.status_code == 200, out.text
    receipt_id = pg_client.get(f"/api/v1/bookings/{booking_id}/receipt").json()["receipt_id"]
    engine = get_engine()
    with engine.connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                text("SELECT tgname FROM pg_trigger WHERE tgrelid = 'receipts'::regclass")
            )
        }
        assert "trg_receipts_immutable" in names, names
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE receipts SET content_hash = 'x' WHERE id = :id"),
                {"id": uuid.UUID(receipt_id)},
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM receipts WHERE id = :id"), {"id": uuid.UUID(receipt_id)})
    # Issued receipt survives (bytes unchanged).
    assert pg_client.get(f"/api/v1/bookings/{booking_id}/receipt").status_code == 200


def test_postgres_report_aggregations(pg_client) -> None:
    """SUM aggregations + Decimal correctness on PostgreSQL."""
    from datetime import timedelta
    from decimal import Decimal

    from sqlalchemy import select

    from app.core.db import get_session_factory
    from app.models.payment import Payment
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    booking_id = _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out)
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "3000.00", "mode": "UPI", "payment_stage": "CHECK_IN"},
        headers=headers,
    )
    today = check_in - timedelta(days=1)
    summary = pg_client.get(
        f"/api/v1/reports/financial/summary?from_date={today.isoformat()}&to_date={today.isoformat()}"
    )
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["room_charges"] == "9000.00"
    assert body["net_payments"] == "3000.00"
    assert body["outstanding"] == "6000.00"
    db = get_session_factory()()
    try:
        db_sum = db.scalars(select(Payment.amount).where(Payment.booking_id == booking_id)).all()
        assert sum(db_sum, Decimal(0)) == Decimal("3000.00")
    finally:
        db.close()


def _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out):
    """Create a booking on PG and return its id."""
    created = pg_client.post(
        "/api/v1/bookings",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "source": "PHONE",
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "number_of_guests": 1,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_postgres_portal_token_roundtrip(pg_client) -> None:
    """Portal token: hash-only storage, overview, revocation, expiry rules."""
    from datetime import datetime, timedelta

    from sqlalchemy import text as _t

    from app.core.db import get_session_factory
    from app.models.booking import Booking
    from app.models.guest_portal_token import GuestPortalToken
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    booking_id = _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out)
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "3000.00", "mode": "UPI", "payment_stage": "CHECK_IN"},
        headers=headers,
    )
    checked = pg_client.post(
        f"/api/v1/bookings/{booking_id}/check-in", json={}, headers=headers
    )
    assert checked.status_code == 200, checked.text
    raw = checked.json()["portal_access_token"]
    assert raw not in (None, "")
    # Hash-only persisted.
    db = get_session_factory()()
    try:
        rows = db.query(GuestPortalToken).filter(
            GuestPortalToken.booking_id == booking_id
        ).all()
        assert len(rows) == 1
        assert rows[0].token_hash != raw
        assert len(rows[0].token_hash) == 64
        booking = db.get(Booking, booking_id)
        booking.checked_out_at = datetime.now(UTC) - timedelta(hours=23)
        db.commit()
    finally:
        db.close()
    # Valid 23h after checkout; dead 25h after.
    assert pg_client.get(f"/api/v1/guest-portal/{raw}/overview").status_code == 200
    db = get_session_factory()()
    try:
        booking = db.get(Booking, booking_id)
        booking.checked_out_at = datetime.now(UTC) - timedelta(hours=25)
        db.commit()
    finally:
        db.close()
    assert pg_client.get(f"/api/v1/guest-portal/{raw}/overview").status_code == 404
    # Revocation cuts the rotated token too.
    db = get_session_factory()()
    try:
        booking = db.get(Booking, booking_id)
        booking.checked_out_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()
    rotate = pg_client.post(
        f"/api/v1/guest-portal/admin-rotate/{booking_id}", headers=headers
    )
    assert rotate.status_code == 200, rotate.text
    rotated = rotate.json()["portal_access_token"]
    assert pg_client.get(f"/api/v1/guest-portal/{rotated}/overview").status_code == 200
    revoke = pg_client.post(
        f"/api/v1/guest-portal/admin-revoke/{booking_id}", headers=headers
    )
    assert revoke.status_code == 200
    assert pg_client.get(f"/api/v1/guest-portal/{rotated}/overview").status_code == 404
    with get_engine().connect() as conn:
        count = conn.execute(
            _t(
                "SELECT count(*) FROM guest_portal_tokens WHERE booking_id = :id "
                "AND revoked_at IS NULL"
            ),
            {"id": booking_id},
        ).scalar()
        assert count == 0


def test_postgres_portal_isolation(pg_client) -> None:
    """Two bookings' tokens are disjoint; staff APIs stay session-gated."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    booking_id = _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out)
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "3000.00", "mode": "UPI", "payment_stage": "CHECK_IN"},
        headers=headers,
    )
    checked = pg_client.post(
        f"/api/v1/bookings/{booking_id}/check-in", json={}, headers=headers
    )
    raw = checked.json()["portal_access_token"]
    anon = TestClient(create_app())
    assert anon.get("/api/v1/bookings").status_code == 401
    assert anon.get(f"/api/v1/guest-portal/{raw}/overview").status_code == 200
    meta = pg_client.get(f"/api/v1/guest-portal/{raw}/overview")
    assert meta.status_code == 200, meta.text
    assert meta.json()["booking_ref"]



def test_postgres_payment_flow(pg_client) -> None:
    """Payment record/overpayment/reversal + check-in on PostgreSQL."""
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    booking_id = _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out)
    # Folio is read-only and non-empty after create (initial charge).
    folio = pg_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    assert folio["total_charges"] == "9000.00"
    # One-night rule uses the stored snapshot (3000.00).
    denied = pg_client.post(f"/api/v1/bookings/{booking_id}/check-in", json={}, headers=headers)
    assert denied.status_code == 422
    # Overpayment beyond the folio: blocked without a reason.
    early = pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "9000.01", "mode": "CASH", "payment_stage": "ADVANCE"},
        headers=headers,
    )
    assert early.status_code == 422, early.text
    pay = pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "3000.00", "mode": "UPI", "payment_stage": "CHECK_IN"},
        headers=headers,
    )
    assert pay.status_code == 201, pay.text
    payment_id = pay.json()["id"]
    # Underpaid check-in: room subtotal is 9000; only one night collected.
    assert (
        pg_client.post(
            f"/api/v1/bookings/{booking_id}/payments",
            json={"amount": "3000.00", "mode": "CARD_POS", "payment_stage": "OTHER"},
            headers=headers,
        ).status_code
        == 201
    )
    assert pg_client.get(f"/api/v1/bookings/{booking_id}/folio").json()["balance_due"] == "3000.00"
    assert (
        pg_client.post(f"/api/v1/bookings/{booking_id}/check-in", json={}, headers=headers).json()[
            "status"
        ]
        == "CHECKED_IN"
    )
    # Duplicate check-in is rejected.
    assert (
        pg_client.post(
            f"/api/v1/bookings/{booking_id}/check-in", json={}, headers=headers
        ).status_code
        == 422
    )
    # ADMIN reversal drives the paid total back down.
    rev = pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments/{payment_id}/reverse",
        json={"reason": "pg test reversal"},
        headers=headers,
    )
    assert rev.status_code == 201, rev.text
    assert rev.json()["is_reversal"] is True
    after = pg_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    assert after["total_paid"] == "3000.00"
    # Duplicate reversal is rejected.
    assert (
        pg_client.post(
            f"/api/v1/bookings/{booking_id}/payments/{payment_id}/reverse",
            json={"reason": "again"},
            headers=headers,
        ).status_code
        == 422
    )


def test_postgres_payment_and_checkin_concurrency(pg_client) -> None:
    """Racing full payments: at most one succeeds (booking-row lock)."""
    import threading
    import uuid as _uuid
    from decimal import Decimal

    from app.billing.service import OverpaymentError, record_payment
    from app.core.db import get_session_factory
    from app.models.booking import Booking
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, actor_id, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    booking_id = _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out)
    booking_uuid = _uuid.UUID(booking_id)
    results: list[str] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        barrier.wait(timeout=10)
        db = get_session_factory()()
        try:
            booking = db.get(Booking, booking_uuid)
            record_payment(
                db,
                booking,
                amount=Decimal("9000.00"),
                mode="CASH",
                payment_stage="CHECK_IN",
                reference_note=None,
                overpayment_reason=None,
                actor_user_id=actor_id,
                actor_role="ADMIN",
            )
            db.commit()
            results.append("ok")
        except OverpaymentError:
            db.rollback()
            results.append("overpay")
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
    assert sorted(results) == ["ok", "overpay"], results


def test_postgres_checkout_and_receipt(pg_client) -> None:
    """Settle, check out, download identical bytes; immutability holds after."""
    import hashlib

    from tests.factories import csrf_headers

    room_id, _rt, guest_id, _actor, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    booking_id = _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out)
    assert pg_client.get(f"/api/v1/bookings/{booking_id}/receipt").status_code == 404
    # Full settlement: 9000 owed; one-night 3000 CHECK_IN + 6000 CHECKOUT.
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "3000.00", "mode": "UPI", "payment_stage": "CHECK_IN"},
        headers=headers,
    )
    blocked = pg_client.post(
        f"/api/v1/bookings/{booking_id}/check-out", json={}, headers=headers
    )
    assert blocked.status_code == 422
    checked = pg_client.post(
        f"/api/v1/bookings/{booking_id}/check-in", json={}, headers=headers
    )
    assert checked.status_code == 200, checked.text
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "6000.00", "mode": "CARD_POS", "payment_stage": "CHECKOUT"},
        headers=headers,
    )
    out = pg_client.post(
        f"/api/v1/bookings/{booking_id}/check-out", json={}, headers=headers
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["status"] == "CHECKED_OUT"
    assert body["balance_due"] == "0.00"
    # Receipt metadata + identical PDF bytes across downloads.
    meta = pg_client.get(f"/api/v1/bookings/{booking_id}/receipt").json()
    assert meta["receipt_ref"] == body["receipt_ref"]
    first = pg_client.get(f"/api/v1/bookings/{booking_id}/receipt/download")
    second = pg_client.get(f"/api/v1/bookings/{booking_id}/receipt/download")
    assert first.status_code == 200
    assert first.headers["content-type"] == "application/pdf"
    assert first.content.startswith(b"%PDF-")
    assert first.content == second.content
    assert hashlib.sha256(first.content).hexdigest() == meta["content_hash"]
    # Post-checkout financial mutations are barred.
    assert pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "1.00", "mode": "CASH", "payment_stage": "OTHER"},
        headers=headers,
    ).status_code == 409


def test_postgres_checkout_concurrency(pg_client) -> None:
    """Two simultaneous checkouts: at most one succeeds (booking-row lock)."""
    import threading
    import uuid as _uuid

    from app.bookings.service import check_out_booking
    from app.core.db import get_session_factory
    from app.models.booking import Booking
    from tests.factories import csrf_headers

    room_id, _rt, guest_id, actor_id, check_in, check_out = _pg_booking_setup(pg_client)
    headers = csrf_headers(pg_client)
    booking_id = _pg_create_booking(pg_client, headers, room_id, guest_id, check_in, check_out)
    booking_uuid = _uuid.UUID(booking_id)
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "3000.00", "mode": "UPI", "payment_stage": "CHECK_IN"},
        headers=headers,
    )
    pg_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "6000.00", "mode": "CASH", "payment_stage": "OTHER"},
        headers=headers,
    )
    checked = pg_client.post(
        f"/api/v1/bookings/{booking_id}/check-in", json={}, headers=headers
    )
    assert checked.status_code == 200, checked.text
    results: list[str] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        barrier.wait(timeout=10)
        db = get_session_factory()()
        try:
            check_out_booking(db, db.get(Booking, booking_uuid), actor_user_id=actor_id)
            db.commit()
            results.append("ok")
        except ValueError:
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
