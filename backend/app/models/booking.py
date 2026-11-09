"""Booking model — reservations for the six rooms.

Date convention: ``check_in_date`` is inclusive, ``check_out_date`` is
exclusive. A stay 10→12 Nov occupies nights of 10 and 11 Nov; another
booking starting 12 Nov does not conflict.

Lifecycle (Phase 3.2): CONFIRMED → CANCELLED only. Check-in/out statuses
belong to a later milestone and are deliberately not defined here.
Double-booking prevention: app check + row lock, plus a PostgreSQL
exclusion constraint (enforced in migration, not in the ORM metadata, so
SQLite tests can still run).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BookingStatus:
    """Values for ``bookings.status`` (Phase 3.2 minimal lifecycle)."""

    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class BookingSource:
    """Values for ``bookings.source`` — phone/walk-in only, never online."""

    PHONE = "PHONE"
    WALK_IN = "WALK_IN"


class Booking(Base):
    """One reservation linking an active guest to an operational room."""

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("check_out_date > check_in_date", name="ck_bookings_dates"),
        CheckConstraint("nights >= 1", name="ck_bookings_nights"),
        CheckConstraint("number_of_guests >= 1", name="ck_bookings_guests"),
        CheckConstraint("night_rate_snapshot >= 0", name="ck_bookings_rate"),
        CheckConstraint("room_subtotal >= 0", name="ck_bookings_subtotal"),
        CheckConstraint("total_amount >= 0", name="ck_bookings_total"),
        CheckConstraint(
            "tax_rate_snapshot IS NULL OR tax_rate_snapshot >= 0", name="ck_bookings_tax_rate"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    booking_ref: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    guest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("room_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BookingStatus.CONFIRMED, index=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default=BookingSource.PHONE)
    check_in_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_out_date: Mapped[date] = mapped_column(Date, nullable=False)
    nights: Mapped[int] = mapped_column(nullable=False)
    number_of_guests: Mapped[int] = mapped_column(nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    night_rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    room_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_type_snapshot: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    tax_rate_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    tax_pricing_mode_snapshot: Mapped[str] = mapped_column(
        String(16), nullable=False, default="EXCLUSIVE"
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        """Return a debug representation without PII."""
        return f"<Booking {self.booking_ref!r} status={self.status!r}>"
