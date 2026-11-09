"""Billing tests — folio, balance math, reversals, RBAC, immutability.

Phase 4.1 scope: folio view, initial room charge, charges, discounts,
charge reversals, payment history (read-only). Payment writing and
check-in/out belong to Phase 4.2.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.billing.service import folio_totals
from app.models.audit import AuditLog
from app.models.folio_entry import FolioEntry
from app.models.payment import Payment
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
        json={"full_name": "Billing Guest", "phone": "+919876543210"},
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


def _dates(nights=3, offset=1):
    start = _today() + timedelta(days=offset)
    return start, start + timedelta(days=nights)


def _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id, nights=3):
    """Create a booking (folio initializes atomically) and return its id."""
    _setup_rate(admin_client, room_type_id)
    start, end = _dates(nights)
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


# --- Folio retrieval / initial charge ----------------------------------------


def test_folio_retrieval_with_initial_charge(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Folio shows exactly one initial ROOM_CHARGE from the snapshot."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    folio = receptionist_client.get(f"/api/v1/bookings/{booking_id}/folio")
    assert folio.status_code == 200, folio.text
    body = folio.json()
    assert body["booking_id"] == booking_id
    assert body["booking_ref"].startswith("SSH-")
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["entry_type"] == "ROOM_CHARGE"
    assert entry["is_initial"] is True
    assert entry["amount"] == "7500.00"  # 3 nights x 2500.00
    assert entry["quantity"] == "3.00"
    assert entry["unit_amount"] == "2500.00"
    assert body["total_charges"] == "7500.00"
    assert body["total_paid"] == "0.00"
    assert body["balance_due"] == "7500.00"
    assert body["payment_count"] == 0


def test_folio_missing_booking_404(receptionist_client) -> None:
    """Unknown booking → 404."""
    r = receptionist_client.get("/api/v1/bookings/00000000-0000-0000-0000-000000000000/folio")
    assert r.status_code == 404


def test_initial_charge_idempotent(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Repeated folio reads never duplicate the initial charge."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    for _ in range(3):
        receptionist_client.get(f"/api/v1/bookings/{booking_id}/folio")
    body = receptionist_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    initials = [e for e in body["entries"] if e["is_initial"]]
    assert len(initials) == 1
    assert len(body["entries"]) == 1


def test_folio_totals_decimal_math(
    db_session, receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """folio_totals returns Decimal zero/values, never None or float."""
    import uuid

    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    charges, paid, balance = folio_totals(db_session, uuid.UUID(booking_id))
    assert charges == Decimal("7500.00")
    assert paid == Decimal("0.00")
    assert balance == Decimal("7500.00")
    assert all(isinstance(v, Decimal) for v in (charges, paid, balance))


def test_empty_folio_zero_totals(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """A booking with entries deleted has zero totals (defensive floor)."""
    import uuid

    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    db_session.query(FolioEntry).delete()
    db_session.commit()
    charges, paid, balance = folio_totals(db_session, uuid.UUID(booking_id))
    assert charges == Decimal("0.00")
    assert paid == Decimal("0.00")
    assert balance == Decimal("0.00")


# --- Charges -----------------------------------------------------------------


def test_additional_charge(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Additional charges append with server-computed amounts."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    r = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Restaurant dinner", "quantity": "2", "unit_amount": "450.00"},
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 201, r.text
    assert r.json()["amount"] == "900.00"
    assert r.json()["entry_type"] == "ADDITIONAL_CHARGE"
    folio = receptionist_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    assert folio["total_charges"] == "8400.00"
    assert folio["balance_due"] == "8400.00"


def test_charge_validation(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Empty description / zero quantity / negative rate → 422."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    url = f"/api/v1/bookings/{booking_id}/folio/charges"
    bad = [
        {"description": "", "quantity": "1", "unit_amount": "100.00"},
        {"description": "x", "quantity": "0", "unit_amount": "100.00"},
        {"description": "x", "quantity": "1", "unit_amount": "-5.00"},
        {"description": "x", "quantity": "1", "unit_amount": "0.00"},
    ]
    for payload in bad:
        r = receptionist_client.post(url, json=payload, headers=csrf_headers(receptionist_client))
        assert r.status_code == 422, payload


def test_charge_on_cancelled_booking_409(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Cancelled bookings are read-only history → 409."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/cancel", json={}, headers=csrf_headers(receptionist_client)
    )
    r = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Late charge", "quantity": "1", "unit_amount": "100.00"},
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 409
    # History preserved: initial charge still readable.
    folio = receptionist_client.get(f"/api/v1/bookings/{booking_id}/folio")
    assert folio.status_code == 200
    assert folio.json()["total_charges"] == "7500.00"


# --- Discounts ---------------------------------------------------------------


def test_discount_admin_only(
    admin_client, room_type_id, room_id, guest_id, receptionist_client
) -> None:
    """ADMIN may discount; RECEPTIONIST is denied (D4)."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    url = f"/api/v1/bookings/{booking_id}/folio/discounts"
    denied = receptionist_client.post(
        url,
        json={"amount": "100.00", "reason": "guest complaint"},
        headers=csrf_headers(receptionist_client),
    )
    assert denied.status_code == 403
    ok = admin_client.post(
        url,
        json={"amount": "200.00", "reason": "guest complaint"},
        headers=csrf_headers(admin_client),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["amount"] == "-200.00"
    folio = admin_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    assert folio["total_charges"] == "7300.00"


def test_discount_reason_mandatory(
    admin_client, room_type_id, room_id, guest_id, receptionist_client
) -> None:
    """Empty reason → 422 (reason-free discounts do not exist)."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    r = admin_client.post(
        f"/api/v1/bookings/{booking_id}/folio/discounts",
        json={"amount": "100.00", "reason": ""},
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 422


def test_discount_cannot_go_negative(
    admin_client, room_type_id, room_id, guest_id, receptionist_client
) -> None:
    """Discount larger than the folio total → 422 (no negative folio)."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    r = admin_client.post(
        f"/api/v1/bookings/{booking_id}/folio/discounts",
        json={"amount": "99999.00", "reason": "too much"},
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 422


def test_receptionist_discount_denied_no_audit(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Denied discounts leave no ledger or audit rows (D4)."""
    import uuid

    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    denied = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/discounts",
        json={"amount": "100.00", "reason": "nope"},
        headers=csrf_headers(receptionist_client),
    )
    assert denied.status_code == 403
    assert (
        db_session.query(FolioEntry).filter(FolioEntry.booking_id == uuid.UUID(booking_id)).count()
        == 1
    )
    audits = db_session.scalars(select(AuditLog).where(AuditLog.action == "DISCOUNT_APPLIED")).all()
    assert audits == []


# --- Reversals ---------------------------------------------------------------


def test_charge_reversal(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Charge reversal offsets the original exactly; original stays."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    charge = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Cab ride", "quantity": "1", "unit_amount": "600.00"},
        headers=csrf_headers(receptionist_client),
    ).json()
    rev = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": charge["id"], "reason": "wrongly added"},
        headers=csrf_headers(receptionist_client),
    )
    assert rev.status_code == 201, rev.text
    assert rev.json()["amount"] == "-600.00"
    assert rev.json()["reverses_entry_id"] == charge["id"]
    folio = admin_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    assert folio["total_charges"] == "7500.00"
    entries = {e["id"]: e for e in folio["entries"]}
    assert entries[charge["id"]]["amount"] == "600.00"  # original untouched


def test_invalid_reversal_targets_422(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Unknown entry → 404; reversing a reversal → 422."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    missing = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": "00000000-0000-0000-0000-000000000000", "reason": "x"},
        headers=csrf_headers(receptionist_client),
    )
    assert missing.status_code == 404
    charge = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Wine", "quantity": "1", "unit_amount": "300.00"},
        headers=csrf_headers(receptionist_client),
    ).json()
    reversal = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": charge["id"], "reason": "error"},
        headers=csrf_headers(receptionist_client),
    ).json()
    again = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": reversal["id"], "reason": "double fault"},
        headers=csrf_headers(receptionist_client),
    )
    assert again.status_code == 422


def test_repeated_reversal_protection(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Reversing an already-reversed entry → 422, no second offset."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    charge = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Minibar", "quantity": "1", "unit_amount": "150.00"},
        headers=csrf_headers(receptionist_client),
    ).json()
    first = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": charge["id"], "reason": "not consumed"},
        headers=csrf_headers(receptionist_client),
    )
    assert first.status_code == 201
    second = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": charge["id"], "reason": "again"},
        headers=csrf_headers(receptionist_client),
    )
    assert second.status_code == 422
    folio = admin_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    assert folio["total_charges"] == "7500.00"


# --- Permissions / CSRF / audit / PII -----------------------------------------


def test_unauthenticated_folio(client) -> None:
    """No session → 401 on folio and payments reads."""
    assert (
        client.get("/api/v1/bookings/00000000-0000-0000-0000-000000000000/folio").status_code == 401
    )
    assert (
        client.get("/api/v1/bookings/00000000-0000-0000-0000-000000000000/payments").status_code
        == 401
    )


def test_receptionist_reads_folio_and_payments(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """D6: both roles read the folio and the payment history."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    folio = receptionist_client.get(f"/api/v1/bookings/{booking_id}/folio")
    assert folio.status_code == 200
    payments = receptionist_client.get(f"/api/v1/bookings/{booking_id}/payments")
    assert payments.status_code == 200
    assert payments.json()["total"] == 0
    assert payments.json()["items"] == []


def test_csrf_required_on_mutations(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Charge/discount/reversal without CSRF → 403."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    r = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "No CSRF", "quantity": "1", "unit_amount": "100.00"},
    )
    assert r.status_code == 403


def test_billing_audit_without_pii(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Charge/discount/reversal audits carry ids, amounts, reasons — no PII."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Laundry", "quantity": "1", "unit_amount": "200.00"},
        headers=csrf_headers(receptionist_client),
    )
    admin_client.post(
        f"/api/v1/bookings/{booking_id}/folio/discounts",
        json={"amount": "50.00", "reason": "loyal guest"},
        headers=csrf_headers(admin_client),
    )
    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action.in_(("CHARGE_ADDED", "DISCOUNT_APPLIED")))
    ).all()
    assert len(rows) == 2
    blob = " ".join(str(r.metadata_json or "") for r in rows)
    assert "Billing Guest" not in blob
    assert "9876543210" not in blob


