"""Hotel configuration tests — hotel profile, room types, rooms, rates, tax."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from tests.factories import ADMIN_PASSWORD, create_user, csrf_headers, login


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


# --- Hotel profile ------------------------------------------------------


def test_hotel_initially_null_then_created(admin_client) -> None:
    """GET /hotel is null before configuration, then PATCH creates the row."""
    assert admin_client.get("/api/v1/admin/hotel").json() is None
    response = admin_client.patch(
        "/api/v1/admin/hotel",
        json={"hotel_name": "Shree Shyam Home Stay", "city": "Example City"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hotel_name"] == "Shree Shyam Home Stay"
    assert body["city"] == "Example City"


def test_hotel_update(admin_client) -> None:
    """PATCH updates existing fields without creating a second row."""
    admin_client.patch(
        "/api/v1/admin/hotel", json={"hotel_name": "A"}, headers=csrf_headers(admin_client)
    )
    response = admin_client.patch(
        "/api/v1/admin/hotel", json={"city": "New City"}, headers=csrf_headers(admin_client)
    )
    assert response.json()["city"] == "New City"
    assert response.json()["hotel_name"] == "A"  # preserved


def test_hotel_singleton_enforced(admin_client) -> None:
    """Only one hotel_info row ever exists."""
    for name in ("One", "Two", "Three"):
        admin_client.patch(
            "/api/v1/admin/hotel", json={"hotel_name": name}, headers=csrf_headers(admin_client)
        )
    listed = admin_client.get("/api/v1/admin/hotel").json()
    assert listed["hotel_name"] == "Three"


# --- Room types ---------------------------------------------------------


def test_create_room_type(admin_client) -> None:
    """ADMIN creates a category."""
    response = admin_client.post(
        "/api/v1/admin/room-types",
        json={"name": "Deluxe", "maximum_occupancy": 3},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Deluxe"


def test_duplicate_room_type_rejected(admin_client) -> None:
    """Duplicate category name → 409."""
    admin_client.post(
        "/api/v1/admin/room-types", json={"name": "Normal"}, headers=csrf_headers(admin_client)
    )
    response = admin_client.post(
        "/api/v1/admin/room-types", json={"name": "Normal"}, headers=csrf_headers(admin_client)
    )
    assert response.status_code == 409


def test_deactivate_room_type(admin_client) -> None:
    """Deactivation sets is_active=false (record kept, never deleted)."""
    created = admin_client.post(
        "/api/v1/admin/room-types", json={"name": "Old Cat"}, headers=csrf_headers(admin_client)
    ).json()
    response = admin_client.patch(
        f"/api/v1/admin/room-types/{created['id']}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    assert response.json()["is_active"] is False


# --- Rooms --------------------------------------------------------------


@pytest.fixture()
def room_type_id(admin_client) -> str:
    """Create a category and return its id."""
    return admin_client.post(
        "/api/v1/admin/room-types", json={"name": "Deluxe"}, headers=csrf_headers(admin_client)
    ).json()["id"]


def test_create_room(admin_client, room_type_id) -> None:
    """ADMIN creates a room with an assigned number."""
    response = admin_client.post(
        "/api/v1/admin/rooms",
        json={"room_number": "101", "room_type_id": room_type_id},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 201
    assert response.json()["operational_status"] == "AVAILABLE"


def test_duplicate_room_number_rejected(admin_client, room_type_id) -> None:
    """Duplicate room_number → 409."""
    payload = {"room_number": "102", "room_type_id": room_type_id}
    admin_client.post("/api/v1/admin/rooms", json=payload, headers=csrf_headers(admin_client))
    response = admin_client.post(
        "/api/v1/admin/rooms", json=payload, headers=csrf_headers(admin_client)
    )
    assert response.status_code == 409


def test_invalid_room_category_rejected(admin_client) -> None:
    """Unknown room_type_id → 404."""
    response = admin_client.post(
        "/api/v1/admin/rooms",
        json={"room_number": "103", "room_type_id": "00000000-0000-0000-0000-000000000000"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 404


def test_room_maintenance_status(admin_client, room_type_id) -> None:
    """A room can be put into MAINTENANCE (operational, not occupancy)."""
    room = admin_client.post(
        "/api/v1/admin/rooms",
        json={"room_number": "104", "room_type_id": room_type_id},
        headers=csrf_headers(admin_client),
    ).json()
    response = admin_client.patch(
        f"/api/v1/admin/rooms/{room['id']}",
        json={"operational_status": "MAINTENANCE"},
        headers=csrf_headers(admin_client),
    )
    assert response.json()["operational_status"] == "MAINTENANCE"


def test_room_invalid_operational_status(admin_client, room_type_id) -> None:
    """Invalid operational_status → 422."""
    room = admin_client.post(
        "/api/v1/admin/rooms",
        json={"room_number": "105", "room_type_id": room_type_id},
        headers=csrf_headers(admin_client),
    ).json()
    response = admin_client.patch(
        f"/api/v1/admin/rooms/{room['id']}",
        json={"operational_status": "OCCUPIED"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 422


# --- Room rates ---------------------------------------------------------


def test_create_rate(admin_client, room_type_id) -> None:
    """ADMIN creates a category rate version."""
    response = admin_client.post(
        "/api/v1/admin/room-rates",
        json={"room_type_id": room_type_id, "nightly_rate": "2500.00", "valid_from": "2026-11-05"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 201
    assert Decimal(response.json()["nightly_rate"]) == Decimal("2500.00")


def test_negative_rate_rejected(admin_client, room_type_id) -> None:
    """Negative nightly_rate → 422 (schema-level)."""
    response = admin_client.post(
        "/api/v1/admin/room-rates",
        json={"room_type_id": room_type_id, "nightly_rate": "-1", "valid_from": "2026-11-05"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 422


def test_overlapping_rate_rejected(admin_client, room_type_id) -> None:
    """Overlapping active rate periods → 409."""
    admin_client.post(
        "/api/v1/admin/room-rates",
        json={"room_type_id": room_type_id, "nightly_rate": "2000", "valid_from": "2026-11-05"},
        headers=csrf_headers(admin_client),
    )
    response = admin_client.post(
        "/api/v1/admin/room-rates",
        json={"room_type_id": room_type_id, "nightly_rate": "2200", "valid_from": "2026-12-01"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 409


def test_future_price_change_preserves_history(admin_client, room_type_id, db_session) -> None:
    """A new version never modifies the prior row."""
    first = admin_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": "2000",
            "valid_from": "2026-11-05",
            "valid_until": "2026-11-30",
        },
        headers=csrf_headers(admin_client),
    ).json()
    second = admin_client.post(
        "/api/v1/admin/room-rates",
        json={"room_type_id": room_type_id, "nightly_rate": "2500", "valid_from": "2026-12-01"},
        headers=csrf_headers(admin_client),
    )
    assert second.status_code == 201
    rates = admin_client.get("/api/v1/admin/room-rates").json()
    assert len(rates) == 2
    old = next(r for r in rates if r["id"] == first["id"])
    assert Decimal(old["nightly_rate"]) == Decimal("2000")  # unchanged


# --- Tax settings -------------------------------------------------------


def test_tax_default_none(admin_client) -> None:
    """No tax configured by default → empty list (NONE)."""
    assert admin_client.get("/api/v1/admin/tax-settings").json() == []


def test_tax_settings_creation(admin_client) -> None:
    """ADMIN creates a tax settings version."""
    response = admin_client.post(
        "/api/v1/admin/tax-settings",
        json={
            "tax_type": "GST",
            "tax_rate": "5.00",
            "pricing_mode": "EXCLUSIVE",
            "valid_from": "2026-11-05",
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 201
    assert response.json()["tax_type"] == "GST"


def test_tax_invalid_configuration_rejected(admin_client) -> None:
    """Non-NONE tax without a rate → 422."""
    response = admin_client.post(
        "/api/v1/admin/tax-settings",
        json={"tax_type": "GST", "tax_rate": None, "valid_from": "2026-11-05"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 422


def test_tax_overlapping_period_rejected(admin_client, db_session) -> None:
    """Overlapping tax periods → 409."""
    admin_client.post(
        "/api/v1/admin/tax-settings",
        json={"tax_type": "NONE", "valid_from": "2026-11-05"},
        headers=csrf_headers(admin_client),
    )
    response = admin_client.post(
        "/api/v1/admin/tax-settings",
        json={"tax_type": "GST", "tax_rate": "12.00", "valid_from": "2026-11-10"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 409


def test_tax_history_preserved(admin_client) -> None:
    """Creating a later version keeps the earlier row."""
    admin_client.post(
        "/api/v1/admin/tax-settings",
        json={"tax_type": "NONE", "valid_from": "2026-11-05", "valid_until": "2026-11-30"},
        headers=csrf_headers(admin_client),
    )
    admin_client.post(
        "/api/v1/admin/tax-settings",
        json={"tax_type": "GST", "tax_rate": "5.00", "valid_from": "2026-12-01"},
        headers=csrf_headers(admin_client),
    )
    rows = admin_client.get("/api/v1/admin/tax-settings").json()
    assert len(rows) == 2
    assert rows[0]["tax_type"] == "NONE"


# --- Authorization ------------------------------------------------------


def test_receptionist_forbidden_hotel_mutations(receptionist_client) -> None:
    """RECEPTIONIST cannot modify any hotel configuration (403)."""
    assert receptionist_client.get("/api/v1/admin/hotel").status_code == 403
    assert (
        receptionist_client.patch(
            "/api/v1/admin/hotel",
            json={"hotel_name": "X"},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )
    assert (
        receptionist_client.post(
            "/api/v1/admin/room-types",
            json={"name": "X"},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )
    assert (
        receptionist_client.post(
            "/api/v1/admin/room-rates",
            json={
                "room_type_id": "00000000-0000-0000-0000-000000000000",
                "nightly_rate": "1",
                "valid_from": "2026-11-05",
            },
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )
    assert (
        receptionist_client.post(
            "/api/v1/admin/tax-settings",
            json={"tax_type": "NONE", "valid_from": "2026-11-05"},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )
    assert (
        receptionist_client.post(
            "/api/v1/admin/cab-providers",
            json={"company_name": "CabCo", "contact_number": "1234567890"},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )


def test_unauthenticated_hotel_endpoints(client) -> None:
    """No session → 401 on admin endpoints."""
    assert client.get("/api/v1/admin/hotel").status_code == 401
    assert client.get("/api/v1/admin/room-types").status_code == 401
    assert client.get("/api/v1/admin/tax-settings").status_code == 401


def test_hotel_mutations_audited(admin_client, db_session) -> None:
    """Every admin mutation writes an audit row (no secrets)."""
    admin_client.patch(
        "/api/v1/admin/hotel", json={"hotel_name": "Audited"}, headers=csrf_headers(admin_client)
    )
    admin_client.post(
        "/api/v1/admin/room-types", json={"name": "Audited Cat"}, headers=csrf_headers(admin_client)
    )
    actions = {r.action for r in db_session.scalars(select(AuditLog)).all()}
    assert "HOTEL_INFO_UPDATED" in actions
    assert "ROOM_TYPE_CREATED" in actions
