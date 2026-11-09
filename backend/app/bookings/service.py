"""Booking business logic — availability, snapshots, lifecycle.

Date convention (everywhere): check-in inclusive, check-out exclusive.
Overlap test: ``existing.check_in < new.check_out AND existing.check_out > new.check_in``.

Single-rate policy: exactly one room-rate version must cover the whole
stay (valid_from ≤ check_in and valid_until ≥ check_out − 1day). A rate
version starting inside the stay is rejected — staff must first adjust
rate validity; the system never silently blends rates across a stay.

Tax snapshot: the tax configuration covering check-in is copied
(type/rate/mode). Default when none is configured: NONE / null / EXCLUSIVE
with no tax amount (calculation belongs to billing, Phase 4).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.service import write_audit
from app.models.booking import Booking, BookingSource, BookingStatus
from app.models.guest import Guest
from app.models.room import Room, RoomOperationalStatus
from app.models.room_rate import RoomRate
from app.models.tax_settings import TaxSettings


class BookingOverlapError(ValueError):
    """Raised when the room already has a conflicting active booking."""


class RoomUnavailableError(ValueError):
    """Raised when the room is inactive or under maintenance."""


class GuestInactiveError(ValueError):
    """Raised when the guest is missing or deactivated."""


class RateUnavailableError(ValueError):
    """Raised when no single rate covers the whole stay."""


def _today() -> date:
    return datetime.now(UTC).date()


def _overlaps(a_in: date, a_out: date, b_in: date, b_out: date) -> bool:
    return a_in < b_out and b_in < a_out


def _active_overlap(
    db: DBSession,
    *,
    room_id: uuid.UUID,
    check_in: date,
    check_out: date,
    exclude_id: uuid.UUID | None,
) -> Booking | None:
    stmt = (
        select(Booking)
        .where(
            Booking.room_id == room_id,
            Booking.status == BookingStatus.CONFIRMED,
            Booking.check_in_date < check_out,
            Booking.check_out_date > check_in,
        )
        .order_by(Booking.check_in_date)
        .limit(1)
    )
    if exclude_id is not None:
        stmt = stmt.where(Booking.id != exclude_id)
    return db.scalar(stmt)


def _resolve_rate(
    db: DBSession, *, room_type_id: uuid.UUID, check_in: date, check_out: date
) -> RoomRate:
    last_night = check_out - timedelta(days=1)
    covering = db.scalars(
        select(RoomRate).where(
            RoomRate.room_type_id == room_type_id,
            RoomRate.is_active.is_(True),
            RoomRate.valid_from <= check_in,
            RoomRate.valid_until.is_(None) | (RoomRate.valid_until >= last_night),
        )
    ).all()
    if not covering:
        raise RateUnavailableError(
            "No active room rate covers the requested stay. "
            "Configure a rate valid across the full stay first."
        )
    # Mid-stay rate change: another version starting inside the stay.
    mid = db.scalars(
        select(RoomRate).where(
            RoomRate.room_type_id == room_type_id,
            RoomRate.is_active.is_(True),
            RoomRate.valid_from > check_in,
            RoomRate.valid_from <= last_night,
        )
    ).all()
    if mid:
        raise RateUnavailableError(
            "A room rate changes during the requested stay. "
            "Adjust rate validity so one rate covers the entire stay."
        )
    # Multiple covering rows (should not happen with overlap guard, but safe).
    ordered = sorted(covering, key=lambda r: r.valid_from)
    return ordered[0]


def _resolve_tax(db: DBSession, *, check_in: date) -> tuple[str, Decimal | None, str]:
    row = db.scalar(
        select(TaxSettings).where(
            TaxSettings.valid_from <= check_in,
            TaxSettings.valid_until.is_(None) | (TaxSettings.valid_until >= check_in),
        )
    )
    if row is None:
        return "NONE", None, "EXCLUSIVE"
    return row.tax_type, row.tax_rate, row.pricing_mode


def lock_room(db: DBSession, room_id: uuid.UUID) -> Room | None:
    """Lock the room row (PG: real lock; SQLite: serializable writes)."""
    return db.scalar(select(Room).where(Room.id == room_id).with_for_update())


def check_availability(
    db: DBSession,
    *,
    room_id: uuid.UUID,
    check_in: date,
    check_out: date,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Return True when the room can be booked for [check_in, check_out)."""
    room = db.get(Room, room_id)
    if (
        room is None
        or not room.is_active
        or room.operational_status != RoomOperationalStatus.AVAILABLE
    ):
        return False
    return (
        _active_overlap(
            db, room_id=room_id, check_in=check_in, check_out=check_out, exclude_id=exclude_id
        )
        is None
    )


def _snapshot_totals(rate: Decimal, nights: int) -> tuple[Decimal, Decimal]:
    subtotal = (rate * Decimal(nights)).quantize(Decimal("0.01"))
    return subtotal, subtotal