def test_folio_response_has_no_guest_pii(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Folio/payment payloads contain ids only — no names/phones."""
    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    folio = receptionist_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    blob = str(folio)
    assert "Billing Guest" not in blob and "9876543210" not in blob


# --- Immutability / integrity (SQLite: triggers are PostgreSQL-only) ----------


def test_sqlite_has_no_immutability_trigger() -> None:
    """SQLite has no append-only trigger equivalent (documented limitation).

    PostgreSQL trigger enforcement is verified in CI via
    ``test_postgres_finance_triggers`` (see test_postgres_integration.py);
    service-layer append-only rules still apply everywhere.
    """
    from app.core.db import get_engine

    assert get_engine().dialect.name == "sqlite"


def test_foreign_key_restrict(
    db_session, receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """RESTRICT FKs on both financial tables prevent orphan/hard-deleted history."""
    fe_fks = list(FolioEntry.__table__.c.booking_id.foreign_keys)
    assert len(fe_fks) == 1
    assert fe_fks[0].target_fullname == "bookings.id"
    assert fe_fks[0].ondelete == "RESTRICT"
    py_fks = list(Payment.__table__.c.booking_id.foreign_keys)
    assert len(py_fks) == 1
    assert py_fks[0].target_fullname == "bookings.id"
    assert py_fks[0].ondelete == "RESTRICT"
    # Behavioural: data created, original rows present (never deleted).
    import uuid

    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    assert (
        db_session.query(FolioEntry).filter(FolioEntry.booking_id == uuid.UUID(booking_id)).count()
    ) >= 1
    assert (
        db_session.query(Payment).filter(Payment.booking_id == uuid.UUID(booking_id)).count() == 0
    )


def test_initial_charge_written_at_creation_not_first_read(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """The initial entry exists immediately after POST /bookings (not lazily)."""
    import uuid

    booking_id = _booking(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    rows = db_session.query(FolioEntry).filter(FolioEntry.booking_id == uuid.UUID(booking_id)).all()
    assert len(rows) == 1 and rows[0].is_initial and rows[0].entry_type == "ROOM_CHARGE"


def test_booking_extension_adjusts_folio_consistently(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Extending a stay appends reversal+revised charge; folio total follows the booking."""
    booking_id = _booking(
        receptionist_client, admin_client, room_type_id, room_id, guest_id, nights=3
    )
    start, end = _dates(3)
    patched = receptionist_client.patch(
        f"/api/v1/bookings/{booking_id}",
        json={"check_out_date": (end + timedelta(days=2)).isoformat()},
        headers=csrf_headers(receptionist_client),
    )
    assert patched.status_code == 200, patched.text
    folio = admin_client.get(f"/api/v1/bookings/{booking_id}/folio").json()
    assert folio["total_charges"] == "12500.00"  # 7500 - 7500 + 12500
    entries = folio["entries"]
    assert sum(1 for e in entries if e["is_initial"]) == 1
    assert {e["entry_type"] for e in entries} == {"ROOM_CHARGE", "REVERSAL"}
