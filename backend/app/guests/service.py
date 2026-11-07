"""Guest business logic — normalization, duplicate detection, CRUD.

Route handlers stay thin: validate (Pydantic) → authorize (RBAC) → call
service → serialize. All writes run in the caller's transaction and write an
audit row. Audit metadata contains field names only — never names, phones,
emails, addresses or notes (PII minimization).
"""

import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.auth.service import write_audit
from app.models.guest import Guest

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class DuplicateGuestError(ValueError):
    """Raised when an exact name+phone match already exists."""

    def __init__(self, existing_id: uuid.UUID) -> None:
        super().__init__("A guest with this name and phone already exists.")
        self.existing_id = existing_id


class InvalidPhoneError(ValueError):
    """Raised when a phone cannot be normalized to E.164."""


def normalize_phone(raw: str) -> str:
    """Normalize a phone to E.164 (+<country><digits>).

    Strips spaces/dashes/parens/dots. ``00`` → ``+``. Leading ``0`` on an
    11-digit number and bare 10-digit numbers are assumed Indian (+91) —
    the property is Indian and SRS records phone as the practical ID.
    Long international numbers without ``+`` are assumed already
    international only when they are 11–15 digits starting non-zero.
    """
    cleaned = re.sub(r"[\s\-().]", "", (raw or "").strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if re.fullmatch(r"0\d{10}", cleaned):
        cleaned = "+91" + cleaned[1:]
    elif re.fullmatch(r"\d{10}", cleaned):
        cleaned = "+91" + cleaned
    elif re.fullmatch(r"\d{11,15}", cleaned):
        cleaned = "+" + cleaned
    if not _E164_RE.match(cleaned):
        raise InvalidPhoneError("Phone number is invalid. Use E.164 format (e.g. +919876543210).")
    return cleaned


def is_valid_phone(raw: str) -> bool:
    """Return True when ``raw`` normalizes to valid E.164."""
    try:
        normalize_phone(raw)
        return True
    except InvalidPhoneError:
        return False


def _canonical_name(name: str) -> str:
    """Collapse internal whitespace and strip (used for storage + matching)."""
    return " ".join((name or "").split())


def find_exact_duplicate(
    db: DBSession, *, full_name: str, phone: str, exclude_id: uuid.UUID | None = None
) -> Guest | None:
    """Return an active guest with the same normalized phone and same name."""
    canonical = _canonical_name(full_name)
    stmt = select(Guest).where(
        Guest.phone == phone,
        func.lower(Guest.full_name) == canonical.lower(),
        Guest.is_active.is_(True),
    )
    if exclude_id is not None:
        stmt = stmt.where(Guest.id != exclude_id)
    return db.scalar(stmt)


def create_guest(
    db: DBSession,
    *,
    full_name: str,
    phone: str,
    email: str | None,
    address: str | None,
    notes: str | None,
    actor_user_id: uuid.UUID,
) -> Guest:
    """Create a guest. Raises DuplicateGuestError / InvalidPhoneError."""
    normalized = normalize_phone(phone)
    duplicate = find_exact_duplicate(db, full_name=full_name, phone=normalized)
    if duplicate is not None:
        raise DuplicateGuestError(duplicate.id)
    row = Guest(
        full_name=_canonical_name(full_name),
        phone=normalized,
        email=email.strip() if email else None,
        address=address,
        notes=notes,
        is_active=True,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="GUEST_CREATED",
        resource_type="guest",
        resource_id=str(row.id),
        actor_user_id=actor_user_id,
        metadata={"fields": ["full_name", "phone"] + (["email"] if email else [])},
    )
    return row


def search_guests(
    db: DBSession,
    *,
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
    include_inactive: bool = False,
) -> tuple[list[Guest], int]:
    """Search guests by name/email/phone with pagination."""
    stmt = select(Guest)
    if not include_inactive:
        stmt = stmt.where(Guest.is_active.is_(True))
    if query and query.strip():
        q = query.strip()
        candidates: list = []
        try:
            normalized = normalize_phone(q)
            candidates.append(Guest.phone == normalized)
        except InvalidPhoneError:
            pass
        candidates.extend(
            [
                Guest.full_name.ilike(f"%{q}%"),
                Guest.email.ilike(f"%{q}%"),
                Guest.phone.ilike(f"%{q}%"),
            ]
        )
        stmt = stmt.where(or_(*candidates))
    count_subq = stmt.with_only_columns(Guest.id).subquery()
    total_raw = db.scalar(select(func.count()).select_from(count_subq))
    total = int(total_raw) if total_raw is not None else 0
    rows = db.scalars(
        stmt.order_by(Guest.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), total


def update_guest(db: DBSession, guest: Guest, *, data: dict, actor_user_id: uuid.UUID) -> Guest:
    """Apply partial updates. Phone changes re-check duplicates."""
    if "phone" in data and data["phone"] is not None:
        normalized = normalize_phone(data["phone"])
        candidate_name = data.get("full_name") or guest.full_name
        duplicate = find_exact_duplicate(
            db, full_name=candidate_name, phone=normalized, exclude_id=guest.id
        )
        if duplicate is not None:
            raise DuplicateGuestError(duplicate.id)
        data = {**data, "phone": normalized}
    for field, value in data.items():
        if value is not None:
            setattr(guest, field, value)
    guest.updated_by = actor_user_id
    write_audit(
        db,
        action="GUEST_UPDATED",
        resource_type="guest",
        resource_id=str(guest.id),
        actor_user_id=actor_user_id,
        metadata={"fields": sorted(data.keys())},
    )
    return guest


def deactivate_guest(db: DBSession, guest: Guest, *, actor_user_id: uuid.UUID) -> Guest:
    """Soft-deactivate a guest (never hard-delete). Idempotent."""
    if guest.is_active:
        guest.is_active = False
        guest.updated_by = actor_user_id
        write_audit(
            db,
            action="GUEST_DEACTIVATED",
            resource_type="guest",
            resource_id=str(guest.id),
            actor_user_id=actor_user_id,
            metadata={"fields": ["is_active"]},
        )
    return guest
