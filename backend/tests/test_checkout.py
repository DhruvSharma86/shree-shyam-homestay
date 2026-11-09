"""Checkout tests — settlement, lifecycle guards, immutability, concurrency."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.audit import AuditLog
from tests.factories import ADMIN_PASSWORD, create_user, csrf_headers, login


def _today() -> date:
    return datetime.now(UTC).date()


def _new_client(db_session, username: str, role: str):
    """Distinct TestClient per role (separate cookie jars)."""
    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import create_app

    create_user(db_session, username=username, role=role)
    db_session.commit()
    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    login(client, username, ADMIN_PASSWORD)
    return client


@pytest.fixture()
def admin_client(db_session):
    """Logged-in ADMIN client."""
    return _new_client(db_session, "admin1", "ADMIN")


@pytest.fixture()
def receptionist_client(db_session):
    """Logged-in RECEPTIONIST client."""
    return _new_client(db_session, "rec1", "RECEPTIONIST")


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
        json={"full_name": "Checkout Guest", "phone": "+919876543210"},
        headers=csrf_headers(receptionist_client),
    ).json()["id"]


def _setup_rate(admin_client, room_type_id, rate="2500.00"):
    """Ensure a rate covering [tomorrow, +365d) exists."""
    start = _today() + timedelta(days=1)
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


def _booking(
    receptionist_client,
    admin_client,
    room_type_id,
    room_id,
    guest_id,
    nights=3,
    with_rate=True,
    offset=1,
):
    """Create a booking and return its id."""
    if with_rate:
        _setup_rate(admin_client, room_type_id)
    start = _today() + timedelta(days=offset)
    end = start + timedelta(days=nights)
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
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _pay(
    receptionist_client, booking_id, amount, *, stage="OTHER", mode="CASH", reason=None, client=None
):
    payload = {"amount": amount, "mode": mode, "payment_stage": stage}
    if reason is not None:
        payload["overpayment_reason"] = reason
    caller = client or receptionist_client
    return caller.post(
        f"/api/v1/bookings/{booking_id}/payments", json=payload, headers=csrf_headers(caller)
    )


def _checked_in_booking(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, with_rate=True, offset=1
):
    """Booking with one-night CHECK_IN payment applied and checked in."""
    booking_id = _booking(
        receptionist_client,
        admin_client,
        room_type_id,
        room_id,
        guest_id,
        with_rate=with_rate,
        offset=offset,
    )
    _pay(receptionist_client, booking_id, "2500.00", stage="CHECK_IN")
    r = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/check-in",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 200, r.text
    return booking_id


def _checkout(receptionist_client, booking_id):
    return receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/check-out",
        json={},
        headers=csrf_headers(receptionist_client),
    )


def test_zero_balance_checkout(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Successful settlement: status flips, audits land, receipt issued."""
    booking_id = _checked_in_booking(
        receptionist_client, admin_client, room_type_id, room_id, guest_id
    )
    _pay(receptionist_client, booking_id, "5000.00", stage="CHECKOUT", mode="UPI")
    r = _checkout(receptionist_client, booking_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "CHECKED_OUT"
    assert body["total_charges"] == "7500.00"
    assert body["total_paid"] == "7500.00"
    assert body["balance_due"] == "0.00"
    assert body["receipt_ref"].startswith("RCPT-")
    assert len(body["content_hash"]) == 64
    fetched = receptionist_client.get(f"/api/v1/bookings/{booking_id}").json()
    assert fetched["status"] == "CHECKED_OUT"
    actions = {r.action for r in db_session.query(AuditLog)}
    assert {"CHECKOUT_COMPLETED", "RECEIPT_ISSUED"} <= actions


def test_positive_balance_checkout_blocked(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Outstanding balance blocks checkout."""
    booking_id = _checked_in_booking(
        receptionist_client, admin_client, room_type_id, room_id, guest_id
    )
    r = _checkout(receptionist_client, booking_id)
    assert r.status_code == 422
    assert "Outstanding balance" in r.text


def test_negative_balance_checkout_blocked(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Credit balance (authorized overpayment) blocks checkout pending resolution."""
    booking_id = _checked_in_booking(
        receptionist_client, admin_client, room_type_id, room_id, guest_id
    )
    _pay(receptionist_client, booking_id, "5000.00", stage="CHECKOUT", mode="UPI")
    r = _pay(
        receptionist_client,
        booking_id,
        "100.00",
        stage="OTHER",
        reason="goodwill",
        client=admin_client,
    )
    assert r.status_code == 201, r.text
    blocked = _checkout(receptionist_client, booking_id)
    assert blocked.status_code == 422
    assert "Credit balance" in blocked.text


def test_lifecycle_guards(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """CONFIRMED/cancelled/duplicate checkouts are rejected."""
    plain = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    assert _checkout(receptionist_client, plain).status_code == 422
    cancelled = _booking(
        receptionist_client,
        admin_client,
        room_type_id,
        room_id,
        guest_id,
        nights=1,
        with_rate=False,
        offset=10,
    )
    receptionist_client.post(
        f"/api/v1/bookings/{cancelled}/cancel", json={}, headers=csrf_headers(receptionist_client)
    )
    assert _checkout(receptionist_client, cancelled).status_code == 422
    done = _checked_in_booking(
        receptionist_client,
        admin_client,
        room_type_id,
        room_id,
        guest_id,
        with_rate=False,
        offset=20,
    )
    _pay(receptionist_client, done, "5000.00", stage="CHECKOUT")
    assert _checkout(receptionist_client, done).status_code == 200
    assert _checkout(receptionist_client, done).status_code == 422


def test_post_checkout_immutability(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """After checkout every financial/booking mutation is barred (409/422)."""
    booking_id = _checked_in_booking(
        receptionist_client, admin_client, room_type_id, room_id, guest_id
    )
    _pay(receptionist_client, booking_id, "5000.00", stage="CHECKOUT")
    assert _checkout(receptionist_client, booking_id).status_code == 200
    base = f"/api/v1/bookings/{booking_id}"
    charge = receptionist_client.post(
        f"{base}/folio/charges",
        json={"description": "late", "quantity": "1", "unit_amount": "100.00"},
        headers=csrf_headers(receptionist_client),
    )
    assert charge.status_code == 409
    discount = admin_client.post(
        f"{base}/folio/discounts",
        json={"amount": "1.00", "reason": "late"},
        headers=csrf_headers(admin_client),
    )
    assert discount.status_code == 409
    pay = _pay(receptionist_client, booking_id, "1.00")
    assert pay.status_code == 409
    patch = receptionist_client.patch(
        f"{base}", json={"check_out_date": "2099-01-01"}, headers=csrf_headers(receptionist_client)
    )
    assert patch.status_code == 422
    checkin = receptionist_client.post(
        f"{base}/check-in", json={}, headers=csrf_headers(receptionist_client)
    )
    assert checkin.status_code in (409, 422)
    folio = admin_client.get(f"{base}/folio").json()
    assert folio["booking_status"] == "CHECKED_OUT"


def test_checkout_audit_no_pii(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Checkout/receipt audits carry ids and totals — no guest PII."""
    booking_id = _checked_in_booking(
        receptionist_client, admin_client, room_type_id, room_id, guest_id
    )
    _pay(receptionist_client, booking_id, "5000.00", stage="CHECKOUT")
    _checkout(receptionist_client, booking_id)
    rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.action.in_(["CHECKOUT_COMPLETED", "RECEIPT_ISSUED"]))
        .all()
    )
    assert len(rows) == 2
    blob = " ".join(str(r.metadata_json or "") for r in rows)
    assert "Checkout Guest" not in blob
    assert "9876543210" not in blob
