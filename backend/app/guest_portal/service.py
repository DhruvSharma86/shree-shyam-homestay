"""Guest portal service — token issuance, resolution, guest-safe reads.

Tokens are 256-bit URL-safe random strings; only their SHA-256 hex is
persisted (never logged, never audited, never returned again — the raw
value is shown exactly once, at issuance/rotation). Portal access
expires 24 hours after the booking's successful checkout
(``checked_out_at``), derived from the lifecycle — never from the
token's creation time.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.auth.rate_limit import (
    is_rate_limited as _login_limited,
)
from app.auth.rate_limit import (
    register_failed_attempt as _login_fail,
)
from app.auth.service import write_audit
from app.core.security import compare_tokens, generate_session_token, hash_token
from app.models.booking import Booking
from app.models.cab_info import CabInfo
from app.models.guest_portal_token import GuestPortalToken
from app.models.hotel_info import HotelInfo
from app.models.receipt import Receipt, ReceiptKind
from app.models.restaurant import MenuCategory, MenuItem
from app.models.room import Room
from app.models.room_type import RoomType

PORTAL_WINDOW = timedelta(hours=24)


class PortalAccessDenied(ValueError):
    """Raised when a token does not grant portal access (generic 404 upstream)."""


def _portal_key(raw_token: str) -> str:
    """Rate-limit key for a presented token (hash only, never the token)."""
    return f"portal:{hash_token(raw_token)[:24]}"


def is_portal_rate_limited(raw_token: str) -> bool:
    """Return True when this token hash has blown its failed-access budget."""
    return _login_limited(_portal_key(raw_token))


def register_portal_attempt(raw_token: str) -> None:
    """Record one unresolvable token access attempt."""
    _login_fail(_portal_key(raw_token))


def now_utc() -> datetime:
    """Return the current UTC timestamp (tests may monkeypatch)."""
    return datetime.now(UTC)


def portal_deadline(booking: Booking) -> datetime | None:
    """Return the checkout-derived expiry, or None while open-ended."""
    if booking.status != "CHECKED_OUT" or booking.checked_out_at is None:
        return None
    return booking.checked_out_at + PORTAL_WINDOW


def portal_active(booking: Booking, token: GuestPortalToken, at: datetime | None = None) -> bool:
    """Return True when the token grants access right now.

    Revocation always forbids; cancellation always forbids; after
    checkout the 24-hour window governs (strict: at the deadline the
    access is already expired).
    """
    if token.revoked_at is not None:
        return False
    if booking.status == "CANCELLED":
        return False
    deadline = portal_deadline(booking)
    if deadline is not None:
        moment = at or now_utc()
        # DB timestamps may be naive (SQLite) or aware (PostgreSQL); both treated as UTC.
        naive_deadline = deadline.replace(tzinfo=None)
        naive_moment = moment.replace(tzinfo=None)
        if naive_moment >= naive_deadline:
            return False
    return True


def issue_portal_token(
    db: DBSession,
    booking: Booking,
    *,
    actor_user_id: uuid.UUID | None,
    rotate: bool = False,
) -> tuple[GuestPortalToken, str]:
    """Issue (or rotate) the single active portal token for a booking.

    Returns ``(row, raw_token)`` — the raw value exists only in the
    return value, never in the database, logs or audits. ``rotate=True``
    revokes the current active token first (permanent, unrecreatable).
    Idempotent for issuance: an existing active token is returned with
    its original creation (the raw token is only known at that moment,
    so issuance is a no-op for already-issued bookings; rotate is the
    documented re-access path).
    """
    active = db.scalar(
        select(GuestPortalToken).where(
            GuestPortalToken.booking_id == booking.id,
            GuestPortalToken.revoked_at.is_(None),
        )
    )
    if active is not None:
        if not rotate:
            raise ValueError("A portal token is already active for this booking.")
        active.revoked_at = now_utc()
        # Flush the revocation FIRST: the partial unique index would
        # otherwise reject the new active row in the same flush batch.
        db.flush()
        write_audit(
            db,
            action="PORTAL_TOKEN_REVOKED",
            resource_type="booking",
            resource_id=str(booking.id),
            actor_user_id=actor_user_id,
            metadata={"booking_id": str(booking.id)},
        )
    raw = generate_session_token()
    row = GuestPortalToken(
        booking_id=booking.id,
        token_hash=hash_token(raw),
    )
    db.add(row)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        db.rollback()  # loser of a partial-unique race: re-read the winner
        winner = db.scalar(
            select(GuestPortalToken).where(
                GuestPortalToken.booking_id == booking.id,
                GuestPortalToken.revoked_at.is_(None),
            )
        )
        if winner is None:
            raise ValueError("Portal token issuance conflicted; retry.") from None
        raise ValueError("A portal token is already active for this booking.") from None
    write_audit(
        db,
        action="PORTAL_TOKEN_ISSUED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={"booking_id": str(booking.id)},
    )
    return row, raw


def revoke_portal_token(
    db: DBSession, booking: Booking, *, actor_user_id: uuid.UUID
) -> GuestPortalToken:
    """Permanently revoke the booking's active token (never reactivated)."""
    active = db.scalar(
        select(GuestPortalToken).where(
            GuestPortalToken.booking_id == booking.id,
            GuestPortalToken.revoked_at.is_(None),
        )
    )
    if active is None:
        raise ValueError("No active portal token for this booking.")
    active.revoked_at = now_utc()
    write_audit(
        db,
        action="PORTAL_TOKEN_REVOKED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={"booking_id": str(booking.id)},
    )
    return active


