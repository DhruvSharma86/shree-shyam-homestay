"""Pydantic schemas for the guest endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GuestResponse(BaseModel):
    """Safe guest representation — never includes internal or sensitive fields."""

    id: uuid.UUID
    full_name: str
    phone: str
    email: str | None = None
    address: str | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GuestCreate(BaseModel):
    """Create a guest. Phone is normalized to E.164."""

    full_name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=7, max_length=24)
    email: str | None = Field(
        default=None,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        max_length=255,
    )
    address: str | None = None
    notes: str | None = None


class GuestPatch(BaseModel):
    """Partial guest update. Protected fields (id, timestamps, ownership,
    active status) are not accepted here — use POST /{id}/deactivate."""

    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, min_length=7, max_length=24)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class GuestListResponse(BaseModel):
    """Paginated guest list."""

    items: list[GuestResponse]
    total: int
    page: int
    page_size: int
