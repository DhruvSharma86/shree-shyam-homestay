"""Booking tests — CRUD, availability, snapshots, RBAC, audit, concurrency."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from tests.factories import ADMIN_PASSWORD, create_user, csrf_headers, login


def _today() -> date:
    return datetime.now(UTC).date()


@pytest.fixture()
def admin_client(client, db_session):
    """Logged-in ADMIN client."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)
    return client


@pytest.fixture()
def receptionist_client(client, db_session):
    """Logged-in RECEPTIONIST client."""
    create_user(db_session, username="rec1", role="RECEPTIONIST")
    db_session.commit()
    login(client, "rec1", ADMIN_PASSWORD)
    return client


@pytest.fixture()
def room_type_id(admin_client) -> str:
    """Create a category and return its id."""
    return admin_client.post(
        "/api/v1/admin/room-types", json={"name": "Deluxe"}, headers=csrf_headers(admin_client)
    ).json()["id"]


@pytest.fixture()
def room_id(admin_client, room_type_id) -> str:
    """Create a room and return its id."""
    return admin_client.post(
        "/api/v1/admin/rooms",
        json={"room_number": "101", "room_type_id": room_type_id},
        headers=csrf_headers(admin_client),
    ).json()["id"]


@pytest.fixture()
def guest_id(receptionist_client) -> str:
    """Register a guest and return its id."""
    return receptionist_client.post(
        "/api/v1/guests",
        json={"full_name": "Test Guest", "phone": "+919876543210"},
        headers=csrf_headers(receptionist_client),
    ).json()["id"]


def _setup_rate(admin_client, room_type_id, rate="2500.00", valid_from=None):
    """Ensure a rate covering [tomorrow, +365d) exists."""
    start = valid_from or (_today() + timedelta(days=1))
    end = start + timedelta(days=365)
    return admin_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": rate,
            "valid_from": start.isoformat(),
            "valid_until": end.isoformat(),
        },
        headers=csrf_headers(admin_client),
    )


def _dates(nights=3, offset=1):
    start = _today() + timedelta(days=offset)
    return start, start + timedelta(days=nights)


def _booking_payload(guest_id, room_id, nights=3, offset=1):
    start, end = _dates(nights, offset)
    return {
        "guest_id": guest_id,
        "room_id": room_id,
        "source": "PHONE",
        "check_in_date": start.isoformat(),
        "check_out_date": end.isoformat(),
        "number_of_guests": 2,
    }


# --- Create / retrieve / list ------------------------------------------------


def test_create_booking_success(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Successful creation snapshots rate × nights and returns 201."""
    _setup_rate(admin_client, room_type_id)
    r = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "CONFIRMED"
    assert body["nights"] == 3
    assert Decimal(body["room_subtotal"]) == Decimal("2500.00") * Decimal("3")
    assert Decimal(body["total_amount"]) == Decimal("7500.00")
    assert body["tax_type_snapshot"] == "NONE"
    assert body["booking_ref"].startswith("SSH-")


def test_create_invalid_guest_404_and_422(
    receptionist_client, admin_client, room_type_id, room_id
) -> None:
    """Unknown guest → 422 (guest inactive/missing)."""
    _setup_rate(admin_client, room_type_id)
    r = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload("00000000-0000-0000-0000-000000000000", room_id),
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 422


def test_create_invalid_room_422(receptionist_client, admin_client, room_type_id, guest_id) -> None:
    """Unknown room → 422."""
    _setup_rate(admin_client, room_type_id)
    r = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, "00000000-0000-0000-0000-000000000000"),
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 422


def test_create_invalid_dates(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """check_out <= check_in, and past check-in → 422."""
    _setup_rate(admin_client, room_type_id)
    start, _ = _dates(0)
    payload = _booking_payload(guest_id, room_id)
    payload["check_in_date"] = start.isoformat()
    payload["check_out_date"] = start.isoformat()
    assert (
        receptionist_client.post(
            "/api/v1/bookings", json=payload, headers=csrf_headers(receptionist_client)
        ).status_code
        == 422
    )
    payload["check_in_date"] = (_today() - timedelta(days=2)).isoformat()
    payload["check_out_date"] = (_today() - timedelta(days=1)).isoformat()
    assert (
        receptionist_client.post(
            "/api/v1/bookings", json=payload, headers=csrf_headers(receptionist_client)
        ).status_code
        == 422
    )


def test_get_and_list_and_filters(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Retrieve + list with status/guest/room filters and pagination."""
    _setup_rate(admin_client, room_type_id)
    created = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    ).json()
    one = receptionist_client.get(f"/api/v1/bookings/{created['id']}")
    assert one.status_code == 200 and one.json()["id"] == created["id"]
    listed = receptionist_client.get("/api/v1/bookings?status=CONFIRMED")
    assert listed.json()["total"] == 1
    by_guest = receptionist_client.get(f"/api/v1/bookings?guest_id={guest_id}")
    assert by_guest.json()["total"] == 1
    by_room = receptionist_client.get(f"/api/v1/bookings?room_id={room_id}")
    assert by_room.json()["total"] == 1
    miss = receptionist_client.get("/api/v1/bookings/00000000-0000-0000-0000-000000000000")
    assert miss.status_code == 404


