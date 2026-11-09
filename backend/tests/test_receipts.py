"""Receipt tests — PDF validity, totals, persistence, authorization."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.billing.receipts import get_final_receipt
from app.models.audit import AuditLog
from tests.factories import ADMIN_PASSWORD, create_user, csrf_headers, login


def _today():
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
        json={"full_name": "Receipt Guest", "phone": "+919876543210"},
        headers=csrf_headers(receptionist_client),
    ).json()["id"]


def _settled_booking(receptionist_client, admin_client, room_type_id, room_id, guest_id):
    """Settle a booking (check-in, full payment, checkout) and return its id."""
    start = _today() + timedelta(days=1)
    end = start + timedelta(days=3)
    admin_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": "2500.00",
            "valid_from": start.isoformat(),
            "valid_until": (start + timedelta(days=365)).isoformat(),
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
    assert r.status_code == 201, r.text
    booking_id = r.json()["id"]
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "2500.00", "mode": "CASH", "payment_stage": "CHECK_IN"},
        headers=csrf_headers(receptionist_client),
    )
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/check-in",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "5000.00", "mode": "UPI", "payment_stage": "CHECKOUT"},
        headers=csrf_headers(receptionist_client),
    )
    out = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/check-out",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    assert out.status_code == 200, out.text
    return booking_id


def test_pdf_download_is_valid_and_stable(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Download returns identical PDF bytes with a verifiable content hash."""
    booking_id = _settled_booking(
        receptionist_client, admin_client, room_type_id, room_id, guest_id
    )
    meta = receptionist_client.get(f"/api/v1/bookings/{booking_id}/receipt")
    assert meta.status_code == 200, meta.text
    pdf = receptionist_client.get(f"/api/v1/bookings/{booking_id}/receipt/download")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert "attachment" in pdf.headers["content-disposition"]
    assert meta.json()["receipt_ref"] in pdf.headers["content-disposition"]
    content = pdf.content
    assert content.startswith(b"%PDF-")
    assert len(content) > 0
    # Hash proof: bytes on disk hash to the issued content_hash.
    receipt = get_final_receipt(db_session, uuid.UUID(booking_id))
    assert receipt is not None
    assert hashlib.sha256(bytes(receipt.pdf_content)).hexdigest() == receipt.content_hash
    assert hashlib.sha256(content).hexdigest() == meta.json()["content_hash"]
    # Repeated downloads return the same bytes (immutability).
    again = receptionist_client.get(f"/api/v1/bookings/{booking_id}/receipt/download")
    assert again.content == content
    audits = db_session.query(AuditLog).filter(AuditLog.action == "RECEIPT_DOWNLOADED").count()
    assert audits >= 2


def test_receipt_requires_check_out(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """No receipt metadata/download before checkout (404)."""
    start = _today() + timedelta(days=1)
    end = start + timedelta(days=1)
    admin_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": "2500.00",
            "valid_from": start.isoformat(),
            "valid_until": (start + timedelta(days=365)).isoformat(),
        },
        headers=csrf_headers(admin_client),
    )
    booking_id = receptionist_client.post(
        "/api/v1/bookings",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "source": "WALK_IN",
            "check_in_date": start.isoformat(),
            "check_out_date": end.isoformat(),
        },
        headers=csrf_headers(receptionist_client),
    ).json()["id"]
    assert receptionist_client.get(f"/api/v1/bookings/{booking_id}/receipt").status_code == 404
    assert (
        receptionist_client.get(f"/api/v1/bookings/{booking_id}/receipt/download").status_code
        == 404
    )


def test_receipt_download_requires_auth(
    client, receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Unauthenticated download → 401 (no public links)."""
    booking_id = _settled_booking(
        receptionist_client, admin_client, room_type_id, room_id, guest_id
    )
    anon = client.get(f"/api/v1/bookings/{booking_id}/receipt/download")
    assert anon.status_code == 401


def test_receipt_long_guest_name(admin_client, room_type_id, room_id, db_session) -> None:
    """A long primary-guest name renders without errors."""
    long_name = "A Very Long Frequent Traveller Name " * 3  # near the 160-char limit
    long_guest_id = admin_client.post(
        "/api/v1/guests",
        json={"full_name": long_name.strip(), "phone": "+919800000001"},
        headers=csrf_headers(admin_client),
    ).json()["id"]
    receptionist = _new_client(db_session, "recxx", "RECEPTIONIST")
    booking_id = _settled_booking(receptionist, admin_client, room_type_id, room_id, long_guest_id)
    pdf = receptionist.get(f"/api/v1/bookings/{booking_id}/receipt/download")
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-")
    assert len(pdf.content) > 0
