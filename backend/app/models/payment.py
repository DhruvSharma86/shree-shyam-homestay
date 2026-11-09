"""Payment model — append-only payment records against a booking.

Created in Phase 4.1 (schema only). Payment-writing endpoints belong to
Phase 4.2; recording payments remains off-limits until then. Like
``folio_entries``, rows are immutable once created: fixes happen through
reversal rows (``reverses_payment_id``), never by editing or deleting.
PostgreSQL triggers (migration) reject UPDATE/DELETE; SQLite does not
offer that protection (documented in docs/DATABASE_DESIGN.md).

Money: NUMERIC(12,2); all math in Python Decimal.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PaymentMode:
    """Values for payments.mode (D1, approved)."""

    CASH = "CASH"
    UPI = "UPI"
    CARD_POS = "CARD_POS"


class PaymentStage:
    """Values for payments.payment_stage."""

    ADVANCE = "ADVANCE"
    CHECK_IN = "CHECK_IN"
    CHECKOUT = "CHECKOUT"
    OTHER = "OTHER"


class Payment(Base):
    """One immutable payment received against a booking's folio."""

    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payments_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    payment_stage: Mapped[str] = mapped_column(String(16), nullable=False)
    reference_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reverses_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        """Return a debug representation without amounts/PII."""
        return f"<Payment mode={self.mode!r} booking={self.booking_id!r}>"
