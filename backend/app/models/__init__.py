"""ORM models package. Importing this package registers all models on
``app.core.db.Base.metadata`` for Alembic autogenerate and test DDL.
"""

from app.models.audit import AuditLog
from app.models.cab_info import CabInfo
from app.models.hotel_info import HotelInfo
from app.models.restaurant import MenuCategory, MenuItem, RestaurantInfo
from app.models.room import Room
from app.models.room_rate import RoomRate
from app.models.room_type import RoomType
from app.models.session import Session
from app.models.tax_settings import TaxSettings
from app.models.user import User

__all__ = [
    "AuditLog",
    "CabInfo",
    "HotelInfo",
    "MenuCategory",
    "MenuItem",
    "RestaurantInfo",
    "Room",
    "RoomRate",
    "RoomType",
    "Session",
    "TaxSettings",
    "User",
]
