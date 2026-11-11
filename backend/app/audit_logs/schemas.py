"""Pydantic schemas for the audit log read API.

All money-free, PII-minimal. Metadata is sanitised before it reaches
the client so that secrets accidentally written to ``metadata_json`` are
never exposed through this endpoint.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditLogEntryResponse(BaseModel):
    """One sanitised audit-log record."""

    id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    actor_username: str | None = None
    action: str = Field(max_length=64)
    resource_type: str = Field(max_length=64)
    resource_id: str = Field(max_length=128)
    metadata: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated audit-log listing, newest first."""

    items: list[AuditLogEntryResponse]
    total: int
    page: int
    page_size: int
