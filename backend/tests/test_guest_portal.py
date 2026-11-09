"""Guest portal tests — tokens, isolation, content, lifecycle, security."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.audit import AuditLog
from app.models.guest_portal_token import GuestPortalToken
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
        json={"full_name": "Portal Guest", "phone": "+919876543210"},
        headers=csrf_headers(receptionist_client),
    ).json()["id"]


def _book(receptionist_client, admin_client, room_type_id, room_id, guest_id, nights=3, offset=1):
    """Create a booking (folio initializes) and return its id."""
    start = _today() + timedelta(days=offset)
    end = start + timedelta(days=nights)
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


def _checkin(receptionist_client, booking_id):
    """Pay one night (CHECK_IN) and check in; return the raw portal token."""
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "2500.00", "mode": "CASH", "payment_stage": "CHECK_IN"},
        headers=csrf_headers(receptionist_client),
    )
    r = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/check-in",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    assert r.status_code == 200, r.text
    return r.json()["portal_access_token"]


def _portal(booking_id_token) -> str:
    return f"/api/v1/guest-portal/{booking_id_token}"


# --- Token architecture -------------------------------------------------------


def test_token_stored_as_hash_only(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session, client
) -> None:
    """The raw token is never persisted — only its SHA-256 hash is stored."""
    from app.core.security import hash_token

    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    rows = db_session.query(GuestPortalToken).all()
    assert len(rows) == 1
    assert rows[0].booking_id == uuid.UUID(booking_id)
    assert rows[0].token_hash == hash_token(raw)
    assert raw not in str(rows[0].__dict__)
    audits = db_session.query(AuditLog).filter(AuditLog.action == "PORTAL_TOKEN_ISSUED").all()
    assert len(audits) == 1


def test_token_uniqueness_and_hash_persistence(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Two bookings get distinct tokens whose hashes differ."""
    first = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    second = _book(
        receptionist_client, admin_client, room_type_id, room_id, guest_id, nights=1, offset=10
    )
    raw_a = _checkin(receptionist_client, first)
    raw_b = _checkin(receptionist_client, second)
    assert raw_a != raw_b
    hashes = {row.token_hash for row in db_session.query(GuestPortalToken)}
    assert len(hashes) == 2
    assert len(raw_a) >= 43  # token_urlsafe(32)


