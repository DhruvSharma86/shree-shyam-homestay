"""FastAPI dependencies for authentication, CSRF, and RBAC.

- :func:`get_current_user` — resolves the session cookie to a user (401).
- :func:`require_permission` — factory building a dependency that enforces
  one permission with default-deny semantics (403 when missing).
- CSRF: double-submit cookie. The server sets a random ``sshs_csrf`` cookie
  alongside the session cookie; mutating requests must echo it in the
  ``X-CSRF-Token`` header. Comparison is constant-time.
"""

from collections.abc import Callable

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session as DBSession

from app.auth.service import get_session_user, require_permissions
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.core.security import compare_tokens
from app.models.user import User

UNAUTHENTICATED = ApiError(401, "UNAUTHENTICATED", "Authentication required.")
FORBIDDEN = ApiError(403, "FORBIDDEN", "You do not have permission to perform this action.")
CSRF_FAILED = ApiError(403, "CSRF_FAILED", "CSRF token missing or invalid.")


def _client_ip(request: Request) -> str | None:
    """Return the client IP (first X-Forwarded-For entry or direct peer)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


def get_current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    """Resolve the authenticated user from the session cookie."""
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    resolved = get_session_user(db, token)
    if resolved is None:
        raise UNAUTHENTICATED
    user, _session = resolved
    return user


def require_permission(permission: Permission) -> Callable[..., User]:
    """Build a dependency enforcing ``permission`` (default-deny → 403)."""

    def _dependency(user: User = Depends(get_current_user)) -> User:
        try:
            require_permissions(user, permission)
        except PermissionError:
            raise FORBIDDEN from None
        return user

    return _dependency


def verify_csrf(request: Request) -> None:
    """Validate the double-submit CSRF token for mutating requests."""
    settings = get_settings()
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("x-csrf-token")
    if not cookie_token or not header_token or not compare_tokens(cookie_token, header_token):
        raise CSRF_FAILED


def set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    """Attach session + CSRF cookies to the response.

    ``Secure`` is enabled whenever the app runs outside development
    (behind TLS). ``SameSite=Lax`` blocks cross-site POSTs by default.
    """
    settings = get_settings()
    secure = settings.app_env.lower() != "development"
    max_age = settings.session_absolute_timeout_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,  # JS must read it to echo the header
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age,
    )


def clear_auth_cookies(response: Response) -> None:
    """Expire both auth cookies on the response."""
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
