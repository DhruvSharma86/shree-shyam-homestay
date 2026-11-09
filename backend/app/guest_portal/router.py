"""Guest portal endpoints — unauthenticated, token-scoped, read-only.

Routes live under ``/guest-portal/{token}/...`` and never require
staff sessions (bearer link isolation instead). Every response carries
``no-store`` cache headers. Failures map to one generic 404 so the
API cannot oracle token validity; rate limiting guards brute force.
"""

import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission, verify_csrf
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.guest_portal import service as portal
from app.guest_portal.schemas import (
    PortalCabItem,
    PortalCabResponse,
    PortalLocalInfo,
    PortalMenuCategory,
    PortalMenuItem,
    PortalMenuResponse,
    PortalOverviewResponse,
    PortalReceiptResponse,
    PortalTokenAdminResponse,
    PortalTokenIssuedResponse,
    PortalTourismResponse,
    PortalTourPackage,
    PortalWifiResponse,
)
from app.models.booking import Booking
from app.models.guest_portal_token import GuestPortalToken
from app.models.user import User

router = APIRouter(prefix="/guest-portal", tags=["guest-portal"])

GENERIC_404 = ApiError(404, "NOT_FOUND", "Portal page not found.")
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, private",
    "Pragma": "no-cache",
}


def _portal_json(payload, status_code: int = 200) -> JSONResponse:
    """JSON response with no-store cache headers."""
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        status_code=status_code, content=jsonable_encoder(payload), headers=_NO_STORE_HEADERS
    )


def _resolve(db: DBSession, raw_token: str) -> Booking:
    """Resolve a token to its booking or raise the generic 404.

    Also applies brute-force guarding and records a last-accessed
    timestamp (a GET response may update that one metadata column).
    """
    if len(raw_token) > 256:
        raise GENERIC_404
    if portal.is_portal_rate_limited(raw_token):
        raise ApiError(429, "RATE_LIMITED", "Too many failed accesses; try again later.")
    try:
        _, booking = portal.resolve_portal_token(db, raw_token, touch=True)
    except portal.PortalAccessDenied:
        portal.register_portal_attempt(raw_token)
        raise GENERIC_404 from None
    return booking


@router.get("/{token}/overview", response_model=PortalOverviewResponse)
def portal_overview(
    token: str,
    db: DBSession = Depends(get_db),
) -> JSONResponse:
    """Booking-relevant fields only (no ids, no money, no PII)."""
    booking = _resolve(db, token)
    db.commit()
    return _portal_json(portal.portal_overview(db, booking))


@router.get("/{token}/menu", response_model=PortalMenuResponse)
def portal_menu(
    token: str,
    db: DBSession = Depends(get_db),
) -> JSONResponse:
    """Active guest-visible menu."""
    _resolve(db, token)
    db.commit()
    categories = [
        PortalMenuCategory(
            category=group["category"],
            items=[
                PortalMenuItem(
                    name=item["name"],
                    description=item["description"],
                    price=item["price"],
                    image_url=item["image_url"],
                    is_vegetarian=item["is_vegetarian"],
                )
                for item in group["items"]
            ],
        )
        for group in portal.portal_menu(db)
    ]
    return _portal_json(PortalMenuResponse(categories=categories))


@router.get("/{token}/cab", response_model=PortalCabResponse)
def portal_cab(
    token: str,
    db: DBSession = Depends(get_db),
) -> JSONResponse:
    """Active guest-visible cab providers."""
    _resolve(db, token)
    db.commit()
    providers = [
        PortalCabItem(
            company_name=provider["company_name"],
            description=provider["description"],
            contact_number=provider["contact_number"],
            service_description=provider["service_description"],
        )
        for provider in portal.portal_cab(db)
    ]
    return _portal_json(PortalCabResponse(providers=providers))


@router.get("/{token}/wifi", response_model=PortalWifiResponse)
def portal_wifi(
    token: str,
    db: DBSession = Depends(get_db),
) -> JSONResponse:
    """Wi-Fi name/password only when configured (never invented)."""
    _resolve(db, token)
    db.commit()
    return _portal_json(portal.portal_wifi(db))


