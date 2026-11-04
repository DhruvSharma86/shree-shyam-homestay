"""Authentication endpoint tests (login/logout/me/change-password)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.auth.service import _utcnow
from app.core.security import hash_token
from app.models.session import Session as SessionModel
from app.models.user import UserRole
from tests.factories import ADMIN_PASSWORD, create_user, csrf_headers, login


def test_login_success_sets_http_only_cookie(client, db_session) -> None:
    """Valid credentials return 200 and an HttpOnly session cookie."""
    create_user(db_session, username="admin1")
    db_session.commit()

    response = login(client, "admin1", ADMIN_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "admin1"
    assert body["user"]["role"] == "ADMIN"
    assert "users.manage" in body["permissions"]
    set_cookie = response.headers.get("set-cookie", "")
    assert "sshs_session" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_login_invalid_password_generic_message(client, db_session) -> None:
    """Wrong password → 401 with the generic INVALID_CREDENTIALS envelope."""
    create_user(db_session, username="admin1")
    db_session.commit()

    response = login(client, "admin1", "WrongPassword999!")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    # Must not reveal whether the username exists.
    assert "admin1" not in response.text


def test_login_unknown_user_same_generic_message(client, db_session) -> None:
    """Unknown username produces the identical generic error as a bad password."""
    response = login(client, "ghost", "Whatever12345!")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_inactive_user_rejected(client, db_session) -> None:
    """Inactive accounts cannot log in (same generic 401)."""
    create_user(db_session, username="off1", is_active=False)
    db_session.commit()

    response = login(client, "off1", ADMIN_PASSWORD)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_authentication(client) -> None:
    """Unauthenticated /me → 401 UNAUTHENTICATED."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_returns_current_user(client, db_session) -> None:
    """Authenticated /me returns the user + permissions."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "admin1"
    assert body["user"]["role"] == "ADMIN"
    assert "users.manage" in body["permissions"]


def test_logout_revokes_session(client, db_session) -> None:
    """After logout the old cookie no longer authenticates."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)
    assert client.get("/api/v1/auth/me").status_code == 200

    response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    assert response.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_without_csrf_rejected(client, db_session) -> None:
    """Mutating endpoints require the CSRF header."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)

    response = client.post("/api/v1/auth/logout")  # no CSRF header

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"


def test_session_token_stored_hashed_only(client, db_session) -> None:
    """The DB stores only the SHA-256 hash, never the plaintext token."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)

    plaintext = client.cookies.get("sshs_session")
    assert plaintext
    stored = db_session.scalars(select(SessionModel)).all()
    assert len(stored) == 1
    assert stored[0].session_token_hash == hash_token(plaintext)
    assert stored[0].session_token_hash != plaintext


def test_expired_session_rejected(client, db_session) -> None:
    """A session past its absolute expiry is revoked and rejected."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)

    row = db_session.scalar(select(SessionModel))
    row.expires_at = _utcnow() - timedelta(minutes=1)
    row.last_seen_at = _utcnow() - timedelta(minutes=1)
    db_session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_idle_timeout_rejected(client, db_session) -> None:
    """A session idle longer than the configured window is rejected."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)

    row = db_session.scalar(select(SessionModel))
    # Idle deadline (30 min) exceeded, absolute expiry still in future.
    row.last_seen_at = _utcnow() - timedelta(minutes=31)
    row.expires_at = _utcnow() + timedelta(hours=11)
    db_session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_change_password_success_and_old_rejected(client, db_session) -> None:
    """Password change works; the old password no longer logs in."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "NewSecret123!"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200

    fresh = login(client, "admin1", ADMIN_PASSWORD)
    assert fresh.status_code == 401
    fresh2 = login(client, "admin1", "NewSecret123!")
    assert fresh2.status_code == 200


def test_change_password_wrong_current_rejected(client, db_session) -> None:
    """Wrong current password → 401, password unchanged."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "NotThePassword!", "new_password": "NewSecret123!"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 401


def test_login_rate_limiting(client, db_session) -> None:
    """After the failed-attempt budget, further attempts get 429."""
    create_user(db_session, username="admin1")
    db_session.commit()

    for _ in range(10):
        assert login(client, "admin1", "bad-password-1").status_code == 401
    response = login(client, "admin1", "bad-password-1")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.parametrize(
    "role,expected_admin_perm",
    [("ADMIN", True), ("RECEPTIONIST", False)],
)
def test_receptionist_login_has_no_admin_permissions(
    client, db_session, role, expected_admin_perm
) -> None:
    """Receptionists log in but never receive admin permissions."""
    create_user(db_session, username="u1", role=role)
    db_session.commit()

    response = login(client, "u1", ADMIN_PASSWORD)

    assert response.status_code == 200
    perms = response.json()["permissions"]
    assert ("users.manage" in perms) == expected_admin_perm
    if role == UserRole.RECEPTIONIST.value:
        assert "reports.financial.read" not in perms
        assert "pricing.manage" not in perms
        assert "profile.read" in perms