# --- Availability / overlap --------------------------------------------------


def test_overlap_rejected_and_boundary_allowed(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Overlapping request → 409; checkout-day boundary → 201."""
    _setup_rate(admin_client, room_type_id)
    start, end = _dates(3, 1)
    receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    )
    overlap = _booking_payload(guest_id, room_id)
    overlap["check_in_date"] = (start + timedelta(days=1)).isoformat()
    overlap["check_out_date"] = (end + timedelta(days=1)).isoformat()
    r = receptionist_client.post(
        "/api/v1/bookings", json=overlap, headers=csrf_headers(receptionist_client)
    )
    assert r.status_code == 409
    boundary = _booking_payload(guest_id, room_id)
    boundary["check_in_date"] = end.isoformat()
    boundary["check_out_date"] = (end + timedelta(days=2)).isoformat()
    r2 = receptionist_client.post(
        "/api/v1/bookings", json=boundary, headers=csrf_headers(receptionist_client)
    )
    assert r2.status_code == 201, r2.text


def test_availability_endpoint(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """GET /availability reports unavailable for booked dates."""
    _setup_rate(admin_client, room_type_id)
    start, end = _dates(2, 1)
    receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id, 2),
        headers=csrf_headers(receptionist_client),
    )
    busy = receptionist_client.get(
        f"/api/v1/bookings/availability/{room_id}?check_in={start.isoformat()}&check_out={end.isoformat()}"
    )
    assert busy.json()["available"] is False
    nxt = end + timedelta(days=1)
    free = receptionist_client.get(
        f"/api/v1/bookings/availability/{room_id}"
        f"?check_in={end.isoformat()}&check_out={nxt.isoformat()}"
    )
    assert free.json()["available"] is True


def test_maintenance_room_rejected(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """MAINTENANCE rooms cannot be booked."""
    _setup_rate(admin_client, room_type_id)
    room = admin_client.get(f"/api/v1/admin/rooms/{room_id}").json()
    assert room["operational_status"] == "AVAILABLE"
    admin_client.patch(
        f"/api/v1/admin/rooms/{room_id}",
        json={"operational_status": "MAINTENANCE"},
        headers=csrf_headers(admin_client),
    )
    r = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 422


def test_no_rate_covers_stay_422(receptionist_client, room_type_id, room_id, guest_id) -> None:
    """No rate configured → 422 (prices never invented)."""
    r = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 422


def test_mid_stay_rate_change_rejected(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """A rate starting mid-stay → 422 until validity is adjusted."""
    start, end = _dates(5, 1)
    mid = start + timedelta(days=2)
    admin_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": "2000.00",
            "valid_from": start.isoformat(),
            "valid_until": mid.isoformat(),
        },
        headers=csrf_headers(admin_client),
    )
    admin_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": "3000.00",
            "valid_from": (mid + timedelta(days=1)).isoformat(),
        },
        headers=csrf_headers(admin_client),
    )
    r = receptionist_client.post(
        "/api/v1/bookings",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "source": "PHONE",
            "check_in_date": start.isoformat(),
            "check_out_date": end.isoformat(),
        },
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 422


def test_rate_change_does_not_mutate_snapshot(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Later rate versions never rewrite an existing booking's snapshot."""
    _setup_rate(admin_client, room_type_id, rate="2500.00")
    created = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    ).json()
    # Later price change (non-overlapping future period).
    later = _today() + timedelta(days=400)
    admin_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": "9999.00",
            "valid_from": later.isoformat(),
        },
        headers=csrf_headers(admin_client),
    )
    fetched = receptionist_client.get(f"/api/v1/bookings/{created['id']}").json()
    assert fetched["night_rate_snapshot"] == "2500.00"
    assert fetched["room_subtotal"] == "7500.00"


# --- Update / cancel ---------------------------------------------------------


