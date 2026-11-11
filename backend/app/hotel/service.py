"""Hotel configuration service layer.

All mutations are ADMIN-only (enforced at the router via RBAC), run in the
caller's transaction, and write an audit-log row. No secrets are ever placed
in audit metadata.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.service import write_audit
from app.models.hotel_info import HotelInfo
from app.models.room import Room
from app.models.room_rate import RoomRate
from app.models.room_type import RoomType
from app.models.tax_settings import TaxSettings


def get_or_create_hotel(db: DBSession) -> HotelInfo:
    """Return the singleton hotel row, creating an empty one if absent."""
    row = db.scalar(select(HotelInfo).where(HotelInfo.singleton_key == 1))
    if row is None:
        row = HotelInfo(hotel_name="Shree Shyam Home Stay")
        db.add(row)
        db.flush()
    return row


def create_room_type(
    db: DBSession,
    *,
    name: str,
    description: str | None,
    maximum_occupancy: int,
    amenities: str | None,
    display_order: int,
    actor_user_id: uuid.UUID,
) -> RoomType:
    """Create a room category. Raises ValueError on duplicate name."""
    existing = db.scalar(select(RoomType).where(RoomType.name == name))
    if existing is not None:
        raise ValueError("Room category name already exists.")
    row = RoomType(
        name=name,
        description=description,
        maximum_occupancy=maximum_occupancy,
        amenities=amenities,
        display_order=display_order,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="ROOM_TYPE_CREATED",
        resource_type="room_type",
        resource_id=str(row.id),
        actor_user_id=actor_user_id,
        metadata={
            "name": name,
            "description": description,
            "maximum_occupancy": maximum_occupancy,
            "amenities": amenities,
            "display_order": display_order,
        },
    )
    return row


def create_room(
    db: DBSession,
    *,
    room_number: str,
    room_type_id: uuid.UUID,
    floor: int | None,
    description: str | None,
    maximum_occupancy: int,
    actor_user_id: uuid.UUID,
) -> Room:
    """Create a room. Raises ValueError on duplicate number or bad type."""
    room_type = db.get(RoomType, room_type_id)
    if room_type is None:
        raise LookupError("Room category not found.")
    existing = db.scalar(select(Room).where(Room.room_number == room_number))
    if existing is not None:
        raise ValueError("Room number already exists.")
    row = Room(
        room_number=room_number,
        room_type_id=room_type_id,
        floor=floor,
        description=description,
        maximum_occupancy=maximum_occupancy,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="ROOM_CREATED",
        resource_type="room",
        resource_id=str(row.id),
        actor_user_id=actor_user_id,
        metadata={
            "room_number": room_number,
            "floor": floor,
            "description": description,
            "maximum_occupancy": maximum_occupancy,
        },
    )
    return row


def _periods_overlap(a_from: date, a_to: date | None, b_from: date, b_to: date | None) -> bool:
    """Return True when two closed date periods share at least one day."""
    a_end = a_to or date.max
    b_end = b_to or date.max
    return a_from <= b_end and b_from <= a_end


def create_room_rate(
    db: DBSession,
    *,
    room_type_id: uuid.UUID,
    nightly_rate: Decimal,
    valid_from: date,
    valid_until: date | None,
    actor_user_id: uuid.UUID,
) -> RoomRate:
    """Create a new rate version. Old rows are never modified."""
    if nightly_rate < 0:
        raise ValueError("Nightly rate cannot be negative.")
    if valid_until is not None and valid_until < valid_from:
        raise ValueError("valid_until cannot be before valid_from.")
    room_type = db.get(RoomType, room_type_id)
    if room_type is None:
        raise LookupError("Room category not found.")
    active = db.scalars(
        select(RoomRate).where(RoomRate.room_type_id == room_type_id, RoomRate.is_active.is_(True))
    ).all()
    for existing in active:
        if _periods_overlap(valid_from, valid_until, existing.valid_from, existing.valid_until):
            raise ValueError("An active rate period overlaps the requested period.")
    row = RoomRate(
        room_type_id=room_type_id,
        nightly_rate=nightly_rate,
        valid_from=valid_from,
        valid_until=valid_until,
        created_by=actor_user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="RATE_CREATED",
        resource_type="room_rate",
        resource_id=str(row.id),
        actor_user_id=actor_user_id,
        metadata={"room_type_id": str(room_type_id), "nightly_rate": str(nightly_rate)},
    )
    return row


def create_tax_settings(
    db: DBSession,
    *,
    registration_status: str,
    tax_type: str,
    tax_rate: Decimal | None,
    pricing_mode: str,
    valid_from: date,
    valid_until: date | None,
    notes: str | None,
    actor_user_id: uuid.UUID,
) -> TaxSettings:
    """Create a new tax-settings version. History is preserved."""
    if tax_rate is not None and tax_rate < 0:
        raise ValueError("Tax rate cannot be negative.")
    if tax_type != "NONE" and tax_rate is None:
        raise ValueError("A tax rate is required when tax_type is not NONE.")
    if valid_until is not None and valid_until < valid_from:
        raise ValueError("valid_until cannot be before valid_from.")
    active = db.scalars(select(TaxSettings)).all()
    for existing in active:
        if _periods_overlap(valid_from, valid_until, existing.valid_from, existing.valid_until):
            raise ValueError("A tax settings period overlaps the requested period.")
    row = TaxSettings(
        registration_status=registration_status,
        tax_type=tax_type,
        tax_rate=tax_rate,
        pricing_mode=pricing_mode,
        valid_from=valid_from,
        valid_until=valid_until,
        notes=notes,
        created_by=actor_user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        action="TAX_SETTINGS_CREATED",
        resource_type="tax_settings",
        resource_id=str(row.id),
        actor_user_id=actor_user_id,
        metadata={
            "registration_status": registration_status,
            "tax_type": tax_type,
            "tax_rate": str(tax_rate) if tax_rate is not None else None,
            "pricing_mode": pricing_mode,
            "valid_from": valid_from.isoformat(),
            "valid_until": valid_until.isoformat() if valid_until is not None else None,
        },
    )
    return row
