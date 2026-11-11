"""Authentication service — session lifecycle and credential checks.

All functions take an explicit ``Session`` (SQLAlchemy session) so callers
control transactions. Nothing here logs passwords or plaintext tokens.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.schemas import UserResponse
from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.core.permissions import Permission, permissions_for_role
from app.core.security import generate_session_token, hash_password, hash_token, verify_password
from app.models.audit import AuditLog
from app.models.session import Session as SessionModel
from app.models.user import User

logger = get_logger(__name__)

# Generic response for every credential failure — reveals nothing about
# whether the username exists, the password was wrong, or the account is
# inactive.
LOGIN_FAILED = "Invalid username or password."


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """Normalise a DB datetime to timezone-aware UTC.

    PostgreSQL returns aware datetimes (TIMESTAMPTZ); SQLite returns naive
    ones. Treating naive values as UTC keeps comparisons well-defined on
    both backends.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def write_audit(
    db: DBSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    actor_user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Append an audit-log row. Metadata must contain no secrets."""
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=metadata,
            ip_address=ip_address,
        )
    )


def authenticate(db: DBSession, username: str, password: str) -> User | None:
    """Verify credentials; return the user or None (generic failure).

    Inactive accounts are rejected with the same generic result as a bad
    password.
    """
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_session(
    db: DBSession,
    user: User,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[SessionModel, str]:
    """Create a persisted session; return (row, plaintext_token).

    The plaintext token is returned once for the Set-Cookie header and is
    never stored — only its hash is persisted.
    """
    settings = get_settings()
    now = _utcnow()
    token = generate_session_token()
    row = SessionModel(
        user_id=user.id,
        session_token_hash=hash_token(token),
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_absolute_timeout_hours),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(row)
    db.flush()
    user.last_login_at = now
    write_audit(
        db,
        action="AUTH_LOGIN",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
        ip_address=ip_address,
    )
    db.commit()  # Session is a security boundary: persist immediately.
    return row, token


def get_session_user(db: DBSession, token: str | None) -> tuple[User, SessionModel] | None:
    """Resolve a plaintext session token to (user, session) if valid.

    Returns None for missing/unknown/revoked/expired/idle-timed-out tokens.
    Expired or idle sessions are revoked in place so they cannot be reused.
    """
    if not token:
        return None
    settings = get_settings()
    now = _utcnow()
    row = db.scalar(
        select(SessionModel).where(SessionModel.session_token_hash == hash_token(token))
    )
    if row is None or row.revoked_at is not None:
        return None
    if _aware(row.expires_at) <= now:
        row.revoked_at = now
        db.commit()
        return None
    idle_deadline = _aware(row.last_seen_at) + timedelta(
        minutes=settings.session_idle_timeout_minutes
    )
    if idle_deadline <= now:
        row.revoked_at = now
        db.commit()
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        row.revoked_at = now
        db.commit()
        return None
    row.last_seen_at = now
    db.commit()
    return user, row


def revoke_session(db: DBSession, row: SessionModel, *, actor_user_id: uuid.UUID | None) -> None:
    """Revoke (logout) a session. Idempotent.

    This function commits the transaction independently of its caller.
    It is invoked from ``login()`` to revoke any pre-existing session
    before a new one is issued (session-fixation protection). Because the
    revocation must persist even if the subsequent login fails, the
    AUTH_LOGOUT audit row is committed here rather than being folded into
    the login transaction. Consequently, an AUTH_LOGOUT audit event may
    exist even when the following login attempt fails — this is by design,
    not a defect.
    """
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
        write_audit(
            db,
            action="AUTH_LOGOUT",
            resource_type="session",
            resource_id=str(row.id),
            actor_user_id=actor_user_id,
        )
        db.commit()


def revoke_user_sessions(
    db: DBSession, user_id: uuid.UUID, *, actor_user_id: uuid.UUID | None = None
) -> int:
    """Revoke every live session for a user (password change / deactivation).

    Returns the number of sessions revoked.
    """
    rows = db.scalars(
        select(SessionModel).where(
            SessionModel.user_id == user_id,
            SessionModel.revoked_at.is_(None),
        )
    ).all()
    now = _utcnow()
    for row in rows:
        row.revoked_at = now
    write_audit(
        db,
        action="SESSIONS_REVOKED",
        resource_type="user",
        resource_id=str(user_id),
        actor_user_id=actor_user_id,
        metadata={"count": len(rows)},
    )
    db.commit()
    return len(rows)


def change_password(db: DBSession, user: User, current_password: str, new_password: str) -> bool:
    """Change a user's password after verifying the current one.

    On success also revokes all other live sessions for the user.
    Returns False when the current password does not match.
    """
    if not verify_password(current_password, user.password_hash):
        return False
    user.password_hash = hash_password(new_password)
    write_audit(
        db,
        action="PASSWORD_CHANGED",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
    )
    db.commit()
    revoke_user_sessions(db, user.id, actor_user_id=user.id)
    return True


def to_user_response(user: User) -> UserResponse:
    """Convert a User row to the safe API representation."""
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
    )


def permission_names_for_role(role: str) -> list[str]:
    """Return sorted permission names for a role (for /auth/me)."""
    return sorted(p.value for p in permissions_for_role(role))


def require_permissions(user: User, required: Permission) -> None:
    """Raise PermissionError when the user lacks the permission.

    Used by route handlers through the ``require_permission`` dependency.
    """
    if required not in permissions_for_role(user.role):
        raise PermissionError(required.value)


def ensure_not_last_active_admin(
    db: DBSession, *, excluding_user_id: uuid.UUID | None = None
) -> bool:
    """Return True when at least one OTHER active ADMIN exists.

    Implements RBAC hard rule 4: the final active ADMIN can never be
    deactivated. Admin-creation flows in the users module use this guard
    before deactivating an ADMIN account.
    """
    stmt = select(User).where(User.role == "ADMIN", User.is_active.is_(True))
    if excluding_user_id is not None:
        stmt = stmt.where(User.id != excluding_user_id)
    return db.scalar(stmt) is not None
