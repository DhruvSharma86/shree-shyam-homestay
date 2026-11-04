"""Request/response schemas for the auth endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials submitted to POST /auth/login."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    """Password change submitted to POST /auth/change-password."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class UserResponse(BaseModel):
    """Safe user representation — never includes password material."""

    id: UUID
    username: str
    email: str | None = None
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None


class MeResponse(BaseModel):
    """Current-user payload for GET /auth/me."""

    user: UserResponse
    permissions: list[str]
