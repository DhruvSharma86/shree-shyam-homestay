"""Room model — one row per physical room (6 rooms)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RoomOperationalStatus:
    """Values for ``rooms.operational_status``.

    IMPORTANT: operational status describes whether a room may be sold
    (housekeeping/maintenance state) — it is NOT booking occupancy. A room
    that is AVAILABLE may still be reserved for future dates.
    """

    AVAILABLE = "AVAILABLE"
    MAINTENANCE = "MAINTENANCE"
    INACTIVE = "INACTIVE"


class Room(Base):
    """A physical room. Room numbers are assigned by the ADMIN (never invented)."""

    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    room_number: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("room_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    floor: Mapped[int | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    maximum_occupancy: Mapped[int] = mapped_column(nullable=False, default=2)
    operational_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RoomOperationalStatus.AVAILABLE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"<Room {self.room_number!r} status={self.operational_status!r}>"
