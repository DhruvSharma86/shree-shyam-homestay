"""Financial reporting — read-only aggregates over the ledger.

All figures derive from folio/payment rows (never stored report tables).
Money is Decimal; date filtering uses half-open UTC ranges
``[from, to + 1 day)`` — an entry dated exactly ``to`` belongs to the
period end. Hotel timezone: `hotel_info` carries no timezone setting,
so all reporting treats timestamps as UTC (documented assumption).

- `financial_summary`: entry-kind sums (charges-created in period) and
  net payments (received in period).
- `collections`: (date, method, stage) rows from payment rows.
- `payment_methods`: per-method aggregates for the whole period.
- `outstanding`: a **live snapshot** (current ledger state, not a
  historical reconstruction), cross-joined to booking refs/rooms.
- `reconciliation`: period-only charge/payment/reversal reconciliation.
- `bookings_summary` / `occupancy`: stay-overlap counts under the
  [check-in, check-out) convention (cancelled excluded from occupancy).
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.billing.service import folio_totals
from app.models.booking import Booking
from app.models.folio_entry import FolioEntry, FolioEntryType
from app.models.payment import Payment
from app.models.room import Room, RoomOperationalStatus

CENT = Decimal("0.01")


def _bounds(
    from_date: date | None, to_date: date | None
) -> tuple[datetime | None, datetime | None]:
    """Validate and convert [from, to] to a half-open UTC range."""
    if from_date is not None and to_date is not None and from_date > to_date:
        raise ValueError("from_date must be on or before to_date.")
    if from_date is None:
        start = None
    else:
        start = datetime.combine(from_date, time.min)
    if to_date is None:
        end = None
    else:
        end = datetime.combine(to_date, time.min) + timedelta(days=1)
    return start, end


def _in_range(created_at: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    """Return True when a possibly-None timestamp lies in [start, end).

    Row timestamps may be naive (SQLite) or timezone-aware (PostgreSQL);
    they are both treated as UTC, so the comparison ignores tzinfo.
    """
    if created_at is None:
        return False
    ts = created_at.replace(tzinfo=None)
    if start is not None and ts < start:
        return False
    if end is not None and ts >= end:
        return False
    return True


def _entries_in_range(
    db: DBSession, start: datetime | None, end: datetime | None
) -> list[FolioEntry]:
    rows = db.scalars(select(FolioEntry)).all()
    return [r for r in rows if _in_range(r.created_at, start, end)]


def _payments_in_range(
    db: DBSession, start: datetime | None, end: datetime | None
) -> list[Payment]:
    rows = db.scalars(select(Payment)).all()
    return [r for r in rows if _in_range(r.received_at, start, end)]


def financial_summary(
    db: DBSession, from_date: date | None, to_date: date | None
) -> dict[str, Any]:
    """Period ledger measures (JSON-shaped dict)."""
    start, end = _bounds(from_date, to_date)
    entries = _entries_in_range(db, start, end)
    payments = _payments_in_range(db, start, end)
    by_type: dict[str, Decimal] = defaultdict(Decimal)
    for entry in entries:
        by_type[entry.entry_type] += entry.amount
    originals = sum((p.amount for p in payments if not p.is_reversal), Decimal(0))
    reversals = sum((p.amount for p in payments if p.is_reversal), Decimal(0))
    gross = by_type[FolioEntryType.ROOM_CHARGE] + by_type[FolioEntryType.ADDITIONAL_CHARGE]
    net = originals - reversals
    outstanding = Decimal(sum(by_type.values(), Decimal(0))) - net
    return {
        "from_date": from_date,
        "to_date": to_date,
        "room_charges": by_type[FolioEntryType.ROOM_CHARGE].quantize(CENT),
        "additional_charges": by_type[FolioEntryType.ADDITIONAL_CHARGE].quantize(CENT),
        "discounts": by_type[FolioEntryType.DISCOUNT].quantize(CENT),
        "charge_reversals": by_type[FolioEntryType.REVERSAL].quantize(CENT),
        "gross_charges": gross.quantize(CENT),
        "net_payments": net.quantize(CENT),
        "outstanding": outstanding.quantize(CENT),
    }


def collections(db: DBSession, from_date: date | None, to_date: date | None) -> dict[str, Any]:
    """Per-(date, method, stage) collections with period totals."""
    start, end = _bounds(from_date, to_date)
    rows: dict[tuple[date, str, str], dict[str, Any]] = {}
    for payment in _payments_in_range(db, start, end):
        key = (payment.received_at.date(), payment.mode, payment.payment_stage)
        bucket = rows.setdefault(
            key, {"transactions": 0, "original": Decimal(0), "reversal": Decimal(0)}
        )
        bucket["transactions"] += 1
        if payment.is_reversal:
            bucket["reversal"] += payment.amount
        else:
            bucket["original"] += payment.amount
    ordered = sorted(rows.items())
    original_total = sum((b["original"] for _, b in ordered), Decimal(0))
    reversal_total = sum((b["reversal"] for _, b in ordered), Decimal(0))
    return {
        "from_date": from_date,
        "to_date": to_date,
        "rows": [
            {
                "date": day,
                "method": mode,
                "stage": stage,
                "transactions": bucket["transactions"],
                "original_total": bucket["original"].quantize(CENT),
                "reversal_total": bucket["reversal"].quantize(CENT),
                "net_total": (bucket["original"] - bucket["reversal"]).quantize(CENT),
            }
            for (day, mode, stage), bucket in ordered
        ],
        "original_total": original_total.quantize(CENT),
        "reversal_total": reversal_total.quantize(CENT),
        "net_total": (original_total - reversal_total).quantize(CENT),
    }


def payment_methods(db: DBSession, from_date: date | None, to_date: date | None) -> dict[str, Any]:
    """Per-method aggregates for the whole period."""
    start, end = _bounds(from_date, to_date)
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"transactions": 0, "original": Decimal(0), "reversal": Decimal(0)}
    )
    for payment in _payments_in_range(db, start, end):
        bucket = buckets[payment.mode]
        bucket["transactions"] += 1
        if payment.is_reversal:
            bucket["reversal"] += payment.amount
        else:
            bucket["original"] += payment.amount
    ordered = sorted(buckets.items())
    original_total = sum((b["original"] for _, b in ordered), Decimal(0))
    reversal_total = sum((b["reversal"] for _, b in ordered), Decimal(0))
    return {
        "from_date": from_date,
        "to_date": to_date,
        "rows": [
            {
                "method": mode,
                "transactions": bucket["transactions"],
                "original_total": bucket["original"].quantize(CENT),
                "reversal_total": bucket["reversal"].quantize(CENT),
                "net_total": (bucket["original"] - bucket["reversal"]).quantize(CENT),
            }
            for mode, bucket in ordered
        ],
        "original_total": original_total.quantize(CENT),
        "reversal_total": reversal_total.quantize(CENT),
        "net_total": (original_total - reversal_total).quantize(CENT),
    }


def outstanding_report(db: DBSession, page: int, page_size: int) -> dict[str, Any]:
    """Live (point-in-time) folios with non-zero balances.

    Checked-out (settled) and cancelled bookings never appear here; the
    ledger behind each row still records them. Credits (balance < 0)
    are shown distinctly from outstanding dues.
    """
    rows: list[dict[str, Any]] = []
    for booking in db.scalars(
        select(Booking).where(
            Booking.status.in_(["CONFIRMED", "CHECKED_IN"]),
        )
    ).all():
        charges, paid, balance = folio_totals(db, booking.id)
        if balance == 0:
            continue
        room = db.get(Room, booking.room_id)
        rows.append(
            {
                "booking_id": str(booking.id),
                "booking_ref": booking.booking_ref,
                "room_number": room.room_number if room else "",
                "status": booking.status,
                "total_charges": charges,
                "net_paid": paid,
                "balance": balance,
            }
        )
    rows.sort(key=lambda r: (r["balance"] < 0, r["balance"]))
    total = len(rows)
    offset = (page - 1) * page_size
    return {
        "snapshot": "live-current",
        "rows": rows[offset : offset + page_size],
        "outstanding_total": sum(
            (r["balance"] for r in rows if r["balance"] > 0), Decimal(0)
        ).quantize(CENT),
        "credit_total": sum(
            (-r["balance"] for r in rows if r["balance"] < 0), Decimal(0)
        ).quantize(CENT),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def reconciliation(db: DBSession, from_date: date | None, to_date: date | None) -> dict[str, Any]:
    """Period reconciliation of charges vs originals vs reversals vs net."""
    start, end = _bounds(from_date, to_date)
    entries = _entries_in_range(db, start, end)
    payments = _payments_in_range(db, start, end)
    charges_in_period = Decimal(sum((e.amount for e in entries), Decimal(0)))
    original_payments = sum((p.amount for p in payments if not p.is_reversal), Decimal(0))
    reversal_payments = sum((p.amount for p in payments if p.is_reversal), Decimal(0))
    net = original_payments - reversal_payments
    outstanding_in_period = charges_in_period - net
    credit_in_period = -outstanding_in_period if outstanding_in_period < 0 else Decimal(0)
    return {
        "from_date": from_date,
        "to_date": to_date,
        "charge_entries": charges_in_period.quantize(CENT),
        "original_payments": original_payments.quantize(CENT),
        "reversal_payments": reversal_payments.quantize(CENT),
        "net_payments": net.quantize(CENT),
        "outstanding_in_period": outstanding_in_period.quantize(CENT)
        if outstanding_in_period > 0
        else Decimal(0).quantize(CENT),
        "credit_in_period": credit_in_period.quantize(CENT),
        "entry_count": len(entries),
        "payment_count": len(payments),
        "reversal_count": sum(1 for p in payments if p.is_reversal),
    }


def reversals_report(
    db: DBSession, from_date: date | None, to_date: date | None, page: int, page_size: int
) -> dict[str, Any]:
    """Charge and payment reversals in the period (paginated, linked rows)."""
    start, end = _bounds(from_date, to_date)
    items: list[dict[str, Any]] = []
    charge_total = Decimal(0)
    for entry in _entries_in_range(db, start, end):
        if entry.entry_type != FolioEntryType.REVERSAL:
            continue
        charge_total += entry.amount
        items.append(
            {
                "kind": "charge",
                "id": str(entry.id),
                "booking_id": str(entry.booking_id),
                "amount": -entry.amount,
                "reason": entry.description,
                "reverses_id": str(entry.reverses_entry_id) if entry.reverses_entry_id else "",
                "created_at": entry.created_at.isoformat() if entry.created_at else "",
            }
        )
    payment_total = Decimal(0)
    for payment in _payments_in_range(db, start, end):
        if not payment.is_reversal:
            continue
        payment_total += payment.amount
        items.append(
            {
                "kind": "payment",
                "id": str(payment.id),
                "booking_id": str(payment.booking_id),
                "amount": payment.amount,
                "reason": payment.reference_note,
                "reverses_id": str(payment.reverses_payment_id)
                if payment.reverses_payment_id
                else "",
                "created_at": payment.received_at.isoformat() if payment.received_at else "",
            }
        )
    items.sort(key=lambda item: item["created_at"], reverse=True)
    total = len(items)
    offset = (page - 1) * page_size
    refs: dict[uuid.UUID, str] = {}
    for booking_id in {uuid.UUID(item["booking_id"]) for item in items}:
        booking = db.get(Booking, booking_id)
        refs[booking_id] = booking.booking_ref if booking else ""
    for item in items:
        item["booking_ref"] = refs[uuid.UUID(item["booking_id"])]
    return {
        "from_date": from_date,
        "to_date": to_date,
        "payment_reversal_total": payment_total.quantize(CENT),
        "charge_reversal_total": charge_total.quantize(CENT),
        "items": items[offset : offset + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def bookings_summary(db: DBSession, from_date: date | None, to_date: date | None) -> dict[str, Any]:
    """Booking counts by status for stays overlapping the period."""
    start, end = _bounds(from_date, to_date)
    low = from_date
    high = to_date + timedelta(days=1) if to_date is not None else None
    counts: dict[str, int] = defaultdict(int)
    total = 0
    for booking in db.scalars(select(Booking)).all():
        if low is not None and booking.check_out_date <= low:
            continue
        if high is not None and booking.check_in_date >= high:
            continue
        counts[booking.status] += 1
        total += 1
    return {
        "from_date": from_date,
        "to_date": to_date,
        "total": total,
        "confirmed": counts["CONFIRMED"],
        "checked_in": counts["CHECKED_IN"],
        "checked_out": counts["CHECKED_OUT"],
        "cancelled": counts["CANCELLED"],
    }


def occupancy(db: DBSession, from_date: date | None, to_date: date | None) -> dict[str, Any]:
    """Occupied vs available room-nights for the period.

    Occupied = stay segments of non-cancelled bookings intersecting
    [from, to+1); capacity = active + AVAILABLE rooms × days in the
    period. Historical per-room maintenance is not recorded, so capacity
    assumes every active room was available for the whole period
    (documented assumption, not invented history).
    """
    start, end = _bounds(from_date, to_date)
    occupied = 0
    for booking in db.scalars(select(Booking)).all():
        if booking.status == "CANCELLED":
            continue
        seg_from = booking.check_in_date
        seg_to = booking.check_out_date
        start_date = from_date
        end_date = to_date + timedelta(days=1) if to_date is not None else None
        if start_date is not None and seg_from < start_date:
            seg_from = start_date
        if end_date is not None and seg_to > end_date:
            seg_to = end_date
        if seg_to > seg_from:
            occupied += (seg_to - seg_from).days
    room_count = db.scalar(
        select(func.count())
        .select_from(Room)
        .where(Room.is_active.is_(True), Room.operational_status == RoomOperationalStatus.AVAILABLE)
    )
    days = ((to_date - from_date).days + 1) if (from_date and to_date) else 0
    capacity = (room_count or 0) * days if days else 0
    rate = (
        (Decimal(occupied) * Decimal(100) / Decimal(capacity)).quantize(CENT)
        if capacity
        else Decimal(0)
    )
    return {
        "from_date": from_date,
        "to_date": to_date,
        "occupied_room_nights": occupied,
        "available_room_nights": capacity,
        "occupancy_rate": rate,
    }