def test_update_booking_dates_recaculates(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Extending the stay recomputes nights and subtotal."""
    _setup_rate(admin_client, room_type_id)
    created = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id, 3),
        headers=csrf_headers(receptionist_client),
    ).json()
    start, end = _dates(3, 1)
    r = receptionist_client.patch(
        f"/api/v1/bookings/{created['id']}",
        json={"check_out_date": (end + timedelta(days=2)).isoformat()},
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["nights"] == 5
    assert r.json()["room_subtotal"] == "12500.00"


def test_cancelled_booking_blocks_no_availability(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Cancel releases dates; repeated cancel is idempotent."""
    _setup_rate(admin_client, room_type_id)
    start, end = _dates(2, 1)
    created = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id, 2),
        headers=csrf_headers(receptionist_client),
    ).json()
    cancelled = receptionist_client.post(
        f"/api/v1/bookings/{created['id']}/cancel",
        json={"reason": "guest called"},
        headers=csrf_headers(receptionist_client),
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    again = receptionist_client.post(
        f"/api/v1/bookings/{created['id']}/cancel",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    assert again.status_code == 200
    avail = receptionist_client.get(
        f"/api/v1/bookings/availability/{room_id}?check_in={start.isoformat()}&check_out={end.isoformat()}"
    )
    assert avail.json()["available"] is True
    rebooked = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id, 2),
        headers=csrf_headers(receptionist_client),
    )
    assert rebooked.status_code == 201


def test_cancelled_booking_cannot_be_modified(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """PATCH on a cancelled booking → 422."""
    _setup_rate(admin_client, room_type_id)
    created = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    ).json()
    receptionist_client.post(
        f"/api/v1/bookings/{created['id']}/cancel",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    r = receptionist_client.patch(
        f"/api/v1/bookings/{created['id']}",
        json={"number_of_guests": 1},
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 422


def test_deactivated_guest_cannot_book(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Deactivated guest → 422 (must be reactivated, never silently reused)."""
    _setup_rate(admin_client, room_type_id)
    receptionist_client.post(
        f"/api/v1/guests/{guest_id}/deactivate", headers=csrf_headers(receptionist_client)
    )
    r = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 422


# --- Authorization & audit ---------------------------------------------------


def test_unauthenticated_bookings(client) -> None:
    """No session → 401."""
    assert client.get("/api/v1/bookings").status_code == 401
    assert client.post("/api/v1/bookings", json={}).status_code == 401


def test_receptionist_and_admin_both_can_book(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Both roles can create bookings."""
    _setup_rate(admin_client, room_type_id)
    r1 = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id, 1, 1),
        headers=csrf_headers(receptionist_client),
    )
    assert r1.status_code == 201
    r2 = admin_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id, 1, 5),
        headers=csrf_headers(admin_client),
    )
    assert r2.status_code == 201


def test_booking_csrf_required(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Mutations without CSRF → 403."""
    _setup_rate(admin_client, room_type_id)
    r = receptionist_client.post("/api/v1/bookings", json=_booking_payload(guest_id, room_id))
    assert r.status_code == 403


def test_booking_audit_without_pii(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Create/update/cancel write audit rows with no guest PII."""
    _setup_rate(admin_client, room_type_id)
    created = receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    ).json()
    receptionist_client.patch(
        f"/api/v1/bookings/{created['id']}",
        json={"number_of_guests": 1},
        headers=csrf_headers(receptionist_client),
    )
    receptionist_client.post(
        f"/api/v1/bookings/{created['id']}/cancel",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    rows = db_session.scalars(select(AuditLog).where(AuditLog.action.like("BOOKING_%"))).all()
    actions = {r.action for r in rows}
    assert {"BOOKING_CREATED", "BOOKING_UPDATED", "BOOKING_CANCELLED"} <= actions
    blob = " ".join(str(r.metadata_json or "") for r in rows)
    assert "Test Guest" not in blob
    assert "9876543210" not in blob


def test_concurrent_duplicate_db_guard(
    db_session, receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Second overlapping insert is blocked: PG exclusion (verified in CI)."""
    _setup_rate(admin_client, room_type_id)
    receptionist_client.post(
        "/api/v1/bookings",
        json=_booking_payload(guest_id, room_id),
        headers=csrf_headers(receptionist_client),
    )
    start, end = _dates(3, 1)
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.core.db import get_engine

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        pytest.skip("Exclusion constraint is PostgreSQL-only; service lock guards SQLite.")
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO bookings (id, booking_ref, guest_id, room_id,"
                    " room_type_id, status, source, check_in_date, check_out_date,"
                    " nights, number_of_guests, night_rate_snapshot, room_subtotal,"
                    " total_amount, tax_pricing_mode_snapshot, tax_type_snapshot,"
                    " created_at, updated_at)"
                    " VALUES (gen_random_uuid(), 'SSH-999999', :g, :r, :t,"
                    " 'CONFIRMED', 'PHONE', :ci, :co, 3, 1, 2500.00, 7500.00,"
                    " 7500.00, 'EXCLUSIVE', 'NONE', now(), now())"
                ),
                {
                    "g": guest_id,
                    "r": room_id,
                    "t": room_type_id,
                    "ci": start.isoformat(),
                    "co": end.isoformat(),
                },
            )