def resolve_portal_token(
    db: DBSession, raw_token: str, *, touch: bool = False
) -> tuple[GuestPortalToken, Booking]:
    """Resolve a presented raw token to its token row and booking.

    Raises ``PortalAccessDenied`` for every failure mode (unknown,
    revoked, expired, cancelled booking) — callers must map all of
    these to the same generic 404 so the API cannot oracle token
    validity. Rate-limit registration is the router's responsibility.
    """
    if not raw_token or not isinstance(raw_token, str) or len(raw_token) > 256:
        raise PortalAccessDenied("Invalid portal token.")
    token_hash = hash_token(raw_token)
    row = db.scalar(select(GuestPortalToken).where(GuestPortalToken.token_hash == token_hash))
    if row is None or not compare_tokens(row.token_hash, token_hash):
        raise PortalAccessDenied("Invalid portal token.")
    booking = db.get(Booking, row.booking_id)
    if booking is None or not portal_active(booking, row):
        raise PortalAccessDenied("Invalid portal token.")
    if touch:
        row.last_accessed_at = now_utc()
    return row, booking


def portal_contact(db: DBSession, booking: Booking) -> dict:
    """Guest-safe hotel contact block (configured fields only)."""
    hotel = db.scalar(select(HotelInfo).where(HotelInfo.singleton_key == 1))
    if hotel is None:
        return {"contact_number": None, "email": None, "address": None}
    return {
        "contact_number": hotel.contact_number,
        "email": hotel.email,
        "address": hotel.address,
    }


def portal_overview(db: DBSession, booking: Booking) -> dict:
    """Booking fields a guest may see (no ids, no money, no PII)."""
    room = db.get(Room, booking.room_id)
    room_type = db.get(RoomType, booking.room_type_id)
    hotel = db.scalar(select(HotelInfo).where(HotelInfo.singleton_key == 1))
    deadline = portal_deadline(booking)
    return {
        "hotel_name": hotel.hotel_name if hotel else "Shree Shyam Home Stay",
        "booking_ref": booking.booking_ref,
        "room_number": room.room_number if room else "",
        "room_type": room_type.name if room_type else "",
        "check_in_date": booking.check_in_date.isoformat(),
        "check_out_date": booking.check_out_date.isoformat(),
        "nights": booking.nights,
        "status": booking.status,
        "checked_out_at": booking.checked_out_at.isoformat() if booking.checked_out_at else None,
        "expires_at": deadline.isoformat() if deadline else None,
        "contact": portal_contact(db, booking),
    }


def portal_menu(db: DBSession) -> list[dict]:
    """Active guest-visible menu, grouped by active category name."""
    categories = db.scalars(
        select(MenuCategory)
        .where(MenuCategory.is_active.is_(True))
        .order_by(MenuCategory.display_order.asc(), MenuCategory.name.asc())
    ).all()
    items = db.scalars(
        select(MenuItem)
        .where(MenuItem.is_available.is_(True))
        .order_by(MenuItem.display_order.asc(), MenuItem.name.asc())
    ).all()
    by_category: dict[str, list] = {}
    for item in items:
        by_category.setdefault(str(item.category_id), []).append(item)
    grouped: list[dict] = []
    for category in categories:
        children = by_category.get(str(category.id), [])
        if not children:
            continue
        grouped.append(
            {
                "category": category.name,
                "items": [
                    {
                        "name": item.name,
                        "description": item.description,
                        "price": item.price,
                        "image_url": item.image_url,
                        "is_vegetarian": item.is_vegetarian,
                    }
                    for item in children
                ],
            }
        )
    return grouped


def portal_cab(db: DBSession) -> list[dict]:
    """Active guest-visible cab providers (no internal ids)."""
    rows = db.scalars(
        select(CabInfo)
        .where(CabInfo.is_active.is_(True))
        .order_by(CabInfo.display_order.asc(), CabInfo.company_name.asc())
    ).all()
    return [
        {
            "company_name": row.company_name,
            "description": row.description,
            "contact_number": row.contact_number,
            "service_description": row.service_description,
        }
        for row in rows
    ]


def portal_wifi(db: DBSession) -> dict:
    """Wi-Fi network name/password, only when configured (never invented)."""
    hotel = db.scalar(select(HotelInfo).where(HotelInfo.singleton_key == 1))
    if hotel is None or not hotel.wifi_ssid:
        return {"ssid": None, "password": None}
    return {"ssid": hotel.wifi_ssid, "password": hotel.wifi_password}


def portal_final_receipt(db: DBSession, booking_id: uuid.UUID) -> Receipt | None:
    """Return the booking's stored FINAL receipt (never regenerated)."""
    return db.scalar(
        select(Receipt).where(Receipt.booking_id == booking_id, Receipt.kind == ReceiptKind.FINAL)
    )
