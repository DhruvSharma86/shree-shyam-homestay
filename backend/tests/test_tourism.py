"""Tourism content tests — CRUD, RBAC, CSRF, guest filtering, audit."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.tourism import LocalInfo, TourPackage
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
        json={"full_name": "Tour Guest", "phone": "+919876543210"},
        headers=csrf_headers(receptionist_client),
    ).json()["id"]


def _checkin_token(receptionist_client, admin_client, room_type_id, room_id, guest_id):
    """Create + check in a booking and return its raw portal token."""
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
    r = receptionist_client.post(
        "/api/v1/bookings",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "source": "WALK_IN",
            "check_in_date": start.isoformat(),
            "check_out_date": end.isoformat(),
        },
        headers=csrf_headers(receptionist_client),
    )
    booking_id = r.json()["id"]
    receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"amount": "2500.00", "mode": "CASH", "payment_stage": "CHECK_IN"},
        headers=csrf_headers(receptionist_client),
    )
    checked = receptionist_client.post(
        f"/api/v1/bookings/{booking_id}/check-in",
        json={},
        headers=csrf_headers(receptionist_client),
    )
    assert checked.status_code == 200, checked.text
    return checked.json()["portal_access_token"]


# --- Tour packages --------------------------------------------------------------


def test_tour_package_crud(admin_client, receptionist_client) -> None:
    """Create + patch lifecycle (inactive toggle) with content values."""
    created = admin_client.post(
        "/api/v1/admin/tour-packages",
        json={
            "name": "Fort Walk",
            "description": "Morning guided tour",
            "duration": "3 hours",
            "price": "800.00",
            "image_url": "https://pics.test/fort.jpg",
            "contact_number": "+919800000000",
            "display_order": 1,
        },
        headers=csrf_headers(admin_client),
    )
    assert created.status_code == 201, created.text
    pkg_id = created.json()["id"]
    patched = admin_client.patch(
        f"/api/v1/admin/tour-packages/{pkg_id}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False
    assert patched.json()["name"] == "Fort Walk"


def test_tour_package_validation(admin_client, receptionist_client) -> None:
    """Empty name / negative price rejected."""
    empty = admin_client.post(
        "/api/v1/admin/tour-packages", json={"name": ""}, headers=csrf_headers(admin_client)
    )
    assert empty.status_code == 422
    negative = admin_client.post(
        "/api/v1/admin/tour-packages",
        json={"name": "x", "price": "-1.00"},
        headers=csrf_headers(admin_client),
    )
    assert negative.status_code == 422


def test_tourism_rbac(admin_client, receptionist_client, client) -> None:
    """Content endpoints are ADMIN-only; anonymous gets 401."""
    payload = {"name": "Hidden"}
    assert receptionist_client.post(
        "/api/v1/admin/tour-packages", json=payload, headers=csrf_headers(receptionist_client)
    ).status_code == 403
    assert client.post("/api/v1/admin/tour-packages", json=payload).status_code == 401
    assert receptionist_client.get("/api/v1/admin/tour-packages").status_code == 403
    assert (
        receptionist_client.post(
            "/api/v1/admin/local-info",
            json={"title": "x"},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )


def test_tourism_csrf(admin_client, receptionist_client) -> None:
    """Mutations without CSRF tokens are rejected."""
    assert (
        admin_client.post("/api/v1/admin/tour-packages", json={"name": "no csrf"}).status_code
        == 403
    )


def test_tourism_audit(admin_client, receptionist_client, db_session) -> None:
    """Mutations audit with ids/titles — no PII."""
    created = admin_client.post(
        "/api/v1/admin/tour-packages",
        json={"name": "Boat Ride", "description": "Lake"},
        headers=csrf_headers(admin_client),
    ).json()
    admin_client.post(
        "/api/v1/admin/local-info",
        json={"title": "Old Market", "location": "North Gate"},
        headers=csrf_headers(admin_client),
    )
    assert created["name"] == "Boat Ride"
    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action.in_(["TOUR_PACKAGE_CREATED", "LOCAL_INFO_CREATED"]))
    ).all()
    assert len(rows) == 2
    blob = " ".join(str(r.metadata_json or "") for r in rows)
    assert "Tour Guest" not in blob


def test_local_info_crud(admin_client, receptionist_client) -> None:
    """Create/patch local information (incl. deactivation)."""
    created = admin_client.post(
        "/api/v1/admin/local-info",
        json={"title": "Craft Bazaar", "location": "Old Town", "contact_number": "+919800000000"},
        headers=csrf_headers(admin_client),
    )
    assert created.status_code == 201, created.text
    row_id = created.json()["id"]
    patched = admin_client.patch(
        f"/api/v1/admin/local-info/{row_id}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False


# --- Guest endpoint filtering ---------------------------------------------------


def test_guest_tourism_active_only(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """Guests see active tourism only; inactive rows are invisible."""
    raw = _checkin_token(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    active = admin_client.post(
        "/api/v1/admin/tour-packages",
        json={"name": "Visible Trip", "duration": "1 day"},
        headers=csrf_headers(admin_client),
    ).json()
    hidden = admin_client.post(
        "/api/v1/admin/tour-packages",
        json={"name": "Hidden Trip", "price": "999.00"},
        headers=csrf_headers(admin_client),
    ).json()
    admin_client.patch(
        f"/api/v1/admin/tour-packages/{hidden['id']}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    info = admin_client.post(
        "/api/v1/admin/local-info",
        json={"title": "Heritage Park", "location": "Lake Road"},
        headers=csrf_headers(admin_client),
    ).json()
    assert active and info
    r = client.get(f"/api/v1/guest-portal/{raw}/tourism")
    assert r.status_code == 200, r.text
    body = r.json()
    names = [p["name"] for p in body["packages"]]
    assert "Visible Trip" in names
    assert "Hidden Trip" not in names
    assert any(i["title"] == "Heritage Park" for i in body["local_info"])
    assert "id" not in body["packages"][0]  # no internal ids
    assert "is_active" not in body["packages"][0]


def test_guest_tourism_empty_when_unconfigured(
    receptionist_client, admin_client, room_type_id, room_id, guest_id, client
) -> None:
    """No tourism rows configured → empty lists, still 200."""
    raw = _checkin_token(receptionist_client, admin_client, room_type_id, room_id, guest_id)
    r = client.get(f"/api/v1/guest-portal/{raw}/tourism")
    assert r.status_code == 200, r.text
    assert r.json() == {"packages": [], "local_info": []}


def test_tourism_row_persistence(admin_client, db_session) -> None:
    """Both tourism models exist and are registered on metadata."""
    from app.core.db import Base

    assert "tour_packages" in Base.metadata.tables
    assert "local_info" in Base.metadata.tables
    assert db_session.query(TourPackage).count() == 0
    assert db_session.query(LocalInfo).count() == 0
