"""Versioned room rate model — nightly price per room category.

Rates are append-only: a price change creates a NEW row. Existing rows are
never modified, so historical bookings keep pointing at the price that was
in force. Overlap prevention is enforced at the application layer (with a
check for existing active periods in the same transaction) — matching the
approved bookings pattern; see docs/DATABASE_DESIGN.md.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RoomRate(Base):
    """One nightly-rate version for one room category."""

    __tablename__ = "room_rates"
    __table_args__ = (
        CheckConstraint("nightly_rate >= 0", name="ck_room_rates_non_negative"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from", name="ck_room_rates_dates"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("room_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    nightly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        """Return a debug representation."""
        return (
            f"<RoomRate type={self.room_type_id} rate={self.nightly_rate} from={self.valid_from}>"
        )
