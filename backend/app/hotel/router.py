"""Hotel configuration endpoints: hotel profile, room types, rooms, rates, tax.

All mutating endpoints require ADMIN (``hotel.manage`` / ``rooms.manage`` /
``pricing.manage`` / ``tax.manage``) and return 401/403 via the existing
RBAC dependency. Every mutation writes an audit-log row.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission, verify_csrf
from app.auth.service import write_audit
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.hotel.schemas import (
    HotelInfoPatch,
    HotelInfoResponse,
    RoomCreate,
    RoomPatch,
    RoomRateCreate,
    RoomRateResponse,
    RoomResponse,
    RoomTypeCreate,
    RoomTypePatch,
    RoomTypeResponse,
    TaxSettingsCreate,
    TaxSettingsResponse,
)
from app.hotel.service import (
    create_room,
    create_room_rate,
    create_room_type,
    create_tax_settings,
    get_or_create_hotel,
)
from app.models.hotel_info import HotelInfo
from app.models.room import Room, RoomOperationalStatus
from app.models.room_rate import RoomRate
from app.models.room_type import RoomType
from app.models.tax_settings import TaxSettings
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin-hotel"])

_VALID_ROOM_STATUSES = {
    RoomOperationalStatus.AVAILABLE,
    RoomOperationalStatus.MAINTENANCE,
    RoomOperationalStatus.INACTIVE,
}


def _serialize_hotel(row: HotelInfo) -> HotelInfoResponse:
    return HotelInfoResponse(
        id=row.id,
        hotel_name=row.hotel_name,
        description=row.description,
        address=row.address,
        city=row.city,
        state=row.state,
        pincode=row.pincode,
        contact_number=row.contact_number,
        alternate_contact_number=row.alternate_contact_number,
        email=row.email,
        google_maps_url=row.google_maps_url,
        website_url=row.website_url,
        logo_url=row.logo_url,
        check_in_time=row.check_in_time,
        check_out_time=row.check_out_time,
        wifi_ssid=row.wifi_ssid,
    )


def _serialize_room_type(row: RoomType) -> RoomTypeResponse:
    return RoomTypeResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        maximum_occupancy=row.maximum_occupancy,
        amenities=row.amenities,
        is_active=row.is_active,
        display_order=row.display_order,
    )


def _serialize_room(row: Room) -> RoomResponse:
    return RoomResponse(
        id=row.id,
        room_number=row.room_number,
        room_type_id=row.room_type_id,
        floor=row.floor,
        description=row.description,
        maximum_occupancy=row.maximum_occupancy,
        operational_status=row.operational_status,
        is_active=row.is_active,
    )


def _serialize_rate(row: RoomRate) -> RoomRateResponse:
    return RoomRateResponse(
        id=row.id,
        room_type_id=row.room_type_id,
        nightly_rate=row.nightly_rate,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        is_active=row.is_active,
    )


def _serialize_tax(row: TaxSettings) -> TaxSettingsResponse:
    return TaxSettingsResponse(
        id=row.id,
        registration_status=row.registration_status,
        tax_type=row.tax_type,
        tax_rate=row.tax_rate,
        pricing_mode=row.pricing_mode,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        notes=row.notes,
    )


# --- Hotel profile ------------------------------------------------------


@router.get("/hotel", response_model=HotelInfoResponse | None)
def get_hotel(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.HOTEL_MANAGE)),
) -> HotelInfoResponse | None:
    """Return the singleton hotel profile (null until first configured)."""
    row = db.scalar(select(HotelInfo).where(HotelInfo.singleton_key == 1))
    return _serialize_hotel(row) if row is not None else None


@router.patch("/hotel", response_model=HotelInfoResponse)
def patch_hotel(
    payload: HotelInfoPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.HOTEL_MANAGE)),
) -> HotelInfoResponse:
    """Create-or-update the singleton hotel profile (ADMIN only)."""
    verify_csrf(request)
    row = get_or_create_hotel(db)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    row.updated_by = actor.id
    write_audit(
        db,
        action="HOTEL_INFO_UPDATED",
        resource_type="hotel_info",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(row)
    return _serialize_hotel(row)


# --- Room types ---------------------------------------------------------


@router.get("/room-types", response_model=list[RoomTypeResponse])
def list_room_types(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.ROOMS_MANAGE)),
) -> list[RoomTypeResponse]:
    """List room categories (newest last)."""
    rows = db.scalars(select(RoomType).order_by(RoomType.display_order, RoomType.created_at)).all()
    return [_serialize_room_type(r) for r in rows]


@router.post("/room-types", response_model=RoomTypeResponse, status_code=201)
def create_room_type_route(
    payload: RoomTypeCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.ROOMS_MANAGE)),
) -> RoomTypeResponse:
    """Create a room category (ADMIN only)."""
    verify_csrf(request)
    try:
        row = create_room_type(
            db,
            name=payload.name,
            description=payload.description,
            maximum_occupancy=payload.maximum_occupancy,
            amenities=payload.amenities,
            display_order=payload.display_order,
            actor_user_id=actor.id,
        )
    except ValueError as exc:
        raise ApiError(409, "CONFLICT", str(exc)) from None
    db.commit()
    db.refresh(row)
    return _serialize_room_type(row)


@router.get("/room-types/{room_type_id}", response_model=RoomTypeResponse)
def get_room_type_route(
    room_type_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.ROOMS_MANAGE)),
) -> RoomTypeResponse:
    """Fetch one room category."""
    row = db.get(RoomType, room_type_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Room category not found.")
    return _serialize_room_type(row)


@router.patch("/room-types/{room_type_id}", response_model=RoomTypeResponse)
def patch_room_type_route(
    room_type_id: uuid.UUID,
    payload: RoomTypePatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.ROOMS_MANAGE)),
) -> RoomTypeResponse:
    """Update a room category, including deactivation (ADMIN only).

    Categories referenced by rooms or historical bookings are never deleted
    — use ``is_active=false`` (deactivation) instead.
    """
    verify_csrf(request)
    row = db.get(RoomType, room_type_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Room category not found.")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None and data["name"] != row.name:
        dup = db.scalar(
            select(RoomType).where(RoomType.name == data["name"], RoomType.id != row.id)
        )
        if dup is not None:
            raise ApiError(409, "CONFLICT", "Room category name already exists.")
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    write_audit(
        db,
        action="ROOM_TYPE_UPDATED",
        resource_type="room_type",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(row)
    return _serialize_room_type(row)


# --- Rooms --------------------------------------------------------------


@router.get("/rooms", response_model=list[RoomResponse])
def list_rooms(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.ROOMS_MANAGE)),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[RoomResponse]:
    """List rooms with pagination."""
    rows = db.scalars(
        select(Room).order_by(Room.room_number).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [_serialize_room(r) for r in rows]


@router.post("/rooms", response_model=RoomResponse, status_code=201)
def create_room_route(
    payload: RoomCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.ROOMS_MANAGE)),
) -> RoomResponse:
    """Create a room (ADMIN assigns the number)."""
    verify_csrf(request)
    try:
        row = create_room(
            db,
            room_number=payload.room_number,
            room_type_id=payload.room_type_id,
            floor=payload.floor,
            description=payload.description,
            maximum_occupancy=payload.maximum_occupancy,
            actor_user_id=actor.id,
        )
    except ValueError as exc:
        raise ApiError(409, "CONFLICT", str(exc)) from None
    except LookupError as exc:
        raise ApiError(404, "NOT_FOUND", str(exc)) from None
    db.commit()
    db.refresh(row)
    return _serialize_room(row)


@router.get("/rooms/{room_id}", response_model=RoomResponse)
def get_room_route(
    room_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.ROOMS_MANAGE)),
) -> RoomResponse:
    """Fetch one room."""
    row = db.get(Room, room_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Room not found.")
    return _serialize_room(row)


@router.patch("/rooms/{room_id}", response_model=RoomResponse)
def patch_room_route(
    room_id: uuid.UUID,
    payload: RoomPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.ROOMS_MANAGE)),
) -> RoomResponse:
    """Update a room, including operational status (ADMIN only)."""
    verify_csrf(request)
    row = db.get(Room, room_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Room not found.")
    if (
        payload.operational_status is not None
        and payload.operational_status not in _VALID_ROOM_STATUSES
    ):
        raise ApiError(422, "VALIDATION_ERROR", "Invalid operational_status.")
    if payload.room_type_id is not None and db.get(RoomType, payload.room_type_id) is None:
        raise ApiError(404, "NOT_FOUND", "Room category not found.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(row, field, value)
    write_audit(
        db,
        action="ROOM_UPDATED",
        resource_type="room",
        resource_id=str(row.id),
        actor_user_id=actor.id,
        metadata={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(row)
    return _serialize_room(row)


# --- Room rates ---------------------------------------------------------


@router.get("/room-rates", response_model=list[RoomRateResponse])
def list_room_rates(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PRICING_MANAGE)),
) -> list[RoomRateResponse]:
    """List all rate versions (history preserved)."""
    rows = db.scalars(select(RoomRate).order_by(RoomRate.valid_from)).all()
    return [_serialize_rate(r) for r in rows]


@router.post("/room-rates", response_model=RoomRateResponse, status_code=201)
def create_room_rate_route(
    payload: RoomRateCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PRICING_MANAGE)),
) -> RoomRateResponse:
    """Create a new rate version (ADMIN only). Old rows untouched."""
    verify_csrf(request)
    try:
        row = create_room_rate(
            db,
            room_type_id=payload.room_type_id,
            nightly_rate=payload.nightly_rate,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            actor_user_id=actor.id,
        )
    except ValueError as exc:
        raise ApiError(409, "CONFLICT", str(exc)) from None
    except LookupError as exc:
        raise ApiError(404, "NOT_FOUND", str(exc)) from None
    db.commit()
    db.refresh(row)
    return _serialize_rate(row)


@router.get("/room-rates/{rate_id}", response_model=RoomRateResponse)
def get_room_rate_route(
    rate_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PRICING_MANAGE)),
) -> RoomRateResponse:
    """Fetch one rate version."""
    row = db.get(RoomRate, rate_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Room rate not found.")
    return _serialize_rate(row)


# --- Tax settings -------------------------------------------------------


@router.get("/tax-settings", response_model=list[TaxSettingsResponse])
def list_tax_settings(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.TAX_MANAGE)),
) -> list[TaxSettingsResponse]:
    """List all tax settings versions. Empty = NONE (no tax configured)."""
    rows = db.scalars(select(TaxSettings).order_by(TaxSettings.valid_from)).all()
    return [_serialize_tax(r) for r in rows]


@router.post("/tax-settings", response_model=TaxSettingsResponse, status_code=201)
def create_tax_settings_route(
    payload: TaxSettingsCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.TAX_MANAGE)),
) -> TaxSettingsResponse:
    """Create a new tax settings version (ADMIN only)."""
    verify_csrf(request)
    if payload.tax_type != "NONE" and payload.tax_rate is None:
        raise ApiError(422, "VALIDATION_ERROR", "A tax rate is required when tax_type is not NONE.")
    try:
        row = create_tax_settings(
            db,
            registration_status=payload.registration_status,
            tax_type=payload.tax_type,
            tax_rate=payload.tax_rate,
            pricing_mode=payload.pricing_mode,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except ValueError as exc:
        raise ApiError(409, "CONFLICT", str(exc)) from None
    db.commit()
    db.refresh(row)
    return _serialize_tax(row)