@router.get("/{token}/tourism", response_model=PortalTourismResponse)
def portal_tourism(
    token: str,
    db: DBSession = Depends(get_db),
) -> JSONResponse:
    """Active tour packages and local information (empty when unconfigured)."""
    _resolve(db, token)
    db.commit()
    data = portal.portal_tourism(db)
    return _portal_json(
        PortalTourismResponse(
            packages=[PortalTourPackage(**p) for p in data["packages"]],
            local_info=[PortalLocalInfo(**i) for i in data["local_info"]],
        )
    )


@router.get("/{token}/receipt", response_model=PortalReceiptResponse)
def portal_receipt(
    token: str,
    db: DBSession = Depends(get_db),
) -> JSONResponse:
    """Final receipt metadata (404 when not issued yet)."""
    booking = _resolve(db, token)
    db.commit()
    receipt = portal.portal_final_receipt(db, booking.id)
    if receipt is None:
        raise ApiError(404, "NOT_FOUND", "No final receipt is available for this stay.")
    return _portal_json(
        PortalReceiptResponse(
            receipt_ref=receipt.receipt_ref,
            kind=receipt.kind,
            content_hash=receipt.content_hash,
        )
    )


@router.get("/{token}/receipt/download")
def portal_receipt_download(
    token: str,
    db: DBSession = Depends(get_db),
) -> Response:
    """Download this booking's stored FINAL receipt PDF (never generated)."""
    booking = _resolve(db, token)
    db.commit()
    receipt = portal.portal_final_receipt(db, booking.id)
    if receipt is None:
        raise ApiError(404, "NOT_FOUND", "No final receipt is available for this stay.")
    return Response(
        content=receipt.pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{receipt.receipt_ref}.pdf"',
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
        },
    )


# --- Staff administration (ADMIN only) -------------------------------------


def _staff_booking(db: DBSession, booking_id: uuid.UUID) -> Booking:
    row = db.get(Booking, booking_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Booking not found.")
    return row


@router.get("/admin-status/{booking_id}", response_model=PortalTokenAdminResponse)
def portal_admin_status(
    booking_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PORTAL_TOKENS_MANAGE)),
) -> PortalTokenAdminResponse:
    """Active-token status for staff (never the raw token)."""
    booking = _staff_booking(db, booking_id)
    active = db.scalar(
        select(GuestPortalToken).where(
            GuestPortalToken.booking_id == booking.id,
            GuestPortalToken.revoked_at.is_(None),
        )
    )
    return PortalTokenAdminResponse(
        booking_id=str(booking.id), active=active is not None, issued=active is not None
    )


@router.post("/admin-revoke/{booking_id}", response_model=PortalTokenAdminResponse)
def portal_admin_revoke(
    booking_id: uuid.UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PORTAL_TOKENS_MANAGE)),
) -> PortalTokenAdminResponse:
    """Permanently revoke the booking's active token (never reactivatable)."""
    verify_csrf(request)
    booking = _staff_booking(db, booking_id)
    try:
        rev = portal.revoke_portal_token(db, booking, actor_user_id=actor.id)
    except ValueError:
        raise ApiError(404, "NOT_FOUND", "No active portal token for this booking.") from None
    db.commit()
    return PortalTokenAdminResponse(booking_id=str(rev.booking_id), active=False, issued=False)


@router.post("/admin-rotate/{booking_id}", response_model=PortalTokenIssuedResponse)
def portal_admin_rotate(
    booking_id: uuid.UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PORTAL_TOKENS_MANAGE)),
) -> PortalTokenIssuedResponse:
    """Revoke the current token and issue a fresh one (raw shown once)."""
    verify_csrf(request)
    booking = _staff_booking(db, booking_id)
    try:
        _, raw = portal.issue_portal_token(db, booking, actor_user_id=actor.id, rotate=True)
    except ValueError as exc:
        raise ApiError(409, "CONFLICT", str(exc)) from None
    db.commit()
    return PortalTokenIssuedResponse(booking_id=str(booking.id), portal_access_token=raw)
