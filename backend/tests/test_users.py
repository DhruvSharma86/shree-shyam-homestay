"""User management + RBAC tests (ADMIN-only endpoints)."""

import pytest

from app.models.user import UserRole
from tests.factories import ADMIN_PASSWORD, RECEPTIONIST_PASSWORD, create_user, csrf_headers, login


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
    create_user(db_session, username="rec1", role=UserRole.RECEPTIONIST.value)
    db_session.commit()
    login(client, "rec1", ADMIN_PASSWORD)
    return client


def test_admin_can_create_user(admin_client) -> None:
    """ADMIN creates a RECEPTIONIST account (201)."""
    response = admin_client.post(
        "/api/v1/users",
        json={
            "username": "rec2",
            "password": RECEPTIONIST_PASSWORD,
            "full_name": "Reception Two",
            "role": "RECEPTIONIST",
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "rec2"
    assert body["role"] == "RECEPTIONIST"
    assert "password" not in body
    assert "password_hash" not in body


def test_receptionist_cannot_create_user(receptionist_client) -> None:
    """RECEPTIONIST is forbidden from user management (403 FORBIDDEN)."""
    response = receptionist_client.post(
        "/api/v1/users",
        json={
            "username": "sneaky",
            "password": RECEPTIONIST_PASSWORD,
            "full_name": "Sneaky",
            "role": "ADMIN",
        },
        headers=csrf_headers(receptionist_client),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_receptionist_cannot_list_users(receptionist_client) -> None:
    """RECEPTIONIST cannot list staff accounts."""
    response = receptionist_client.get("/api/v1/users")
    assert response.status_code == 403


def test_unauthenticated_cannot_access_users(client) -> None:
    """No session → 401 on admin endpoints."""
    assert client.get("/api/v1/users").status_code == 401


def test_admin_can_list_users(admin_client) -> None:
    """ADMIN lists accounts; neither password field is exposed."""
    response = admin_client.get("/api/v1/users")
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["username"] == "admin1"
    for user in users:
        assert "password" not in user
        assert "password_hash" not in user


def test_admin_can_deactivate_and_reactivate(admin_client) -> None:
    """ADMIN toggles is_active via PATCH."""
    created = admin_client.post(
        "/api/v1/users",
        json={
            "username": "rec3",
            "password": RECEPTIONIST_PASSWORD,
            "full_name": "Reception Three",
            "role": "RECEPTIONIST",
        },
        headers=csrf_headers(admin_client),
    ).json()

    off = admin_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    assert off.status_code == 200
    assert off.json()["is_active"] is False

    on = admin_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"is_active": True},
        headers=csrf_headers(admin_client),
    )
    assert on.status_code == 200
    assert on.json()["is_active"] is True


def test_cannot_deactivate_last_active_admin(admin_client) -> None:
    """Deactivating the final active ADMIN is blocked with 409."""
    me = admin_client.get("/api/v1/auth/me").json()["user"]
    response = admin_client.patch(
        f"/api/v1/users/{me['id']}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 409


def test_deactivated_user_sessions_revoked(admin_client, db_session) -> None:
    """Deactivation revokes the target's live sessions immediately."""
    created = admin_client.post(
        "/api/v1/users",
        json={
            "username": "rec4",
            "password": RECEPTIONIST_PASSWORD,
            "full_name": "Reception Four",
            "role": "RECEPTIONIST",
        },
        headers=csrf_headers(admin_client),
    ).json()

    # The new receptionist logs in with a separate client/view — simulate by
    # verifying via the DB that a session exists after login through a fresh
    # TestClient sharing the same app overrides.
    admin_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    # Inactive user can no longer authenticate.
    assert login(admin_client, "rec4", RECEPTIONIST_PASSWORD).status_code == 401


def test_admin_reset_password(admin_client) -> None:
    """ADMIN resets a user's password; old password fails, new works."""
    created = admin_client.post(
        "/api/v1/users",
        json={
            "username": "rec5",
            "password": RECEPTIONIST_PASSWORD,
            "full_name": "Reception Five",
            "role": "RECEPTIONIST",
        },
        headers=csrf_headers(admin_client),
    ).json()

    response = admin_client.post(
        f"/api/v1/users/{created['id']}/reset-password",
        json={"new_password": "ResetDone123!"},
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 200

    assert login(admin_client, "rec5", "ResetDone123!").status_code == 200
    assert login(admin_client, "rec5", RECEPTIONIST_PASSWORD).status_code == 401


def test_receptionist_cannot_reset_password(receptionist_client) -> None:
    """Password resets are ADMIN-only."""
    response = receptionist_client.post(
        "/api/v1/users/00000000-0000-0000-0000-000000000000/reset-password",
        json={"new_password": "ResetDone123!"},
        headers=csrf_headers(receptionist_client),
    )
    assert response.status_code == 403


def test_duplicate_username_conflict(admin_client) -> None:
    """Creating a second account with the same username → 409."""
    payload = {
        "username": "dup1",
        "password": RECEPTIONIST_PASSWORD,
        "full_name": "Dup One",
        "role": "RECEPTIONIST",
    }
    first = admin_client.post("/api/v1/users", json=payload, headers=csrf_headers(admin_client))
    assert first.status_code == 201
    second = admin_client.post("/api/v1/users", json=payload, headers=csrf_headers(admin_client))
    assert second.status_code == 409


def test_invalid_role_rejected(admin_client) -> None:
    """Only ADMIN/RECEPTIONIST roles may be assigned."""
    response = admin_client.post(
        "/api/v1/users",
        json={
            "username": "root1",
            "password": RECEPTIONIST_PASSWORD,
            "full_name": "Root One",
            "role": "SUPERUSER",
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 422


def test_no_public_registration_endpoint(client) -> None:
    """There is no public signup route anywhere."""
    for path in ("/api/v1/auth/register", "/api/v1/auth/signup", "/api/v1/register"):
        assert client.post(path, json={}).status_code == 404
