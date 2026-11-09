"""Pydantic schemas for the guest portal endpoints."""

from decimal import Decimal

from pydantic import BaseModel


class ContactBlock(BaseModel):
    """Hotel contact fields the portal may show (configured values only)."""

    contact_number: str | None = None
    email: str | None = None
    address: str | None = None


class PortalOverviewResponse(BaseModel):
    """Booking-relevant fields only (no ids, no money, no PII)."""

    hotel_name: str
    booking_ref: str
    room_number: str
    room_type: str
    check_in_date: str
    check_out_date: str
    nights: int
    status: str
    checked_out_at: str | None = None
    expires_at: str | None = None
    contact: ContactBlock


class PortalMenuItem(BaseModel):
    """One guest-visible menu item (no internal ids)."""

    name: str
    description: str | None = None
    price: Decimal
    image_url: str | None = None
    is_vegetarian: bool = True


class PortalMenuCategory(BaseModel):
    """One active category with its visible items."""

    category: str
    items: list[PortalMenuItem]


class PortalMenuResponse(BaseModel):
    """Menu view grouped by category."""

    categories: list[PortalMenuCategory]


class PortalCabItem(BaseModel):
    """One guest-visible cab provider."""

    company_name: str
    description: str | None = None
    contact_number: str
    service_description: str | None = None


class PortalCabResponse(BaseModel):
    """Cab providers view."""

    providers: list[PortalCabItem]


class PortalWifiResponse(BaseModel):
    """Wi-Fi details only when configured (otherwise both null)."""

    ssid: str | None = None
    password: str | None = None


class PortalReceiptResponse(BaseModel):
    """Final receipt metadata for the portal's own booking only."""

    receipt_ref: str
    kind: str
    content_hash: str


class PortalTourPackage(BaseModel):
    """One guest-visible tour package (no internal ids)."""

    name: str
    description: str | None = None
    duration: str | None = None
    price: Decimal | None = None
    image_url: str | None = None
    contact_number: str | None = None


class PortalLocalInfo(BaseModel):
    """One guest-visible local information entry (no internal ids)."""

    title: str
    description: str | None = None
    location: str | None = None
    contact_number: str | None = None
    image_url: str | None = None


class PortalTourismResponse(BaseModel):
    """Tourism content for the guest (empty when unconfigured)."""

    packages: list[PortalTourPackage]
    local_info: list[PortalLocalInfo]


class PortalTokenAdminResponse(BaseModel):
    """Portal token status for staff (never the raw token)."""

    booking_id: str
    active: bool
    issued: bool


class PortalTokenIssuedResponse(BaseModel):
    """Fresh issuance (raw token shown once, never persisted)."""

    booking_id: str
    portal_access_token: str
