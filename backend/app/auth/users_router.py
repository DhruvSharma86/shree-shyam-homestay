"""User management routes (ADMIN only: ``users.manage``).

These are the ONLY endpoints that create, modify, or deactivate accounts.
There is no public registration anywhere in the system.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission, verify_csrf
from app.auth.schemas import UserResponse
from app.auth.service import (
    ensure_not_last_active_admin,
    revoke_user_sessions,
    to_user_response,
    write_audit,
)
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.core.security import hash_password
from app.models.user import User, UserRole

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserRequest(BaseModel):
    """Payload for POST /users (ADMIN-created account)."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    full_name: str = Field(min_length=1, max_length=120)
    role: str = "RECEPTIONIST"
    email: str | None = Field(default=None, max_length=255)


class UpdateUserRequest(BaseModel):
    """Payload for PATCH /users/{id} (partial account update)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    """Payload for POST /users/{id}/reset-password (ADMIN-initiated)."""

    new_password: str = Field(min_length=10, max_length=256)


def _get_user_or_404(db: DBSession, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "NOT_FOUND", "User not found.")
    return user


@router.get(
    "",
    response_model=list[UserResponse],
    dependencies=[Depends(require_permission(Permission.USERS_MANAGE))],
)
def list_users(db: DBSession = Depends(get_db)) -> list[UserResponse]:
    """List all staff accounts."""
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return [to_user_response(u) for u in users]


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> UserResponse:
    """Create a staff account (ADMIN only)."""
    verify_csrf(request)
    if payload.role not in {UserRole.ADMIN.value, UserRole.RECEPTIONIST.value}:
        raise ApiError(422, "VALIDATION_ERROR", "Role must be ADMIN or RECEPTIONIST.")
    if db.scalar(select(User).where(User.username == payload.username)):
        raise ApiError(409, "CONFLICT", "Username already exists.")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        email=payload.email,
        is_active=True,
        created_by=actor.id,
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        action="USER_CREATED",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=actor.id,
        metadata={"username": user.username, "role": user.role},
    )
    db.commit()
    return to_user_response(user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> UserResponse:
    """Fetch one staff account."""
    return to_user_response(_get_user_or_404(db, user_id))


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> UserResponse:
    """Update an account: name, email, or active status.

    Deactivating the final active ADMIN is blocked (RBAC hard rule 4), and
    deactivation revokes that user's live sessions.
    """
    verify_csrf(request)
    user = _get_user_or_404(db, user_id)
    if payload.is_active is False and user.role == UserRole.ADMIN.value and user.is_active:
        if not ensure_not_last_active_admin(db, excluding_user_id=user.id):
            raise ApiError(409, "CONFLICT", "Cannot deactivate the last active ADMIN account.")
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.email is not None:
        user.email = payload.email
    if payload.is_active is not None:
        user.is_active = payload.is_active
    write_audit(
        db,
        action="USER_UPDATED",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=actor.id,
        metadata={
            "full_name": payload.full_name,
            "email": payload.email,
            "is_active": payload.is_active,
        },
    )
    db.commit()
    if payload.is_active is False:
        revoke_user_sessions(db, user.id, actor_user_id=actor.id)
    return to_user_response(user)


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: uuid.UUID,
    payload: ResetPasswordRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_RESET_CREDENTIALS)),
) -> dict[str, str]:
    """ADMIN-initiated password reset; revokes the target's sessions."""
    verify_csrf(request)
    user = _get_user_or_404(db, user_id)
    user.password_hash = hash_password(payload.new_password)
    write_audit(
        db,
        action="PASSWORD_RESET",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=actor.id,
    )
    db.commit()
    revoke_user_sessions(db, user.id, actor_user_id=actor.id)
    return {"status": "password_reset"}


@router.delete("/{user_id}", status_code=204)
def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> None:
    """Deactivate (never hard-delete) a staff account."""
    verify_csrf(request)
    user = _get_user_or_404(db, user_id)
    if user.role == UserRole.ADMIN.value and user.is_active:
        if not ensure_not_last_active_admin(db, excluding_user_id=user.id):
            raise ApiError(409, "CONFLICT", "Cannot deactivate the last active ADMIN account.")
    user.is_active = False
    write_audit(
        db,
        action="USER_DEACTIVATED",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=actor.id,
    )
    db.commit()
    revoke_user_sessions(db, user.id, actor_user_id=actor.id)
