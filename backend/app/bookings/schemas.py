"""Pydantic schemas for the booking endpoints."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class BookingResponse(BaseModel):
    """Safe booking representation (no guest PII beyond ids)."""

    id: uuid.UUID
    booking_ref: str
    guest_id: uuid.UUID
    room_id: uuid.UUID
    room_type_id: uuid.UUID
    status: str
    source: str
    check_in_date: date
    check_out_date: date
    nights: int
    number_of_guests: int
    notes: str | None = None
    night_rate_snapshot: Decimal
    rate_id: uuid.UUID | None = None
    room_subtotal: Decimal
    tax_type_snapshot: str
    tax_rate_snapshot: Decimal | None = None
    tax_pricing_mode_snapshot: str
    total_amount: Decimal
    cancelled_at: str | None = None
    cancellation_reason: str | None = None


class BookingCreate(BaseModel):
    """Create a booking (phone/walk-in only — no online source)."""

    guest_id: uuid.UUID
    room_id: uuid.UUID
    source: str = "PHONE"
    check_in_date: date
    check_out_date: date
    number_of_guests: int = Field(default=1, ge=1, le=20)
    notes: str | None = None


class BookingPatch(BaseModel):
    """Update permitted booking fields (cancelled bookings reject)."""

    check_in_date: date | None = None
    check_out_date: date | None = None
    room_id: uuid.UUID | None = None
    number_of_guests: int | None = Field(default=None, ge=1, le=20)
    notes: str | None = None


class BookingCancel(BaseModel):
    """Cancellation payload (reason optional — policy TBD)."""

    reason: str | None = None


class CheckoutResponse(BaseModel):
    """Checkout settlement summary (status transition + receipt handle)."""

    booking_id: uuid.UUID
    booking_ref: str
    status: str
    checked_out_at: str
    total_charges: Decimal
    total_paid: Decimal
    balance_due: Decimal
    receipt_ref: str
    content_hash: str


class CheckInRequest(BaseModel):
    """Check-in payload (note optional — early check-in policy TBD)."""

    note: str | None = None


class BookingListResponse(BaseModel):
    """Paginated booking list."""

    items: list[BookingResponse]
    total: int
    page: int
    page_size: int


class AvailabilityResponse(BaseModel):
    """Room availability for [check_in, check_out)."""

    room_id: uuid.UUID
    available: bool
    check_in_date: date
    check_out_date: date
