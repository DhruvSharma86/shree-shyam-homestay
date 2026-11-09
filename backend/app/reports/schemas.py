"""Pydantic schemas for the reporting endpoints (all Decimal money)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class FinancialSummaryResponse(BaseModel):
    """Ledger-based financial measures for the reporting period (UTC)."""

    from_date: date | None
    to_date: date | None
    room_charges: Decimal
    additional_charges: Decimal
    discounts: Decimal
    charge_reversals: Decimal
    gross_charges: Decimal
    net_payments: Decimal
    outstanding: Decimal


class CollectionRow(BaseModel):
    """One (date, method, stage) collection aggregate."""

    date: date
    method: str
    stage: str
    transactions: int
    original_total: Decimal
    reversal_total: Decimal
    net_total: Decimal


class CollectionReportResponse(BaseModel):
    """Daily collection rows plus period totals."""

    from_date: date | None
    to_date: date | None
    rows: list[CollectionRow]
    original_total: Decimal
    reversal_total: Decimal
    net_total: Decimal


class MethodRow(BaseModel):
    """One payment-method aggregate for the reporting period."""

    method: str
    transactions: int
    original_total: Decimal
    reversal_total: Decimal
    net_total: Decimal


class MethodReportResponse(BaseModel):
    """Method breakdown for the reporting period."""

    from_date: date | None
    to_date: date | None
    rows: list[MethodRow]
    original_total: Decimal
    reversal_total: Decimal
    net_total: Decimal


class OutstandingRow(BaseModel):
    """One booking's live (point-in-time) folio balance."""

    booking_id: str
    booking_ref: str
    room_number: str
    status: str
    total_charges: Decimal
    net_paid: Decimal
    balance: Decimal


class OutstandingReportResponse(BaseModel):
    """Live outstanding + credit balances for open folios."""

    snapshot: str
    rows: list[OutstandingRow]
    outstanding_total: Decimal
    credit_total: Decimal


class ReconciliationResponse(BaseModel):
    """Period reconciliation: charges vs originals vs reversals vs net."""

    from_date: date | None
    to_date: date | None
    charge_entries: Decimal
    original_payments: Decimal
    reversal_payments: Decimal
    net_payments: Decimal
    outstanding_in_period: Decimal
    credit_in_period: Decimal
    entry_count: int
    payment_count: int
    reversal_count: int


class ReversalItem(BaseModel):
    """One charge or payment reversal with its original's reference."""

    kind: str
    id: str
    booking_id: str
    booking_ref: str
    amount: Decimal
    reason: str | None
    reverses_id: str
    created_at: str


class ReversalsReportResponse(BaseModel):
    """Payment and charge reversals in the reporting period."""

    from_date: date | None
    to_date: date | None
    payment_reversal_total: Decimal
    charge_reversal_total: Decimal
    items: list[ReversalItem]
    total: int
    page: int
    page_size: int


class BookingsSummaryResponse(BaseModel):
    """Booking counts by status for stays overlapping the period."""

    from_date: date | None
    to_date: date | None
    total: int
    confirmed: int
    checked_in: int
    checked_out: int
    cancelled: int


class OccupancyResponse(BaseModel):
    """Room-night occupancy for the period (UTC, [check-in, check-out))."""

    from_date: date | None
    to_date: date | None
    occupied_room_nights: int
    available_room_nights: int
    occupancy_rate: Decimal