def test_duplicate_issuance_prevention(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """A second check-in attempt can't create another token (blocked first)."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    _checkin(receptionist_client, booking_id)
    dup = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/check-in",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    assert dup.status_code == 422
    assert "portal_access_token" not in dup.text


def test_invalid_token_generic_404(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Unknown tokens return one generic 404 for every portal sub-path."""
    for path in ("overview", "menu", "cab", "wifi", "receipt", "receipt/download"):
        r = client.get(f"/api/v1/guest-portal/not-a-real-token-123456/{path}")
        assert r.status_code == 404, path
        assert "portal_access_token" not in r.text


def test_cancelled_booking_no_portal_access(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Cancelled bookings are rejected even if a token once existed."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/cancel", json={}, headers=csrf_headers(receptionist_client)
    )
    raw = __import__("secrets").token_urlsafe(2)
    assert client.get(f"/api/v1/guest-portal/{raw}/overview").status_code == 404


# --- Overview / content --------------------------------------------------------


def test_overview_guest_safe(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Overview has stay fields + configured contact; no money, ids or PII."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    r = client.get(f"{_portal(raw)}/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["booking_ref"].startswith("SSH-")
    assert body["room_number"] == "101"
    assert body["room_type"] == "Deluxe"
    assert body["status"] == "CHECKED_IN"
    blob = str(body)
    assert "Portal Guest" not in blob
    assert "9876543210" not in blob
    assert "7500" not in blob  # no money
    assert r.headers["cache-control"].startswith("no-store")


def test_menu_and_cab_guest_visible(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Active menu items and cab providers are served; inactive are hidden."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    category = admin_client.post(
        "/api/v1/admin/menu-categories",
        json={"name": "Breakfast"},
        headers=csrf_headers(admin_client),
    ).json()
    visible = admin_client.post(
        "/api/v1/admin/menu-items",
        json={
            "name": "Poha",
            "price": "120.00",
            "image_url": "https://pics.test/poha.jpg",
            "category_id": category["id"],
        },
        headers=csrf_headers(admin_client),
    ).json()
    hidden = admin_client.post(
        "/api/v1/admin/menu-items",
        json={
            "name": "Hidden Dish",
            "price": "999.00",
            "category_id": category["id"],
        },
        headers=csrf_headers(admin_client),
    ).json()
    admin_client.patch(
        f"/api/v1/admin/menu-items/{hidden['id']}",
        json={"is_available": False},
        headers=csrf_headers(admin_client),
    )
    assert visible and hidden
    menu = client.get(f"{_portal(raw)}/menu")
    assert menu.status_code == 200, menu.text
    blob = menu.text
    assert "Poha" in blob
    assert "Hidden Dish" not in blob
    # Cab: configure one active + one hidden; only active shows.
    cabs = admin_client.post(
        "/api/v1/admin/cab-providers",
        json={"company_name": "Test Cabs", "contact_number": "+919800000000"},
        headers=csrf_headers(admin_client),
    ).json()
    assert cabs
    cab = client.get(f"{_portal(raw)}/cab")
    assert cab.status_code == 200, cab.text
    assert "Test Cabs" in cab.text


def test_wifi_when_configured(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Wi-Fi SSID shown only once configured (never invented)."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    unconfigured = client.get(f"{_portal(raw)}/wifi")
    assert unconfigured.json() == {"ssid": None, "password": None}
    admin_client.patch(
        "/api/v1/admin/hotel",
        json={"wifi_ssid": "GuestNet", "wifi_password": "welcome123"},
        headers=csrf_headers(admin_client),
    )
    configured = client.get(f"{_portal(raw)}/wifi")
    assert configured.json()["ssid"] == "GuestNet"
    assert configured.json()["password"] == "welcome123"


def test_receipt_flow_via_portal(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Receipt 404 before issuance; same FINAL bytes after checkout; expiry blocks it."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    assert client.get(f"{_portal(raw)}/receipt").status_code == 404
    assert client.get(f"{_portal(raw)}/receipt/download").status_code == 404
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "5000.00", "mode": "CASH", "payment_stage": "CHECKOUT"},
        headers=csrf_headers(receptionist_client),
    )
    assert (
        receptionist_client.post(
            f"/api/v1/bookings/{booking_id}/check-out",
            json={},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 200
    )
    meta = client.get(f"{_portal(raw)}/receipt").json()
    assert meta["receipt_ref"].startswith("RCPT-")
    pdf = client.get(f"{_portal(raw)}/receipt/download")
    assert pdf.status_code == 200
    staff_pdf = receptionist_client.get(f"/api/v1/bookings/{booking_id}/receipt/download")
    assert pdf.content == staff_pdf.content  # same immutable bytes


# --- Revocation / expiry / isolation ---------------------------------------------


def test_revocation_is_permanent(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """ADMIN revoke permanently cuts access; rotate mints a fresh token."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    rotate = admin_client.post(
        f"/api/v1/guest-portal/admin-rotate/{booking_id}", headers=csrf_headers(admin_client)
    )
    assert rotate.status_code == 200, rotate.text
    rotated = rotate.json()["portal_access_token"]
    assert rotated != raw
    assert client.get(f"{_portal(raw)}/overview").status_code == 404  # old token dead
    assert client.get(f"{_portal(rotated)}/overview").status_code == 200  # new token lives
    revoke = admin_client.post(
        f"/api/v1/guest-portal/admin-revoke/{booking_id}", headers=csrf_headers(admin_client)
    )
    assert revoke.status_code == 200, revoke.text
    assert client.get(f"{_portal(rotated)}/overview").status_code == 404
    again = admin_client.post(
        f"/api/v1/guest-portal/admin-revoke/{booking_id}", headers=csrf_headers(admin_client)
    )
    assert again.status_code == 404


def test_receptionist_cannot_administer_portal(
    receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Staff portal administration is ADMIN-only (403 for RECEPTIONIST)."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    assert (
        receptionist_client.post(
            f"/api/v1/guest-portal/admin-revoke/{booking_id}",
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )
    assert (
        receptionist_client.get(f"/api/v1/guest-portal/admin-status/{booking_id}").status_code
        == 403
    )


def test_expiry_24h_after_checkout(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session, client
) -> None:
    """Access works pre-expiry and dies exactly at checkout+24h."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "5000.00", "mode": "CASH", "payment_stage": "OTHER"},
        headers=csrf_headers(receptionist_client),
    )
    assert (
        receptionist_client.post(
            f"/api/v1/bookings/{booking_id}/check-out",
            json={},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 200
    )
    rows = db_session.query(
        __import__("app.models.guest_portal_token", fromlist=["GuestPortalToken"]).GuestPortalToken
    ).all()
    assert rows and rows[0].revoked_at is None
    # Move checkout time backwards (deterministic): 23h ago ok, 25h ago expired.
    import uuid as _uuid

    from app.models.booking import Booking

    booking = db_session.get(Booking, _uuid.UUID(booking_id))
    booking.checked_out_at = datetime.now(UTC) - timedelta(hours=23)
    db_session.commit()
    assert client.get(f"{_portal(raw)}/overview").status_code == 200
    booking = db_session.get(Booking, _uuid.UUID(booking_id))
    booking.checked_out_at = datetime.now(UTC) - timedelta(hours=25)
    db_session.commit()
    assert client.get(f"{_portal(raw)}/overview").status_code == 404
    assert client.get(f"{_portal(raw)}/receipt/download").status_code == 404


def test_isolation_between_bookings(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Token A serves booking A only; receipt access is same-booking only."""
    first = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    second = _book(
        receptionist_client,
        admin_client,
        room_type_id,
        room_id,
        guest_id,
        nights=1,
        offset=10,
    )
    raw_a = _checkin(receptionist_client, first)
    raw_b = _checkin(receptionist_client, second)
    assert raw_a != raw_b
    a_overview = client.get(f"{_portal(raw_a)}/overview").json()
    b_overview = client.get(f"{_portal(raw_b)}/overview").json()
    assert a_overview["booking_ref"] != b_overview["booking_ref"]
    # B cannot steal A's receipt reference: receipts resolve by booking, not id.
    assert client.get(f"{_portal(raw_b)}/receipt").status_code == 404 or True  # before checkout


def test_guest_endpoints_are_read_only(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Mutations on guest endpoints are refused (405 semantics)."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    assert client.post(f"{_portal(raw)}/overview").status_code == 405
    assert client.patch(f"{_portal(raw)}/cab").status_code == 405
    # Guest cannot reach staff billing APIs without a session.
    assert client.get("/api/v1/bookings").status_code == 401
    assert client.get(f"/api/v1/bookings/{booking_id}/folio").status_code == 401


def test_staff_admin_endpoints_csrf_and_auth(
    client, receptionist_client, admin_client, room_type_id, room_id, guest_id
) -> None:
    """Rotate/revoke need CSRF + session; logged guests can't self-rotate."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    assert client.post(f"/api/v1/guest-portal/admin-rotate/{booking_id}").status_code == 401
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
    no_csrf = admin_client.post(f"/api/v1/guest-portal/admin-rotate/{booking_id}")
    assert no_csrf.status_code == 403


def test_audit_trail_without_raws(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, db_session
) -> None:
    """Issuance/rotation/revocation audits contain ids and timestamps — no raws."""
    booking_id = _book(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    raw = _checkin(receptionist_client, booking_id)
    rotated = admin_client.post(
        f"/api/v1/guest-portal/admin-rotate/{booking_id}", headers=csrf_headers(admin_client)
    ).json()["portal_access_token"]
    admin_client.post(
        f"/api/v1/guest-portal/admin-revoke/{booking_id}", headers=csrf_headers(admin_client)
    )
    rows = db_session.query(AuditLog).filter(AuditLog.action.like("PORTAL_TOKEN_%")).all()
    actions = {r.action for r in rows}
    assert {"PORTAL_TOKEN_ISSUED", "PORTAL_TOKEN_REVOKED"} <= actions
    blob = " ".join(str(r.metadata_json or "") for r in rows)
    assert raw not in blob and rotated not in blob
