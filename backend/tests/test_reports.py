"""Reporting tests — read-only financial checks, occupancy, reconciliation, exports."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

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
        json={"full_name": "Report Guest", "phone": "+919876543210"},
        headers=csrf_headers(receptionist_client),
    ).json()["id"]


def _book(
    receptionist_client,
    admin_client,
    room_type_id,
    room_id,
    guest_id,
    nights=3,
    with_rate=True,
    offset=1,
):
    """Create a booking (folio initializes) and return its id."""
    start = _today() + timedelta(days=offset)
    end = start + timedelta(days=nights)
    if with_rate:
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
    return r.json()["id"]


def _pay(receptionist_client, booking_id, amount, *, stage="OTHER", mode="CASH", client=None):
    caller = client or receptionist_client
    return caller.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": amount, "mode": mode, "payment_stage": stage},
        headers=csrf_headers(caller),
    )


def _today_str() -> str:
    return _today().isoformat()


# --- Financial summary ---------------------------------------------------------


def test_summary_empty(admin_client) -> None:
    """Empty dataset returns zeros (Decimal-safe)."""
    r = admin_client.get("/api/v1/reports/financial/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["room_charges"] == "0.00"
    assert body["net_payments"] == "0.00"
    assert body["outstanding"] == "0.00"


def test_summary_breakdown(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Room/additional/discount/reversal/new lines are separated and exact."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Food", "quantity": "1", "unit_amount": "500.00"},
        headers=csrf_headers(receptionist_client),
    )
    admin_client.post(
        f"/api/v1/bookings/{booking_id}/folio/discounts",
        json={"amount": "100.00", "reason": "guest complaint"},
        headers=csrf_headers(admin_client),
    )
    _pay(receptionist_client, booking_id, "7900.00")  # full settlement: 7500+500-100
    today = _today_str()
    body = admin_client.get(
        f"/api/v1/reports/financial/summary?from_date={today}&to_date={today}"
    ).json()
    assert body["room_charges"] == "7500.00"
    assert body["additional_charges"] == "500.00"
    assert body["discounts"] == "-100.00"
    assert body["gross_charges"] == "8000.00"
    assert body["net_payments"] == "7900.00"
    assert body["outstanding"] == "0.00"


def test_summary_partial_and_reversals(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Partial payments, charge reversals and payment reversals net correctly."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    charge = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Cab", "quantity": "1", "unit_amount": "600.00"},
        headers=csrf_headers(receptionist_client),
    ).json()
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": charge["id"], "reason": "wrong"},
        headers=csrf_headers(receptionist_client),
    )
    payment = _pay(receptionist_client, booking_id, "3000.00").json()
    admin_client.post(
        f"/api/v1/bookings/{booking_id}/payments/{payment['id']}/reverse",
        json={"reason": "mistake"},
        headers=csrf_headers(admin_client),
    )
    today = _today_str()
    body = admin_client.get(
        f"/api/v1/reports/financial/summary?from_date={today}&to_date={today}"
    ).json()
    assert body["charge_reversals"] == "-600.00"  # signed REVERSAL entry amount
    assert body["net_payments"] == "0.00"
    assert body["outstanding"] == "7500.00"


def test_summary_date_boundaries(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Yesterday's records are excluded from today's window."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    _pay(receptionist_client, booking_id, "1000.00")
    yesterday = (_today() - timedelta(days=1)).isoformat()
    empty = admin_client.get(
        f"/api/v1/reports/financial/summary?from_date={yesterday}&to_date={yesterday}"
    )
    assert empty.json()["net_payments"] == "0.00"
    today = _today_str()
    full = admin_client.get(f"/api/v1/reports/financial/summary?from_date={today}&to_date={today}")
    assert full.json()["net_payments"] == "1000.00"
    bad = admin_client.get(
        f"/api/v1/reports/financial/summary?from_date={today}&to_date={yesterday}"
    )
    assert bad.status_code == 422


# --- Collections / methods -----------------------------------------------------


def test_collections_rows(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Collections rows separate methods/stages; reversals become credits."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    _pay(receptionist_client, booking_id, "2000.00", stage="CHECK_IN", mode="UPI")
    _pay(receptionist_client, booking_id, "1000.00", stage="OTHER", mode="CASH")
    today = _today_str()
    body = admin_client.get(
        f"/api/v1/reports/financial/collections?from_date={today}&to_date={today}"
    ).json()
    assert body["original_total"] == "3000.00"
    assert body["reversal_total"] == "0.00"
    assert body["net_total"] == "3000.00"
    keys = {(r["method"], r["stage"]) for r in body["rows"]}
    assert ("UPI", "CHECK_IN") in keys and ("CASH", "OTHER") in keys
    methods = admin_client.get(
        f"/api/v1/reports/financial/payment-methods?from_date={today}&to_date={today}"
    ).json()
    assert methods["rows"]  # method rows exist
    upi = [r for r in methods["rows"] if r["method"] == "UPI"][0]
    assert upi["net_total"] == "2000.00"


def test_collections_net_after_reversal(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Net collection = originals minus reversals, never double-counted."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    payment = _pay(receptionist_client, booking_id, "2500.00", mode="UPI").json()
    admin_client.post(
        f"/api/v1/bookings/{booking_id}/payments/{payment['id']}/reverse",
        json={"reason": "wrong"},
        headers=csrf_headers(admin_client),
    )
    today = _today_str()
    body = admin_client.get(
        f"/api/v1/reports/financial/collections?from_date={today}&to_date={today}"
    ).json()
    assert body["original_total"] == "2500.00"
    assert body["reversal_total"] == "2500.00"
    assert body["net_total"] == "0.00"
    methods = admin_client.get(
        f"/api/v1/reports/financial/payment-methods?from_date={today}&to_date={today}"
    ).json()
    assert methods["net_total"] == "0.00"


# --- Outstanding / reconciliation ------------------------------------------------


def test_outstanding_rows_and_credits(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Open dues + credits listed; settled bookings absent."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    _pay(receptionist_client, booking_id, "7500.00")
    owned = _book(
        receptionist_client,
        admin_client,
        room_type_id,
        room_id,
        guest_id,
        nights=1,
        with_rate=False,
        offset=10,
    )
    body = admin_client.get("/api/v1/reports/financial/outstanding").json()
    by_id = {r["booking_id"]: r for r in body["rows"]}
    assert booking_id not in by_id  # fully paid
    assert by_id[owned]["balance"] == "2500.00"
    assert body["outstanding_total"] == "2500.00"
    assert body["credit_total"] == "0.00"


def test_reconciliation_matches_sources(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Reconciliation equals direct DB sums (traceable, not invented)."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    _pay(receptionist_client, booking_id, "4000.00")
    import uuid

    entry_sum = (
        db_session.query(FolioEntry.amount)
        .filter(FolioEntry.booking_id == uuid.UUID(booking_id))
        .all()
    )
    expected_charges = sum((row[0] for row in entry_sum), Decimal(0))
    today = _today_str()
    body = admin_client.get(
        f"/api/v1/reports/financial/reconciliation?from_date={today}&to_date={today}"
    ).json()
    assert body["charge_entries"] == str(expected_charges)
    assert body["original_payments"] == "4000.00"
    assert body["net_payments"] == "4000.00"
    assert body["outstanding_in_period"] == "3500.00"
    assert body["credit_in_period"] == "0.00"
    assert body["entry_count"] >= 1
    assert body["payment_count"] == 1
    assert body["reversal_count"] == 0


# --- Bookings summary / occupancy -----------------------------------------------


def test_bookings_summary_and_occupancy(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Status counts and [check-in, check-out) occupancy (cancelled excluded)."""
    start = _today() + timedelta(days=1)
    end = start + timedelta(days=3)
    _book(receptionist_client, admin_client, room_type_id, room_id, guest_id, nights=3)
    summary = admin_client.get("/api/v1/reports/bookings/summary").json()
    assert summary["total"] >= 1
    assert summary["confirmed"] >= 1
    occ = admin_client.get(
        f"/api/v1/reports/bookings/occupancy?from_date={start.isoformat()}&to_date={end.isoformat()}"
    ).json()
    assert occ["occupied_room_nights"] >= 3
    assert Decimal(occ["occupancy_rate"]) > 0


