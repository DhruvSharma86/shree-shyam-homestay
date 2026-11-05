"""Restaurant + cab configuration tests."""

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


# --- Restaurant ---------------------------------------------------------


def test_restaurant_info_create_and_update(admin_client) -> None:
    """Restaurant info is created on first PATCH and updated after."""
    assert admin_client.get("/api/v1/admin/restaurant").json() is None
    created = admin_client.patch(
        "/api/v1/admin/restaurant",
        json={"name": "Shree Shyam Kitchen", "opening_hours": "07:00-22:00"},
        headers=csrf_headers(admin_client),
    )
    assert created.status_code == 200
    assert created.json()["name"] == "Shree Shyam Kitchen"
    updated = admin_client.patch(
        "/api/v1/admin/restaurant",
        json={"contact_number": "+911234567890"},
        headers=csrf_headers(admin_client),
    )
    assert updated.json()["contact_number"] == "+911234567890"
    assert updated.json()["name"] == "Shree Shyam Kitchen"


def test_create_menu_category(admin_client) -> None:
    """ADMIN creates a menu category."""
    response = admin_client.post(
        "/api/v1/admin/menu-categories",
        json={"name": "Breakfast"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Breakfast"


@pytest.fixture()
def category_id(admin_client) -> str:
    """Create a menu category and return its id."""
    return admin_client.post(
        "/api/v1/admin/menu-categories", json={"name": "Lunch"}, headers=csrf_headers(admin_client)
    ).json()["id"]


def test_create_menu_item(admin_client, category_id) -> None:
    """ADMIN adds a menu item with a price and image URL."""
    response = admin_client.post(
        "/api/v1/admin/menu-items",
        json={
            "name": "Paneer Butter Masala",
            "price": "320.00",
            "image_url": "https://example.com/paneer.jpg",
            "category_id": category_id,
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 201
    assert response.json()["price"] == "320.00"


def test_menu_item_price_update(admin_client, category_id) -> None:
    """Prices are configurable via PATCH."""
    item = admin_client.post(
        "/api/v1/admin/menu-items",
        json={"name": "Dal Tadka", "price": "220.00", "category_id": category_id},
        headers=csrf_headers(admin_client),
    ).json()
    response = admin_client.patch(
        f"/api/v1/admin/menu-items/{item['id']}",
        json={"price": "250.00"},
        headers=csrf_headers(admin_client),
    )
    assert response.json()["price"] == "250.00"


def test_menu_item_negative_price_rejected(admin_client, category_id) -> None:
    """Negative menu price → 422."""
    response = admin_client.post(
        "/api/v1/admin/menu-items",
        json={"name": "Bad", "price": "-10", "category_id": category_id},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 422


def test_menu_item_invalid_image_url_rejected(admin_client, category_id) -> None:
    """Non-URL image values → 422."""
    response = admin_client.post(
        "/api/v1/admin/menu-items",
        json={
            "name": "Bad Img",
            "price": "100",
            "image_url": "not-a-url",
            "category_id": category_id,
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 422


def test_deactivate_menu_item(admin_client, category_id) -> None:
    """Deactivation sets is_available=false."""
    item = admin_client.post(
        "/api/v1/admin/menu-items",
        json={"name": "Seasonal", "price": "180.00", "category_id": category_id},
        headers=csrf_headers(admin_client),
    ).json()
    response = admin_client.patch(
        f"/api/v1/admin/menu-items/{item['id']}",
        json={"is_available": False},
        headers=csrf_headers(admin_client),
    )
    assert response.json()["is_available"] is False


def test_menu_item_invalid_category_rejected(admin_client) -> None:
    """Unknown category_id → 404."""
    response = admin_client.post(
        "/api/v1/admin/menu-items",
        json={
            "name": "Ghost",
            "price": "100",
            "category_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 404


# --- Cab providers ------------------------------------------------------


def test_create_cab_provider(admin_client) -> None:
    """ADMIN adds a cab provider."""
    response = admin_client.post(
        "/api/v1/admin/cab-providers",
        json={
            "company_name": "City Cabs",
            "contact_number": "+911234567890",
            "website_url": "https://citycabs.example.com",
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 201
    assert response.json()["company_name"] == "City Cabs"


def test_cab_invalid_url_rejected(admin_client) -> None:
    """Invalid website URL → 422."""
    response = admin_client.post(
        "/api/v1/admin/cab-providers",
        json={
            "company_name": "Bad Cab",
            "contact_number": "1234567890",
            "website_url": "not-a-url",
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 422


def test_cab_short_phone_rejected(admin_client) -> None:
    """Too-short phone number → 422."""
    response = admin_client.post(
        "/api/v1/admin/cab-providers",
        json={"company_name": "Bad Cab", "contact_number": "123"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 422


def test_deactivate_cab_provider(admin_client) -> None:
    """Deactivation keeps the record (is_active=false)."""
    provider = admin_client.post(
        "/api/v1/admin/cab-providers",
        json={"company_name": "Old Cabs", "contact_number": "+919999999999"},
        headers=csrf_headers(admin_client),
    ).json()
    response = admin_client.patch(
        f"/api/v1/admin/cab-providers/{provider['id']}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    assert response.json()["is_active"] is False


# --- Authorization & audit ----------------------------------------------


def test_receptionist_forbidden_restaurant_cab(receptionist_client) -> None:
    """RECEPTIONIST cannot modify restaurant/cab/menu config (403)."""
    assert receptionist_client.get("/api/v1/admin/restaurant").status_code == 403
    assert (
        receptionist_client.patch(
            "/api/v1/admin/restaurant",
            json={"name": "X"},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )
    assert (
        receptionist_client.post(
            "/api/v1/admin/menu-categories",
            json={"name": "X"},
            headers=csrf_headers(receptionist_client),
        ).status_code
        == 403
    )
    assert receptionist_client.get("/api/v1/admin/cab-providers").status_code == 403


def test_unauthenticated_restaurant_endpoints(client) -> None:
    """No session → 401."""
    assert client.get("/api/v1/admin/restaurant").status_code == 401
    assert client.get("/api/v1/admin/cab-providers").status_code == 401


def test_restaurant_mutations_audited(admin_client, db_session) -> None:
    """Restaurant/cab mutations write audit rows without secrets."""
    admin_client.patch(
        "/api/v1/admin/restaurant", json={"name": "Kitchen"}, headers=csrf_headers(admin_client)
    )
    admin_client.post(
        "/api/v1/admin/cab-providers",
        json={"company_name": "City Cabs", "contact_number": "+911234567890"},
        headers=csrf_headers(admin_client),
    )
    actions = {r.action for r in db_session.scalars(select(AuditLog)).all()}
    assert "RESTAURANT_INFO_UPDATED" in actions
    assert "CAB_PROVIDER_CREATED" in actions
    blob = " ".join(str(r.metadata_json or "") for r in db_session.scalars(select(AuditLog)).all())
    assert "password" not in blob.lower()
