"""Hotel information model — singleton property profile.

The application manages exactly one property (a 6-room homestay). The
table is constrained to a single row via ``singleton_key = 1``; the API
creates it on first PATCH and updates it thereafter. No multi-property
complexity is introduced.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class HotelInfo(Base):
    """Singleton row holding the property's public/profile information."""

    __tablename__ = "hotel_info"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    singleton_key: Mapped[int] = mapped_column(nullable=False, unique=True, default=1)
    hotel_name: Mapped[str] = mapped_column(
        String(160), nullable=False, default="Shree Shyam Home Stay"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    alternate_contact_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_maps_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    check_in_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    check_out_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    wifi_ssid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wifi_password: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    def __repr__(self) -> str:
        """Return a debug representation without contact details."""
        return f"<HotelInfo {self.hotel_name!r}>"
