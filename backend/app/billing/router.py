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
    PaymentCreate,
    PaymentListResponse,
    PaymentResponse,
    PaymentReversalCreate,
    ReversalCreate,
)
from app.billing.service import (
    FolioClosedError,
    InvalidReversalError,
    NegativeBalanceError,
    OverpaymentError,
    PaymentReversalError,
    add_charge,
    add_discount,
    ensure_initial_charge,
    folio_totals,
    record_payment,
    reverse_entry,
    reverse_payment,
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
    if isinstance(
        exc, (InvalidReversalError, NegativeBalanceError, PaymentReversalError, OverpaymentError)
    ):
        return ApiError(422, "VALIDATION_ERROR", str(exc))
    if isinstance(exc, ValueError):
        return ApiError(422, "VALIDATION_ERROR", str(exc))
    raise exc


_BILLING_ERRORS = (
    FolioClosedError,
    InvalidReversalError,
    NegativeBalanceError,
    PaymentReversalError,
    OverpaymentError,
    ValueError,
)


def _payment_response(row: Payment) -> PaymentResponse:
    return PaymentResponse(
        id=row.id,
        booking_id=row.booking_id,
        amount=row.amount,
        mode=row.mode,
        payment_stage=row.payment_stage,
        reference_note=row.reference_note,
        is_reversal=row.is_reversal,
        reverses_payment_id=row.reverses_payment_id,
        received_at=row.received_at.isoformat(),
    )


def _folio_view(db: DBSession, booking: Booking) -> FolioResponse:
    """Build the folio view (read-only — shared by GET and initialize)."""
    rows = db.scalars(
        select(FolioEntry)
        .where(FolioEntry.booking_id == booking.id)
        .order_by(FolioEntry.created_at.asc())
    ).all()
    total_charges, total_paid, balance_due = folio_totals(db, booking.id)
    payment_count = (
        db.scalar(select(func.count()).select_from(Payment).where(Payment.booking_id == booking.id))
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


@router.get("/{booking_id}/folio", response_model=FolioResponse)
def get_folio(
    booking_id: uuid.UUID,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_RECEIPTS_READ)),
) -> FolioResponse:
    """Return the folio view (ledger + derived totals).

    Read-only: never writes. Pre-4.1 bookings without an initial entry
    are initialized explicitly via ``POST .../folio/initialize`` (never
    implicitly here).
    """
    booking = _booking_row(db, booking_id)
    return _folio_view(db, booking)


@router.post("/{booking_id}/folio/initialize", response_model=FolioResponse, status_code=201)
def initialize_folio(
    booking_id: uuid.UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_CHARGES_WRITE)),
) -> FolioResponse:
    """Explicitly create the missing initial charge (backfill, idempotent).

    The auditable replacement for the old implicit read-side backfill:
    writes at most one entry (the snapshot charge) plus its audit row.
    Cancelled bookings never receive an initial charge.
    """
    verify_csrf(request)
    booking = _booking_row(db, booking_id)
    ensure_initial_charge(db, booking, actor_user_id=actor.id)
    db.commit()
    return _folio_view(db, booking)


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
    """List the booking's payment history (paginated, newest first)."""
    _booking_row(db, booking_id)
    stmt = select(Payment).where(Payment.booking_id == booking_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return PaymentListResponse(
        items=[_payment_response(r) for r in rows], total=int(total), page=page, page_size=page_size
    )


@router.post("/{booking_id}/payments", response_model=PaymentResponse, status_code=201)
def post_payment(
    booking_id: uuid.UUID,
    payload: PaymentCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_PAYMENTS_WRITE)),
) -> PaymentResponse:
    """Record a staff-collected payment (both roles).

    Overpayment is blocked by default; an ADMIN with
    ``overpayment_reason`` may authorize it (audited).
    """
    verify_csrf(request)
    booking = _booking_row(db, booking_id)
    try:
        payment = record_payment(
            db,
            booking,
            amount=payload.amount,
            mode=payload.mode,
            payment_stage=payload.payment_stage,
            reference_note=payload.reference_note,
            overpayment_reason=payload.overpayment_reason,
            actor_user_id=actor.id,
            actor_role=str(actor.role),
        )
    except (
        FolioClosedError,
        InvalidReversalError,
        NegativeBalanceError,
        PaymentReversalError,
        OverpaymentError,
        ValueError,
    ) as exc:
        raise _map_billing_error(exc) from None
    db.commit()
    db.refresh(payment)
    return _payment_response(payment)


@router.post(
    "/{booking_id}/payments/{payment_id}/reverse", response_model=PaymentResponse, status_code=201
)
def post_payment_reversal(
    booking_id: uuid.UUID,
    payment_id: uuid.UUID,
    payload: PaymentReversalCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.BILLING_PAYMENTS_WRITE)),
) -> PaymentResponse:
    """Reverse a payment via a linked reversal record (ADMIN-only, D3)."""
    verify_csrf(request)
    if str(actor.role).upper() != "ADMIN":
        raise ApiError(403, "FORBIDDEN", "Only ADMIN may reverse payments.")
    booking = _booking_row(db, booking_id)
    original = db.get(Payment, payment_id)
    if original is None:
        raise ApiError(404, "NOT_FOUND", "Payment not found.")
    try:
        reversal = reverse_payment(
            db, booking, original, reason=payload.reason, actor_user_id=actor.id
        )
    except (
        FolioClosedError,
        InvalidReversalError,
        NegativeBalanceError,
        PaymentReversalError,
        OverpaymentError,
        ValueError,
    ) as exc:
        raise _map_billing_error(exc) from None
    db.commit()
    db.refresh(reversal)
    return _payment_response(reversal)
