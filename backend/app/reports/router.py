"""Reporting endpoints (ADMIN-only). All read-only, Decimal-safe.

CSV exports reuse the same service functions as the JSON reports, so the
two views can never disagree. Exported columns contain enums, dates
and numbers only (no free-text fields), so spreadsheet formula injection
is impossible; cells are still prefixed for defence in depth.
"""

import csv
import io
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import require_permission
from app.core.db import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.reports import service as reports_service
from app.reports.schemas import (
    BookingsSummaryResponse,
    CollectionReportResponse,
    FinancialSummaryResponse,
    MethodReportResponse,
    OccupancyResponse,
    OutstandingReportResponse,
    ReconciliationResponse,
    ReversalsReportResponse,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _range(from_date: date | None, to_date: date | None) -> None:
    if from_date is not None and to_date is not None and from_date > to_date:
        from app.core.errors import ApiError

        raise ApiError(422, "VALIDATION_ERROR", "from_date must be on or before to_date.")


def _csv(payload: dict[str, Any], headers: list[tuple[str, str]]) -> Response:
    """Render a dict payload as CSV with sanitized cells."""
    items = payload.get("rows") or payload.get("items") or []
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([title for _, title in headers])
    for row in items:
        line: list[str] = []
        for key, _ in headers:
            value = row.get(key, "")
            cell = f"{value}"
            if cell[:1] in ("=", "+", "-", "@"):
                cell = "'" + cell
            line.append(cell)
        writer.writerow(line)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=report-export.csv",
            "Cache-Control": "no-store",
        },
    )


@router.get("/financial/summary", response_model=FinancialSummaryResponse)
def financial_summary(
    from_date: date | None = None,
    to_date: date | None = None,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> FinancialSummaryResponse:
    """Ledger measures for the period (UTC)."""
    _range(from_date, to_date)
    return FinancialSummaryResponse(**reports_service.financial_summary(db, from_date, to_date))


@router.get("/financial/collections", response_model=CollectionReportResponse)
def collections(
    from_date: date | None = None,
    to_date: date | None = None,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> CollectionReportResponse:
    """Daily collections by (method, stage) for the period (UTC)."""
    _range(from_date, to_date)
    return CollectionReportResponse(**reports_service.collections(db, from_date, to_date))


@router.get("/financial/collections/export.csv")
def collections_export(
    from_date: date | None = None,
    to_date: date | None = None,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> Response:
    """Collections report as CSV (same source as the JSON report)."""
    _range(from_date, to_date)
    payload = reports_service.collections(db, from_date, to_date)
    return _csv(
        payload,
        [
            ("date", "date"),
            ("method", "method"),
            ("stage", "stage"),
            ("transactions", "transactions"),
            ("original_total", "original_total"),
            ("reversal_total", "reversal_total"),
            ("net_total", "net_total"),
        ],
    )


@router.get("/financial/payment-methods", response_model=MethodReportResponse)
def payment_methods(
    from_date: date | None = None,
    to_date: date | None = None,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> MethodReportResponse:
    """Whole-period breakdown by payment method (UTC)."""
    _range(from_date, to_date)
    return MethodReportResponse(**reports_service.payment_methods(db, from_date, to_date))


@router.get("/financial/outstanding", response_model=OutstandingReportResponse)
def outstanding(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> OutstandingReportResponse:
    """Live (point-in-time) folios with non-zero balances."""
    return OutstandingReportResponse(**reports_service.outstanding_report(db, page, page_size))


@router.get("/financial/outstanding/export.csv")
def outstanding_export(
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> Response:
    """Outstanding report as CSV (same source as the JSON report)."""
    payload = reports_service.outstanding_report(db, 1, 500)
    return _csv(
        payload,
        [
            ("booking_ref", "booking_ref"),
            ("room_number", "room_number"),
            ("status", "status"),
            ("total_charges", "total_charges"),
            ("net_paid", "net_paid"),
            ("balance", "balance"),
        ],
    )


@router.get("/financial/reconciliation", response_model=ReconciliationResponse)
def reconciliation(
    from_date: date | None = None,
    to_date: date | None = None,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> ReconciliationResponse:
    """Period reconciliation: charges vs originals vs reversals vs net."""
    _range(from_date, to_date)
    return ReconciliationResponse(**reports_service.reconciliation(db, from_date, to_date))


@router.get("/financial/reversals", response_model=ReversalsReportResponse)
def reversals(
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> ReversalsReportResponse:
    """Charge and payment reversals in the period (paginated, linked)."""
    _range(from_date, to_date)
    return ReversalsReportResponse(
        **reports_service.reversals_report(db, from_date, to_date, page, page_size)
    )


@router.get("/bookings/summary", response_model=BookingsSummaryResponse)
def bookings_summary(
    from_date: date | None = None,
    to_date: date | None = None,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> BookingsSummaryResponse:
    """Booking counts by status for stays overlapping the period."""
    _range(from_date, to_date)
    return BookingsSummaryResponse(**reports_service.bookings_summary(db, from_date, to_date))


@router.get("/bookings/occupancy", response_model=OccupancyResponse)
def occupancy(
    from_date: date | None = None,
    to_date: date | None = None,
    db: DBSession = Depends(get_db),
    actor: User = Depends(require_permission(Permission.REPORTS_FINANCIAL_READ)),
) -> OccupancyResponse:
    """Occupied vs available room-nights (capacity assumes every active room was available)."""
    _range(from_date, to_date)
    return OccupancyResponse(**reports_service.occupancy(db, from_date, to_date))
