"""Receipt model — immutable final receipts (ReportLab PDFs as bytes).

A receipt is issued at checkout and must never change afterwards:
``pdf_content`` stores the exact bytes rendered from the ledger at that
moment, and ``content_hash`` (SHA-256 of those bytes) proves it. Later
hotel/guest/rate edits cannot retroactively alter the issued document.
Storage is database bytes (no filesystem or cloud dependency — the
existing deployment is a single PostgreSQL).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReceiptKind:
    """Values for receipts.kind."""

    FINAL = "FINAL"
    PAYMENT = "PAYMENT"


class Receipt(Base):
    """One issued receipt for a booking (final settlement)."""

    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint("kind IN ('FINAL', 'PAYMENT')", name="ck_receipts_kind"),
        # Exactly one FINAL receipt per booking; PAYMENT kind stays free
        # for possible future per-payment receipts (Phase 4.3 ships FINAL only).
        Index(
            "ux_receipts_final_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("kind = 'FINAL'"),
            sqlite_where=text("kind = 'FINAL'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    receipt_ref: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ReceiptKind.FINAL)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pdf_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        """Return a debug representation without content."""
        return f"<Receipt {self.receipt_ref!r} kind={self.kind!r}>"
