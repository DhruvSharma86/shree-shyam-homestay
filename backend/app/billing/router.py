"""Billing endpoints: folio view, charges, discounts, reversals, payments.

Only billing service functions write financial tables (never route
handlers). Payment history is read-only in Phase 4.1 — payment-writing
endpoints arrive in Phase 4.2. See app/billing/service.py for rules.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission, verify_csrf
from app.billing.schemas import (
    ChargeCreate,
    DiscountCreate,
    FolioEntryResponse,
    FolioResponse,
    PaymentListResponse,
    PaymentResponse,
    ReversalCreate,
)
from app.billing.service import (
    FolioClosedError,
    InvalidReversalError,
    NegativeBalanceError,
    add_charge,
    add_discount,
    ensure_initial_charge,
    folio_totals,
    reverse_entry,
)
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.booking import Booking
from app.models.folio_entry import FolioEntry
from app.models.payment import Payment
from app.models.user import User

router = APIRouter(prefix="/bookings", tags=["billing"])


def _booking_row(db: DBSession, booking_id: uuid.UUID) -> Booking:
    row = db.get(Booking, booking_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Booking not found.")
    return row


def _entry_response(row: FolioEntry) -> FolioEntryResponse:
    return FolioEntryResponse(
        id=row.id,
        booking_id=row.booking_id,
        entry_type=row.entry_type,
        description=row.description,
        quantity=row.quantity,
        unit_amount=row.unit_amount,
        amount=row.amount,
        is_initial=row.is_initial,
        reverses_entry_id=row.reverses_entry_id,
        created_at=row.created_at.isoformat(),
    )


def _map_billing_error(exc: Exception) -> ApiError:
    if isinstance(exc, FolioClosedError):
        return ApiError(409, "CONFLICT", str(exc))
    if isinstance(exc, (InvalidReversalError, NegativeBalanceError)):
        return ApiError(422, "VALIDATION_ERROR", str(exc))
    if isinstance(exc, ValueError):
        return ApiError(422, "VALIDATION_ERROR", str(exc))
    raise exc


@router.get("/{booking_id}/folio", response_model=FolioResponse)
def get_folio(
    booking_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_RECEIPTS_READ)),
) -> FolioResponse:
    """Return the folio view (ledger + derived totals).

    Also performs backfill-by-demand: a pre-4.1 booking that has no
    initial entry yet gets its snapshot charge created here (idempotent —
    never a second charge). Cancelled bookings stay history-only.
    """
    booking = _booking_row(db, booking_id)
    ensure_initial_charge(db, booking, actor_user_id=actor.id)
    rows = db.scalars(
        select(FolioEntry)
        .where(FolioEntry.booking_id == booking_id)
        .order_by(FolioEntry.created_at.asc())
    ).all()
    total_charges, total_paid, balance_due = folio_totals(db, booking_id)
    payment_count = (
        db.scalar(select(func.count()).select_from(Payment).where(Payment.booking_id == booking_id))
        or 0
    )
    return FolioResponse(
        booking_id=booking.id,
        booking_ref=booking.booking_ref,
        booking_status=booking.status,
        entries=[_entry_response(r) for r in rows],
        total_charges=total_charges,
        total_paid=total_paid,
        balance_due=balance_due,
        payment_count=int(payment_count),
    )


@router.post("/{booking_id}/folio/charges", response_model=FolioEntryResponse, status_code=201)
def post_charge(
    booking_id: uuid.UUID,
    payload: ChargeCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_CHARGES_WRITE)),
) -> FolioEntryResponse:
    """Append an ADDITIONAL_CHARGE to the folio."""
    verify_csrf(request)
    booking = _booking_row(db, booking_id)
    try:
        entry = add_charge(
            db,
            booking,
            description=payload.description,
            quantity=payload.quantity,
            unit_amount=payload.unit_amount,
            actor_user_id=actor.id,
        )
    except (FolioClosedError, InvalidReversalError, NegativeBalanceError, ValueError) as exc:
        raise _map_billing_error(exc) from None
    db.commit()
    db.refresh(entry)
    return _entry_response(entry)


@router.post("/{booking_id}/folio/discounts", response_model=FolioEntryResponse, status_code=201)
def post_discount(
    booking_id: uuid.UUID,
    payload: DiscountCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_DISCOUNTS_WRITE)),
) -> FolioEntryResponse:
    """Append a DISCOUNT (ADMIN-only). Reason is mandatory."""
    verify_csrf(request)
    booking = _booking_row(db, booking_id)
    try:
        entry = add_discount(
            db,
            booking,
            amount=payload.amount,
            reason=payload.reason,
            actor_user_id=actor.id,
        )
    except (FolioClosedError, InvalidReversalError, NegativeBalanceError, ValueError) as exc:
        raise _map_billing_error(exc) from None
    db.commit()
    db.refresh(entry)
    return _entry_response(entry)


@router.post("/{booking_id}/folio/reversals", response_model=FolioEntryResponse, status_code=201)
def post_reversal(
    booking_id: uuid.UUID,
    payload: ReversalCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_CHARGES_WRITE)),
) -> FolioEntryResponse:
    """Reverse a charge/discount via an offsetting REVERSAL entry."""
    verify_csrf(request)
    booking = _booking_row(db, booking_id)
    original = db.get(FolioEntry, payload.entry_id)
    if original is None:
        raise ApiError(404, "NOT_FOUND", "Folio entry not found.")
    try:
        entry = reverse_entry(db, booking, original, reason=payload.reason, actor_user_id=actor.id)
    except (FolioClosedError, InvalidReversalError, NegativeBalanceError, ValueError) as exc:
        raise _map_billing_error(exc) from None
    db.commit()
    db.refresh(entry)
    return _entry_response(entry)


@router.get("/{booking_id}/payments", response_model=PaymentListResponse)
def list_payments(
    booking_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_RECEIPTS_READ)),
) -> PaymentListResponse:
    """List the booking's payment history (none until Phase 4.2 writes)."""
    _booking_row(db, booking_id)
    stmt = select(Payment).where(Payment.booking_id == booking_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        PaymentResponse(
            id=r.id,
            booking_id=r.booking_id,
            amount=r.amount,
            mode=r.mode,
            payment_stage=r.payment_stage,
            reference_note=r.reference_note,
            reverses_payment_id=r.reverses_payment_id,
            received_at=r.received_at.isoformat(),
        )
        for r in rows
    ]
    return PaymentListResponse(items=items, total=int(total), page=page, page_size=page_size)
