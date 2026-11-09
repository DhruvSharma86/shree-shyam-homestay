"""Guest portal access token model — bearer tokens hashed at rest.

One active (non-revoked) token per booking, enforced by a partial
unique index. Only the SHA-256 hex digest is stored; the raw token
exists only in the issuance response and the guest's link (never in
logs, audits, or normal booking/guest API payloads).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class GuestPortalToken(Base):
    """Hashed bearer token granting read-only portal access to one booking."""

    __tablename__ = "guest_portal_tokens"
    __table_args__ = (
        # At most one active token per booking, even under concurrent issues.
        Index(
            "ux_guest_portal_tokens_booking_active",
            "booking_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        """Return a debug representation (hash truncated, never the token)."""
        return f"<GuestPortalToken booking={self.booking_id!r} {self.token_hash[:8]}...>"
