"""Authentication routes: login, logout, me, change-password.

All routes are under ``/api/v1/auth`` — mounted by the app factory with the
configured API prefix. There is **no public registration**: accounts are
created only by an ADMIN (users module, later phase) or the one-time
bootstrap command.
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import (
    _client_ip,
    clear_auth_cookies,
    get_current_user,
    set_auth_cookies,
    verify_csrf,
)
from app.auth.rate_limit import clear_attempts, is_rate_limited, register_failed_attempt
from app.auth.schemas import ChangePasswordRequest, LoginRequest, MeResponse
from app.auth.service import (
    LOGIN_FAILED,
    authenticate,
    change_password,
    create_session,
    get_session_user,
    permission_names_for_role,
    revoke_session,
    to_user_response,
    write_audit,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import generate_csrf_token
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = ApiError(401, "INVALID_CREDENTIALS", LOGIN_FAILED)
WRONG_CURRENT_PASSWORD = ApiError(401, "INVALID_CREDENTIALS", "Current password is incorrect.")


@router.post("/login")
def login(
    payload: LoginRequest, request: Request, response: Response, db: DBSession = Depends(get_db)
) -> MeResponse:
    """Authenticate and start a session.

    Session rotation: any previous session cookie is revoked first, so a
    pre-login (possibly fixation-planted) token can never become an
    authenticated one. Failed attempts are audit-logged with IP only —
    never with credentials.
    """
    settings = get_settings()
    old_token = request.cookies.get(settings.session_cookie_name)
    if old_token:
        resolved = get_session_user(db, old_token)
        if resolved is not None:
            _, old_row = resolved
            revoke_session(db, old_row, actor_user_id=old_row.user_id)

    if is_rate_limited(payload.username):
        raise ApiError(
            429,
            "RATE_LIMITED",
            "Too many failed login attempts. Please try again later.",
        )

    user = authenticate(db, payload.username, payload.password)
    if user is None:
        register_failed_attempt(payload.username)
        write_audit(
            db,
            action="AUTH_LOGIN_FAILED",
            resource_type="user",
            resource_id=payload.username,
            ip_address=_client_ip(request),
            metadata={"reason": "invalid_credentials"},
        )
        db.commit()
        raise GENERIC_LOGIN_ERROR

    clear_attempts(payload.username)
    _row, session_token = create_session(
        db,
        user,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    csrf_token = generate_csrf_token()
    set_auth_cookies(response, session_token, csrf_token)
    return MeResponse(
        user=to_user_response(user),
        permissions=permission_names_for_role(user.role),
    )


@router.post("/logout")
def logout(request: Request, response: Response, db: DBSession = Depends(get_db)) -> dict[str, str]:
    """Revoke the current session and clear auth cookies. Idempotent."""
    verify_csrf(request)
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        resolved = get_session_user(db, token)
        if resolved is not None:
            user, row = resolved
            revoke_session(db, row, actor_user_id=user.id)
    clear_auth_cookies(response)
    return {"status": "logged_out"}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> MeResponse:
    """Return the currently authenticated user and their permissions."""
    return MeResponse(
        user=to_user_response(user),
        permissions=permission_names_for_role(user.role),
    )


@router.post("/change-password")
def change_password_route(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict[str, str]:
    """Change the caller's password; all other sessions are revoked."""
    verify_csrf(request)
    ok = change_password(db, user, payload.current_password, payload.new_password)
    if not ok:
        raise WRONG_CURRENT_PASSWORD
    return {"status": "password_changed"}
