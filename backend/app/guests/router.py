"""Guest endpoints: registration, search, retrieval, update, deactivation.

Permissions: ``guests.read`` for reads, ``guests.write`` for mutations
(both granted to ADMIN and RECEPTIONIST — operational workflow).
CSRF required on all mutations. Audit written in the same transaction;
audit metadata never contains PII.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission, verify_csrf
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.guests.schemas import GuestCreate, GuestListResponse, GuestPatch, GuestResponse
from app.guests.service import (
    DuplicateGuestError,
    InvalidPhoneError,
    create_guest,
    deactivate_guest,
    search_guests,
    update_guest,
)
from app.models.guest import Guest
from app.models.user import User

router = APIRouter(prefix="/guests", tags=["guests"])


def _serialize(guest: Guest) -> GuestResponse:
    return GuestResponse(
        id=guest.id,
        full_name=guest.full_name,
        phone=guest.phone,
        email=guest.email,
        address=guest.address,
        notes=guest.notes,
        is_active=guest.is_active,
        created_at=guest.created_at,
        updated_at=guest.updated_at,
    )


def _duplicate_error(exc: DuplicateGuestError) -> ApiError:
    return ApiError(
        409,
        "CONFLICT",
        "A guest with this name and phone already exists.",
        {"existing_guest_id": str(exc.existing_id)},
    )


@router.post("", response_model=GuestResponse, status_code=201)
def create_guest_route(
    payload: GuestCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.GUESTS_WRITE)),
) -> GuestResponse:
    """Register a guest (phone normalized to E.164)."""
    verify_csrf(request)
    try:
        guest = create_guest(
            db,
            full_name=payload.full_name,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except InvalidPhoneError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from None
    except DuplicateGuestError as exc:
        raise _duplicate_error(exc) from None
    except IntegrityError:
        db.rollback()
        raise ApiError(
            409,
            "CONFLICT",
            "A guest with this name and phone already exists.",
        ) from None
    db.commit()
    db.refresh(guest)
    return _serialize(guest)


@router.get("", response_model=GuestListResponse)
def list_guests(
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_inactive: bool = False,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.GUESTS_READ)),
) -> GuestListResponse:
    """List guests with optional name/email/phone search."""
    rows, total = search_guests(
        db, query=q, page=page, page_size=page_size, include_inactive=include_inactive
    )
    return GuestListResponse(
        items=[_serialize(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get("/{guest_id}", response_model=GuestResponse)
def get_guest(
    guest_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.GUESTS_READ)),
) -> GuestResponse:
    """Fetch one guest."""
    guest = db.get(Guest, guest_id)
    if guest is None:
        raise ApiError(404, "NOT_FOUND", "Guest not found.")
    return _serialize(guest)


@router.patch("/{guest_id}", response_model=GuestResponse)
def patch_guest(
    guest_id: uuid.UUID,
    payload: GuestPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.GUESTS_WRITE)),
) -> GuestResponse:
    """Update permitted fields. Active status is managed via deactivate."""
    verify_csrf(request)
    guest = db.get(Guest, guest_id)
    if guest is None:
        raise ApiError(404, "NOT_FOUND", "Guest not found.")
    data = payload.model_dump(exclude_unset=True)
    if "is_active" in data:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Active status changes require POST /guests/{id}/deactivate.",
        )
    data.pop("is_active", None)
    try:
        updated = update_guest(db, guest, data=data, actor_user_id=actor.id)
    except InvalidPhoneError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from None
    except DuplicateGuestError as exc:
        raise _duplicate_error(exc) from None
    except IntegrityError:
        db.rollback()
        raise ApiError(
            409,
            "CONFLICT",
            "A guest with this name and phone already exists.",
        ) from None
    db.commit()
    db.refresh(updated)
    return _serialize(updated)


@router.post("/{guest_id}/deactivate", response_model=GuestResponse)
def deactivate_guest_route(
    guest_id: uuid.UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.GUESTS_WRITE)),
) -> GuestResponse:
    """Soft-deactivate a guest (never hard-delete). Idempotent."""
    verify_csrf(request)
    guest = db.get(Guest, guest_id)
    if guest is None:
        raise ApiError(404, "NOT_FOUND", "Guest not found.")
    updated = deactivate_guest(db, guest, actor_user_id=actor.id)
    db.commit()
    db.refresh(updated)
    return _serialize(updated)
