"""Pydantic schemas for the billing endpoints."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class FolioEntryResponse(BaseModel):
    """One folio ledger line (immutable once written)."""

    id: uuid.UUID
    booking_id: uuid.UUID
    entry_type: str
    description: str
    quantity: Decimal
    unit_amount: Decimal | None = None
    amount: Decimal
    is_initial: bool
    reverses_entry_id: uuid.UUID | None = None
    created_at: str


class FolioResponse(BaseModel):
    """Folio view: ledger lines plus derived totals and balance due."""

    booking_id: uuid.UUID
    booking_ref: str
    booking_status: str
    entries: list[FolioEntryResponse]
    total_charges: Decimal
    total_paid: Decimal
    balance_due: Decimal
    payment_count: int


class ChargeCreate(BaseModel):
    """Add an additional charge (ADDITIONAL_CHARGE)."""

    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    unit_amount: Decimal = Field(ge=0)


class DiscountCreate(BaseModel):
    """Apply a discount (DISCOUNT, ADMIN only — reason mandatory)."""

    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


class ReversalCreate(BaseModel):
    """Reverse a folio entry (REVERSAL – mandatory reason)."""

    entry_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=1000)


class PaymentCreate(BaseModel):
    """Record a staff-collected payment (Phase 4.2)."""

    amount: Decimal = Field(gt=0)
    mode: str = "CASH"
    payment_stage: str = "OTHER"
    reference_note: str | None = None
    overpayment_reason: str | None = None


class PaymentReversalCreate(BaseModel):
    """Reverse a payment (ADMIN-only, reason mandatory)."""

    reason: str = Field(min_length=1, max_length=1000)


class ReceiptResponse(BaseModel):
    """Issued final-receipt metadata (download via the download endpoint)."""

    receipt_id: uuid.UUID
    booking_id: uuid.UUID
    receipt_ref: str
    kind: str
    content_hash: str


class PaymentResponse(BaseModel):
    """One payment record (read-only in Phase 4.1)."""

    id: uuid.UUID
    booking_id: uuid.UUID
    amount: Decimal
    mode: str
    payment_stage: str
    reference_note: str | None = None
    is_reversal: bool
    reverses_payment_id: uuid.UUID | None = None
    received_at: str


class PaymentListResponse(BaseModel):
    """Paginated payment history for a booking."""

    items: list[PaymentResponse]
    total: int
    page: int
    page_size: int
