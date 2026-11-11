"""Audit log read API (ADMIN-only).

Exposes existing audit records through a secure, paginated, filterable
read endpoint. No edit, delete, or bulk-clear operations exist — audit
history is append-only by design.

Route: ``GET /api/v1/audit-logs``
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission
from app.audit_logs.schemas import AuditLogEntryResponse, AuditLogListResponse
from app.audit_logs.service import list_audit_logs as _list_audit_logs
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


def _validate_date_range(from_date: date | None, to_date: date | None) -> None:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise ApiError(422, "VALIDATION_ERROR", "from_date must be on or before to_date.")


@router.get(
    "",
    response_model=AuditLogListResponse,
    dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
)
def list_audit_logs(
    from_date: date | None = Query(default=None, description="Filter records from this date (inclusive)."),
    to_date: date | None = Query(default=None, description="Filter records up to this date (inclusive)."),
    actor: str | None = Query(default=None, description="Filter by actor username (case-insensitive substring)."),
    action: str | None = Query(default=None, description="Filter by action name (case-insensitive substring)."),
    resource_type: str | None = Query(default=None, description="Filter by resource type (case-insensitive substring)."),
    resource_id: str | None = Query(default=None, description="Filter by resource ID (case-insensitive substring)."),
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=50, ge=1, le=100, description="Records per page (max 100)."),
    db: DBSession = Depends(get_db),
    actor_user: User = Depends(require_permission(Permission.AUDIT_READ)),
) -> AuditLogListResponse:
    """Return a paginated page of audit records, newest first.

    Access is restricted to ADMIN users via the ``audit.read`` permission.
    A RECEPTIONIST (or any non-ADMIN) receives 403 when calling this
    endpoint directly.
    """
    _validate_date_range(from_date, to_date)
    payload = _list_audit_logs(
        db,
        page=page,
        page_size=page_size,
        from_date=from_date,
        to_date=to_date,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return AuditLogListResponse(**payload)
