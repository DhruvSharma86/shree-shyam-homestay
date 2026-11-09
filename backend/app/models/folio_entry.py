"""Folio entry model — append-only financial ledger lines.

Rule Zero (see docs/DATABASE_DESIGN.md): financial tables are append-only.
Corrections are REVERSAL entries referencing the original; originals are
never updated or deleted (enforced at the service layer, and — on
PostgreSQL — by triggers installed in migration
``e5f6a7b8c9d0``'s successor; SQLite has no equivalent, documented in
docs/DATABASE_DESIGN.md).

Money: NUMERIC(12,2) with Decimal arithmetic only; amounts are signed
(positive = charge, negative = discount/reversal) so the balance is a
simple sum: ``balance = SUM(entries.amount) - SUM(payments.amount)``.

``is_initial`` marks the single initial ROOM_CHARGE created from the
booking snapshot (uniqueness enforced by a partial unique index).
Extension sessions may later add further ``ROOM_CHARGE`` rows with
``is_initial = FALSE``.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FolioEntryType:
    """Values for folio_entries.entry_type."""

    ROOM_CHARGE = "ROOM_CHARGE"
    ADDITIONAL_CHARGE = "ADDITIONAL_CHARGE"
    DISCOUNT = "DISCOUNT"
    TAX = "TAX"
    REVERSAL = "REVERSAL"


class FolioEntry(Base):
    """One immutable ledger line on a booking's folio."""

    __tablename__ = "folio_entries"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_folio_entries_nonzero"),
        CheckConstraint("quantity > 0", name="ck_folio_entries_qty"),
        CheckConstraint("unit_amount IS NULL OR unit_amount >= 0", name="ck_folio_entries_unit"),
        CheckConstraint(
            "(is_initial AND entry_type = 'ROOM_CHARGE') OR NOT is_initial",
            name="ck_folio_entries_initial",
        ),
        # Exactly one initial ROOM_CHARGE per booking, even under races.
        Index(
            "ux_folio_initial_room_charge",
            "booking_id",
            unique=True,
            postgresql_where=text("is_initial = TRUE"),
            sqlite_where=text("is_initial = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("1"))
    unit_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("folio_entries.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        """Return a debug representation without amounts/PII."""
        return f"<FolioEntry {self.entry_type!r} booking={self.booking_id!r}>"
