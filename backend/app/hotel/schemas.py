"""Pydantic schemas for the hotel configuration endpoints."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, HttpUrl


class HotelInfoResponse(BaseModel):
    """Hotel profile response (never exposes internal fields)."""

    id: uuid.UUID
    hotel_name: str
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    contact_number: str | None = None
    alternate_contact_number: str | None = None
    email: str | None = None
    google_maps_url: str | None = None
    website_url: str | None = None
    logo_url: str | None = None
    check_in_time: str | None = None
    check_out_time: str | None = None
    wifi_ssid: str | None = None


class HotelInfoPatch(BaseModel):
    """Partial hotel profile update (all fields optional)."""

    hotel_name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    address: str | None = None
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=16)
    contact_number: str | None = Field(default=None, max_length=24)
    alternate_contact_number: str | None = Field(default=None, max_length=24)
    email: str | None = Field(default=None, max_length=255)
    google_maps_url: str | None = None
    website_url: str | None = None
    logo_url: str | None = None
    check_in_time: str | None = Field(default=None, max_length=8)
    check_out_time: str | None = Field(default=None, max_length=8)
    wifi_ssid: str | None = Field(default=None, max_length=64)
    wifi_password: str | None = Field(default=None, max_length=128)


class RoomTypeResponse(BaseModel):
    """Room category response."""

    id: uuid.UUID
    name: str
    description: str | None = None
    maximum_occupancy: int
    amenities: str | None = None
    is_active: bool
    display_order: int


class RoomTypeCreate(BaseModel):
    """Create a room category."""

    name: str = Field(min_length=1, max_length=64)
    description: str | None = None
    maximum_occupancy: int = Field(default=2, ge=1, le=20)
    amenities: str | None = None
    display_order: int = 0


class RoomTypePatch(BaseModel):
    """Partial room category update."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    maximum_occupancy: int | None = Field(default=None, ge=1, le=20)
    amenities: str | None = None
    is_active: bool | None = None
    display_order: int | None = None


class RoomResponse(BaseModel):
    """Room response."""

    id: uuid.UUID
    room_number: str
    room_type_id: uuid.UUID
    floor: int | None = None
    description: str | None = None
    maximum_occupancy: int
    operational_status: str
    is_active: bool


class RoomCreate(BaseModel):
    """Create a room (numbers are assigned by ADMIN — never invented)."""

    room_number: str = Field(min_length=1, max_length=16)
    room_type_id: uuid.UUID
    floor: int | None = None
    description: str | None = None
    maximum_occupancy: int = Field(default=2, ge=1, le=20)


class RoomPatch(BaseModel):
    """Partial room update."""

    room_type_id: uuid.UUID | None = None
    floor: int | None = None
    description: str | None = None
    maximum_occupancy: int | None = Field(default=None, ge=1, le=20)
    operational_status: str | None = None
    is_active: bool | None = None


class RoomRateResponse(BaseModel):
    """Room rate version response."""

    id: uuid.UUID
    room_type_id: uuid.UUID
    nightly_rate: Decimal
    valid_from: date
    valid_until: date | None = None
    is_active: bool


class RoomRateCreate(BaseModel):
    """Create a new rate version (history is preserved — append-only)."""

    room_type_id: uuid.UUID
    nightly_rate: Decimal = Field(ge=Decimal("0"))
    valid_from: date
    valid_until: date | None = None


class TaxSettingsResponse(BaseModel):
    """Tax settings version response."""

    id: uuid.UUID
    registration_status: str
    tax_type: str
    tax_rate: Decimal | None
    pricing_mode: str
    valid_from: date
    valid_until: date | None
    notes: str | None = None


class TaxSettingsCreate(BaseModel):
    """Create a new tax settings version. Default must be NONE."""

    registration_status: str = "NONE"
    tax_type: str = "NONE"
    tax_rate: Decimal | None = None
    pricing_mode: str = "EXCLUSIVE"
    valid_from: date
    valid_until: date | None = None
    notes: str | None = None


class RestaurantResponse(BaseModel):
    """Restaurant information response."""

    id: uuid.UUID
    name: str
    description: str | None = None
    contact_number: str | None = None
    opening_hours: str | None = None
    is_active: bool


class RestaurantPatch(BaseModel):
    """Partial restaurant information update."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    contact_number: str | None = Field(default=None, max_length=24)
    opening_hours: str | None = None
    is_active: bool | None = None


class MenuCategoryResponse(BaseModel):
    """Menu category response."""

    id: uuid.UUID
    name: str
    description: str | None = None
    display_order: int
    is_active: bool


class MenuCategoryCreate(BaseModel):
    """Create a menu category."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    display_order: int = 0


class MenuCategoryPatch(BaseModel):
    """Partial menu category update."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class MenuItemResponse(BaseModel):
    """Menu item response (image is a URL, never binary)."""

    id: uuid.UUID
    name: str
    description: str | None = None
    price: Decimal
    image_url: str | None = None
    category_id: uuid.UUID
    is_vegetarian: bool
    is_available: bool
    display_order: int


class MenuItemCreate(BaseModel):
    """Create a menu item."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    price: Decimal = Field(ge=Decimal("0"))
    image_url: HttpUrl | None = None
    category_id: uuid.UUID
    is_vegetarian: bool = True
    display_order: int = 0


class MenuItemPatch(BaseModel):
    """Partial menu item update (price changes create audit entries)."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=Decimal("0"))
    image_url: str | None = None
    category_id: uuid.UUID | None = None
    is_vegetarian: bool | None = None
    is_available: bool | None = None
    display_order: int | None = None


class CabInfoResponse(BaseModel):
    """Cab provider response."""

    id: uuid.UUID
    company_name: str
    description: str | None = None
    contact_number: str
    website_url: str | None = None
    service_description: str | None = None
    is_active: bool
    display_order: int


class CabInfoCreate(BaseModel):
    """Create a cab provider (URL + phone validated)."""

    company_name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    contact_number: str = Field(min_length=7, max_length=24)
    website_url: HttpUrl | None = None
    service_description: str | None = None
    display_order: int = 0


class CabInfoPatch(BaseModel):
    """Partial cab provider update."""

    company_name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    contact_number: str | None = Field(default=None, min_length=7, max_length=24)
    website_url: str | None = None
    service_description: str | None = None
    is_active: bool | None = None
    display_order: int | None = None