# --- Reversals ------------------------------------------------------------------


def test_reversals_report(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Charge and payment reversals listed with originals linked; no deletions."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    charge = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/charges",
        json={"description": "Food", "quantity": "1", "unit_amount": "400.00"},
        headers=csrf_headers(receptionist_client),
    ).json()
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/folio/reversals",
        json={"entry_id": charge["id"], "reason": "not wanted"},
        headers=csrf_headers(receptionist_client),
    )
    payment = _pay(receptionist_client, booking_id, "900.00").json()
    admin_client.post(
        f"/api/v1/bookings/{booking_id}/payments/{payment['id']}/reverse",
        json={"reason": "wrong amount"},
        headers=csrf_headers(admin_client),
    )
    body = admin_client.get("/api/v1/reports/financial/reversals").json()
    assert body["payment_reversal_total"] == "900.00"
    assert body["charge_reversal_total"] == "-400.00"
    kinds = {item["kind"]: item for item in body["items"]}
    assert kinds["payment"]["reverses_id"] == payment["id"]
    assert kinds["charge"]["reverses_id"] == charge["id"]
    assert body["total"] == 2


# --- Security / read-only / export ----------------------------------------------


def test_reports_admin_only(receptionist_client) -> None:
    """RECEPTIONIST denied; unauthenticated denied; default-deny intact."""
    for url in (
        "/api/v1/reports/financial/summary",
        "/api/v1/reports/financial/collections",
        "/api/v1/reports/financial/payment-methods",
        "/api/v1/reports/financial/outstanding",
        "/api/v1/reports/financial/reconciliation",
        "/api/v1/reports/financial/reversals",
        "/api/v1/reports/bookings/summary",
        "/api/v1/reports/bookings/occupancy",
        "/api/v1/reports/financial/outstanding/export.csv",
    ):
        assert receptionist_client.get(url).status_code == 403, url


