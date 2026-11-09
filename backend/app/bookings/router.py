"""Booking endpoints: creation, listing, retrieval, updates, cancellation,
and availability. See app/bookings/service.py for business rules.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission, verify_csrf
from app.bookings.schemas import (
    AvailabilityResponse,
    BookingCancel,
    BookingCreate,
    BookingListResponse,
    BookingPatch,
    BookingResponse,
    CheckInRequest,
)
from app.bookings.service import (
    BookingOverlapError,
    GuestInactiveError,
    RateUnavailableError,
    RoomUnavailableError,
    cancel_booking,
    check_availability,
    check_in_booking,
    create_booking,
    update_booking,
)
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.booking import Booking
from app.models.room import Room
from app.models.user import User

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _serialize(row: Booking) -> BookingResponse:
    return BookingResponse(
        id=row.id,
        booking_ref=row.booking_ref,
        guest_id=row.guest_id,
        room_id=row.room_id,
        room_type_id=row.room_type_id,
        status=row.status,
        source=row.source,
        check_in_date=row.check_in_date,
        check_out_date=row.check_out_date,
        nights=row.nights,
        number_of_guests=row.number_of_guests,
        notes=row.notes,
        night_rate_snapshot=row.night_rate_snapshot,
        rate_id=row.rate_id,
        room_subtotal=row.room_subtotal,
        tax_type_snapshot=row.tax_type_snapshot,
        tax_rate_snapshot=row.tax_rate_snapshot,
        tax_pricing_mode_snapshot=row.tax_pricing_mode_snapshot,
        total_amount=row.total_amount,
        cancelled_at=row.cancelled_at.isoformat() if row.cancelled_at else None,
        cancellation_reason=row.cancellation_reason,
    )


def _map_service_error(exc: Exception) -> ApiError:
    if isinstance(exc, BookingOverlapError):
        return ApiError(409, "CONFLICT", str(exc))
    if isinstance(exc, RoomUnavailableError):
        return ApiError(422, "VALIDATION_ERROR", str(exc))
    if isinstance(exc, GuestInactiveError):
        return ApiError(422, "VALIDATION_ERROR", str(exc))
    if isinstance(exc, RateUnavailableError):
        return ApiError(422, "VALIDATION_ERROR", str(exc))
    if isinstance(exc, ValueError):
        return ApiError(422, "VALIDATION_ERROR", str(exc))
    raise exc


@router.post("", response_model=BookingResponse, status_code=201)
def create_booking_route(
    payload: BookingCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BOOKINGS_WRITE)),
) -> BookingResponse:
    """Create a CONFIRMED booking (phone/walk-in only)."""
    verify_csrf(request)
    try:
        booking = create_booking(
            db,
            guest_id=payload.guest_id,
            room_id=payload.room_id,
            source=payload.source,
            check_in_date=payload.check_in_date,
            check_out_date=payload.check_out_date,
            number_of_guests=payload.number_of_guests,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except (
        BookingOverlapError,
        RoomUnavailableError,
        GuestInactiveError,
        RateUnavailableError,
        ValueError,
    ) as exc:
        raise _map_service_error(exc) from None
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "CONFLICT", "Room is already booked for the requested dates.") from None
    db.commit()
    db.refresh(booking)
    return _serialize(booking)


@router.get("", response_model=BookingListResponse)
def list_bookings(
    status: str | None = None,
    guest_id: uuid.UUID | None = None,
    room_id: uuid.UUID | None = None,
    check_in_from: date | None = None,
    check_in_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BOOKINGS_READ)),
) -> BookingListResponse:
    """List bookings with status/guest/room/date filters."""
    stmt = select(Booking)
    if status:
        stmt = stmt.where(Booking.status == status)
    if guest_id:
        stmt = stmt.where(Booking.guest_id == guest_id)
    if room_id:
        stmt = stmt.where(Booking.room_id == room_id)
    if check_in_from:
        stmt = stmt.where(Booking.check_in_date >= check_in_from)
    if check_in_to:
        stmt = stmt.where(Booking.check_in_date <= check_in_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Booking.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return BookingListResponse(
        items=[_serialize(r) for r in rows], total=int(total), page=page, page_size=page_size
    )


@router.get("/availability", response_model=list[AvailabilityResponse])
def availability_all(
    check_in: date,
    check_out: date,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BOOKINGS_READ)),
) -> list[AvailabilityResponse]:
    """Check availability across all operational rooms."""
    if check_out <= check_in:
        raise ApiError(422, "VALIDATION_ERROR", "check_out must be later than check_in.")
    rooms = db.scalars(
        select(Room).where(
            Room.is_active.is_(True),
            Room.operational_status == "AVAILABLE",
        )
    ).all()
    return [
        AvailabilityResponse(
            room_id=r.id,
            available=check_availability(db, room_id=r.id, check_in=check_in, check_out=check_out),
            check_in_date=check_in,
            check_out_date=check_out,
        )
        for r in rooms
    ]


@router.get("/availability/{room_id}", response_model=AvailabilityResponse)
def availability(
    room_id: uuid.UUID,
    check_in: date,
    check_out: date,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BOOKINGS_READ)),
) -> AvailabilityResponse:
    """Check whether a room is available for [check_in, check_out)."""
    if check_out <= check_in:
        raise ApiError(422, "VALIDATION_ERROR", "check_out must be later than check_in.")
    available = check_availability(db, room_id=room_id, check_in=check_in, check_out=check_out)
    return AvailabilityResponse(
        room_id=room_id, available=available, check_in_date=check_in, check_out_date=check_out
    )


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(
    booking_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BOOKINGS_READ)),
) -> BookingResponse:
    """Fetch one booking."""
    row = db.get(Booking, booking_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Booking not found.")
    return _serialize(row)


@router.patch("/{booking_id}", response_model=BookingResponse)
def patch_booking(
    booking_id: uuid.UUID,
    payload: BookingPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BOOKINGS_WRITE)),
) -> BookingResponse:
    """Update dates/room/notes on a CONFIRMED booking."""
    verify_csrf(request)
    row = db.get(Booking, booking_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Booking not found.")
    try:
        updated = update_booking(
            db,
            row,
            check_in_date=payload.check_in_date,
            check_out_date=payload.check_out_date,
            room_id=payload.room_id,
            number_of_guests=payload.number_of_guests,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except (
        BookingOverlapError,
        RoomUnavailableError,
        GuestInactiveError,
        RateUnavailableError,
        ValueError,
    ) as exc:
        raise _map_service_error(exc) from None
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "CONFLICT", "Room is already booked for the requested dates.") from None
    db.commit()
    db.refresh(updated)
    return _serialize(updated)


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
def cancel_booking_route(
    booking_id: uuid.UUID,
    payload: BookingCancel | None = None,
    request: Request = None,  # type: ignore[assignment]
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BOOKINGS_CANCEL)),
) -> BookingResponse:
    """Cancel a CONFIRMED booking (idempotent, never deletes)."""
    verify_csrf(request)  # type: ignore[arg-type]
    row = db.get(Booking, booking_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Booking not found.")
    updated = cancel_booking(
        db, row, reason=payload.reason if payload else None, actor_user_id=actor.id
    )
    db.commit()
    db.refresh(updated)
    return _serialize(updated)


@router.post("/{booking_id}/check-in", response_model=BookingResponse)
def check_in_booking_route(
    booking_id: uuid.UUID,
    payload: CheckInRequest | None = None,
    request: Request = None,  # type: ignore[assignment]
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BOOKINGS_CHECKIN)),
) -> BookingResponse:
    """Check in a CONFIRMED booking (mandatory one-night CHECK_IN payment)."""
    verify_csrf(request)  # type: ignore[arg-type]
    row = db.get(Booking, booking_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Booking not found.")
    try:
        updated = check_in_booking(db, row, actor_user_id=actor.id)
    except (
        BookingOverlapError,
        RoomUnavailableError,
        GuestInactiveError,
        RateUnavailableError,
        ValueError,
    ) as exc:
        raise _map_service_error(exc) from None
    db.commit()
    db.refresh(updated)
    return _serialize(updated)
