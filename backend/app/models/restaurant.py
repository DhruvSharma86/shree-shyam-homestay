"""Restaurant information and menu models (menu photographs via URLs only)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class RestaurantInfo(Base):
    """Singleton row for the homestay restaurant (like hotel_info)."""

    __tablename__ = "restaurant_info"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    singleton_key: Mapped[int] = mapped_column(nullable=False, unique=True, default=1)
    name: Mapped[str] = mapped_column(String(160), nullable=False, default="Restaurant")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"<RestaurantInfo {self.name!r}>"


class MenuCategory(Base):
    """A grouping of menu items (e.g. Breakfast, Lunch)."""

    __tablename__ = "menu_categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"<MenuCategory {self.name!r}>"


class MenuItem(Base):
    """One dish on the menu. Photographs are URLs only — never DB binaries."""

    __tablename__ = "menu_items"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_menu_items_non_negative"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"<MenuItem {self.name!r} price={self.price}>"
