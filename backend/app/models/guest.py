"""Guest model — primary guest master records.

Aadhaar document handling is deliberately **deferred** in this milestone
(see docs/DATABASE_DESIGN.md §2.9): no Aadhaar image, number, or ID-proof
data is collected or stored. This follows data-minimisation — full ID-proof
handling requires legal review, private encrypted storage, retention
controls and approved safeguards that are not part of Phase 3.1.

Phone numbers are normalized to E.164 before storage. Phone alone is NOT
unique: two family members may share one phone. Duplicate protection is at
the service layer (exact normalized-phone + case-insensitive name match),
never a silent merge.
"""

import re
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def _norm_name(name: str) -> str:
    """Whitespace-collapsed, lowercased name used for duplicate matching."""
    return " ".join((name or "").split()).lower()


class Guest(Base):
    """A primary guest of record. No booking rows exist yet (Phase 3.2)."""

    __tablename__ = "guests"
    __table_args__ = (
        # DB-level guard against concurrent duplicate creation:
        # one active guest per (phone, normalized name).
        Index(
            "ix_guests_phone_name_active",
            "phone",
            text("lower(trim(full_name))"),
            unique=True,
            postgresql_where=text("is_active = TRUE"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    def __repr__(self) -> str:
        """Return a debug representation without PII."""
        suffix = str(self.id)[-6:]
        return f"<Guest id=...{suffix} active={self.is_active}>"