def create_booking(
    db: DBSession,
    *,
    guest_id: uuid.UUID,
    room_id: uuid.UUID,
    source: str,
    check_in_date: date,
    check_out_date: date,
    number_of_guests: int,
    notes: str | None,
    actor_user_id: uuid.UUID,
) -> Booking:
    """Create a CONFIRMED booking with full snapshot. Caller commits."""
    if check_out_date <= check_in_date:
        raise ValueError("check_out_date must be later than check_in_date.")
    if check_in_date < _today():
        raise ValueError("Bookings in the past are not allowed.")
    guest = db.get(Guest, guest_id)
    if guest is None or not guest.is_active:
        raise GuestInactiveError("Guest does not exist or is deactivated.")
    # Serialize concurrent attempts on the same room.
    room = lock_room(db, room_id)
    if room is None:
        raise ValueError("Room not found.")
    if not room.is_active or room.operational_status != RoomOperationalStatus.AVAILABLE:
        raise RoomUnavailableError("Room is inactive or under maintenance.")
    if source not in (BookingSource.PHONE, BookingSource.WALK_IN):
        raise ValueError("source must be PHONE or WALK_IN.")
    overlap = _active_overlap(
        db, room_id=room_id, check_in=check_in_date, check_out=check_out_date, exclude_id=None
    )
    if overlap is not None:
        raise BookingOverlapError("Room is already booked for the requested dates.")
    rate = _resolve_rate(
        db, room_type_id=room.room_type_id, check_in=check_in_date, check_out=check_out_date
    )
    nights = (check_out_date - check_in_date).days
    subtotal, total = _snapshot_totals(rate.nightly_rate, nights)
    tax_type, tax_rate, tax_mode = _resolve_tax(db, check_in=check_in_date)
    booking = Booking(
        booking_ref=f"SSH-{uuid.uuid4().hex[:8].upper()}",
        guest_id=guest_id,
        room_id=room_id,
        room_type_id=room.room_type_id,
        status=BookingStatus.CONFIRMED,
        source=source,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        nights=nights,
        number_of_guests=number_of_guests,
        notes=notes,
        night_rate_snapshot=rate.nightly_rate,
        rate_id=rate.id,
        room_subtotal=subtotal,
        tax_type_snapshot=tax_type,
        tax_rate_snapshot=tax_rate,
        tax_pricing_mode_snapshot=tax_mode,
        total_amount=total,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(booking)
    db.flush()
    write_audit(
        db,
        action="BOOKING_CREATED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={"fields": ["guest_id", "room_id", "check_in_date", "check_out_date"]},
    )
    return booking


def update_booking(
    db: DBSession,
    booking: Booking,
    *,
    check_in_date: date | None,
    check_out_date: date | None,
    room_id: uuid.UUID | None,
    number_of_guests: int | None,
    notes: str | None,
    actor_user_id: uuid.UUID,
) -> Booking:
    """Update permitted fields on a CONFIRMED booking. Caller commits."""
    if booking.status != BookingStatus.CONFIRMED:
        raise ValueError("Only CONFIRMED bookings can be modified.")
    new_in = check_in_date or booking.check_in_date
    new_out = check_out_date or booking.check_out_date
    new_room_id = room_id or booking.room_id
    if new_out <= new_in:
        raise ValueError("check_out_date must be later than check_in_date.")
    if new_in < _today():
        raise ValueError("Bookings in the past are not allowed.")
    room = lock_room(db, new_room_id)
    if room is None:
        raise ValueError("Room not found.")
    if not room.is_active or room.operational_status != RoomOperationalStatus.AVAILABLE:
        raise RoomUnavailableError("Room is inactive or under maintenance.")
    overlap = _active_overlap(
        db, room_id=new_room_id, check_in=new_in, check_out=new_out, exclude_id=booking.id
    )
    if overlap is not None:
        raise BookingOverlapError("Room is already booked for the requested dates.")
    # Snapshot refresh: rates are immutable history; re-snapshot only when
    # dates/room change, preserving the booking as a new decision point.
    changed = []
    if new_room_id != booking.room_id:
        booking.room_id = new_room_id
        booking.room_type_id = room.room_type_id
        changed.append("room_id")
    if new_in != booking.check_in_date or new_out != booking.check_out_date:
        booking.check_in_date = new_in
        booking.check_out_date = new_out
        booking.nights = (new_out - new_in).days
        changed.extend(["check_in_date", "check_out_date"])
        rate = _resolve_rate(db, room_type_id=room.room_type_id, check_in=new_in, check_out=new_out)
        subtotal, total = _snapshot_totals(rate.nightly_rate, booking.nights)
        booking.night_rate_snapshot = rate.nightly_rate
        booking.rate_id = rate.id
        booking.room_subtotal = subtotal
        booking.total_amount = total
        tax_type, tax_rate, tax_mode = _resolve_tax(db, check_in=new_in)
        booking.tax_type_snapshot = tax_type
        booking.tax_rate_snapshot = tax_rate
        booking.tax_pricing_mode_snapshot = tax_mode
    if number_of_guests is not None:
        booking.number_of_guests = number_of_guests
        changed.append("number_of_guests")
    if notes is not None:
        booking.notes = notes
        changed.append("notes")
    booking.updated_by = actor_user_id
    write_audit(
        db,
        action="BOOKING_UPDATED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={"fields": sorted(changed)},
    )
    return booking


def cancel_booking(
    db: DBSession, booking: Booking, *, reason: str | None, actor_user_id: uuid.UUID
) -> Booking:
    """Cancel a booking. Idempotent; never deletes the row."""
    if booking.status != BookingStatus.CONFIRMED:
        return booking
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = datetime.now(UTC)
    booking.cancellation_reason = reason
    booking.updated_by = actor_user_id
    write_audit(
        db,
        action="BOOKING_CANCELLED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={"fields": ["status"]},
    )
    return booking