def test_reports_unauthenticated(client) -> None:
    """No session → 401."""
    assert client.get("/api/v1/reports/financial/summary").status_code == 401


def test_reports_are_read_only(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """GET reports write no financial rows and no audit rows."""
    _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    entries_before = db_session.query(FolioEntry).count()
    payments_before = db_session.query(Payment).count()
    audits_before = db_session.query(AuditLog).count()
    admin_client.get("/api/v1/reports/financial/summary")
    admin_client.get("/api/v1/reports/financial/collections")
    admin_client.get("/api/v1/reports/financial/outstanding")
    admin_client.get("/api/v1/reports/financial/reconciliation")
    admin_client.get("/api/v1/reports/financial/reversals")
    admin_client.get("/api/v1/reports/bookings/summary")
    admin_client.get("/api/v1/reports/bookings/occupancy")
    admin_client.get("/api/v1/reports/financial/outstanding/export.csv")
    assert db_session.query(FolioEntry).count() == entries_before
    assert db_session.query(Payment).count() == payments_before
    assert db_session.query(AuditLog).count() == audits_before


def test_csv_exports(receptionist_client, admin_client, room_type_id, room_id, guest_id) -> None:
    """CSV exports match the JSON figures and are CSV (not JSON)."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    _pay(receptionist_client, booking_id, "500.00", mode="UPI")
    today = _today_str()
    collections = admin_client.get(
        f"/api/v1/reports/financial/collections/export.csv?from_date={today}&to_date={today}"
    )
    assert collections.status_code == 200
    assert "text/csv" in collections.headers["content-type"]
    assert "UPI" in collections.text
    assert "500.00" in collections.text
    outstanding = admin_client.get("/api/v1/reports/financial/outstanding/export.csv")
    assert outstanding.status_code == 200
    assert "7000.00" in outstanding.text  # 7500 owed - 500 paid
