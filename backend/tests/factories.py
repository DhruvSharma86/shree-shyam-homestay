"""Test data factories (no fixtures needed for simple row creation)."""

from sqlalchemy.orm import Session as DBSession

from app.core.security import hash_password
from app.models.user import User, UserRole

ADMIN_PASSWORD = "AdminPass123!"
RECEPTIONIST_PASSWORD = "Reception123!"


def create_user(
    db: DBSession,
    *,
    username: str = "admin1",
    password: str = ADMIN_PASSWORD,
    role: str = UserRole.ADMIN.value,
    is_active: bool = True,
) -> User:
    """Create and flush a user row (caller commits/rolls back)."""
    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=username.title(),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def login(client, username: str, password: str):
    """POST /api/v1/auth/login and return the response."""
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def csrf_headers(client) -> dict[str, str]:
    """Return CSRF headers echoing the cookie set at login."""
    token = client.cookies.get("sshs_csrf")
    return {"X-CSRF-Token": token} if token else {}
