"""Versioned tax settings model.

Default configuration is NONE (no tax). No GST registration or percentage
is ever assumed or seeded. Settings are append-only history; the current
settings are the row whose period covers today. Calculations and legal
invoices belong to the billing phase (Phase 4) — not this phase.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TaxPricingMode:
    """Supported tax pricing modes."""

    INCLUSIVE = "INCLUSIVE"
    EXCLUSIVE = "EXCLUSIVE"


class TaxSettings(Base):
    """One version of the hotel's tax configuration."""

    __tablename__ = "tax_settings"
    __table_args__ = (
        CheckConstraint("tax_rate IS NULL OR tax_rate >= 0", name="ck_tax_settings_non_negative"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from", name="ck_tax_settings_dates"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    registration_status: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    tax_type: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    pricing_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="EXCLUSIVE")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"<TaxSettings {self.tax_type!r} rate={self.tax_rate} from={self.valid_from}>"
