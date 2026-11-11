"""Read-only audit-log service.

Audit records are append-only and immutable. This module only reads —
no edit, delete, or bulk-clear operations exist by design.

Metadata sanitisation: keys whose names suggest secrets (passwords,
tokens, CSRF tokens, session material, credentials, keys) are replaced
with ``"[REDACTED]"`` before the record is returned to the client. This
defends against secrets that may have been written to ``metadata_json``
by older or less careful call sites, even though ``write_audit`` itself
relies on callers to pass safe context.
"""

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession, joinedload

from app.models.audit import AuditLog
from app.models.user import User


# Metadata keys whose values are treated as secrets and redacted.
# Matches are case-insensitive on the key name.
SENSITIVE_METADATA_KEYS: frozenset[str] = frozenset({
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "session_token",
    "csrf",
    "csrf_token",
    "session",
    "cookie",
    "secret",
    "api_key",
    "private_key",
    "credential",
    "authorization",
    "auth",
    "key",
})


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of ``metadata`` with sensitive keys redacted.

    Nested dicts are sanitised recursively. Non-dict values are passed
    through unchanged. Returns ``None`` when input is ``None``.
    """
    if metadata is None:
        return None
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if key.lower() in SENSITIVE_METADATA_KEYS:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_metadata(value)
        else:
            sanitized[key] = value
    return sanitized


def _apply_filters(stmt, from_date: date | None, to_date: date | None,
                   actor: str | None, action: str | None,
                   resource_type: str | None, resource_id: str | None):
    """Apply date, actor, action, and resource filters to the statement.

    The statement already includes a LEFT OUTER JOIN to ``users`` (added in
    ``list_audit_logs``), so this function only adds WHERE clauses — it
    must not join again.
    """
    from app.models.user import User

    if from_date is not None:
        start = datetime.combine(from_date, time.min)
        stmt = stmt.where(AuditLog.created_at >= start)
    if to_date is not None:
        end = datetime.combine(to_date, time.max)
        stmt = stmt.where(AuditLog.created_at <= end)
    if actor is not None and actor.strip():
        stmt = stmt.where(User.username.ilike(f"%{actor.strip()}%"))
    if action is not None and action.strip():
        stmt = stmt.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if resource_type is not None and resource_type.strip():
        stmt = stmt.where(AuditLog.resource_type.ilike(f"%{resource_type.strip()}%"))
    if resource_id is not None and resource_id.strip():
        stmt = stmt.where(AuditLog.resource_id.ilike(f"%{resource_id.strip()}%"))
    return stmt


def list_audit_logs(
    db: DBSession,
    *,
    page: int,
    page_size: int,
    from_date: date | None = None,
    to_date: date | None = None,
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> dict[str, Any]:
    """Return a paginated, reverse-chronological page of audit records.

    Ordering is deterministic: ``created_at DESC, id DESC`` so that
    records sharing the same timestamp still have a stable order.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    max_page_size = 100
    if page_size > max_page_size:
        page_size = max_page_size

    # Base query with a left join to User so we can surface the actor's
    # username without N+1 lookups.
    base = (
        select(
            AuditLog.id,
            AuditLog.actor_user_id,
            User.username.label("actor_username"),
            AuditLog.action,
            AuditLog.resource_type,
            AuditLog.resource_id,
            AuditLog.metadata_json,
            AuditLog.ip_address,
            AuditLog.created_at,
        )
        .select_from(AuditLog)
        .outerjoin(User, AuditLog.actor_user_id == User.id)
    )
    base = _apply_filters(
        base, from_date, to_date, actor, action, resource_type, resource_id
    )

    # Total count before pagination.
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    # Deterministic ordering: newest first, then by id for ties.
    ordered = base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    rows = db.execute(ordered.offset((page - 1) * page_size).limit(page_size)).all()

    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "actor_user_id": row.actor_user_id,
            "actor_username": row.actor_username,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "metadata": _sanitize_metadata(row.metadata_json),
            "ip_address": row.ip_address,
            "created_at": row.created_at,
        })

    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }
