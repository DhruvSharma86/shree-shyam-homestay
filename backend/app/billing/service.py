"""Billing/folio business logic — append-only ledger, balances, reversals.

Folio = the set of ``folio_entries`` rows for one booking (no header row).
Balance = ``SUM(entries.amount) - SUM(payments.amount)`` with
``Decimal`` (never float). Entries are immutable: corrections are new
``REVERSAL`` rows referencing the original; no update/delete path exists.

Initial room charge: exactly one ``ROOM_CHARGE`` row is created from the
booking snapshot (``room_subtotal``) during booking creation, inside the
same transaction (``ensure_initial_charge``). A partial unique index
(``ux_folio_initial_room_charge`` on ``booking_id`` where ``is_initial``)
makes duplicates impossible even under races. ``GET /folio`` also calls
``ensure_initial_charge`` — that is the documented backfill-by-demand for
pre-4.1 bookings (it only creates the missing snapshot charge; it never
guesses or recalculates from mutable rates).

Discounts/reversals are blocked when they would drive the folio total
(``SUM(entries.amount)``) below zero (see ``NegativeBalanceError``).
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.auth.service import write_audit
from app.models.booking import Booking
from app.models.folio_entry import FolioEntry, FolioEntryType
from app.models.payment import Payment


class FolioClosedError(ValueError):
    """Raised when a ledger mutation targets a cancelled booking."""


class InvalidReversalError(ValueError):
    """Raised for a reversal that cannot legally reverse its target."""


class NegativeBalanceError(ValueError):
    """Raised when a discount/reversal would make the folio total negative."""


def _money(value: Decimal) -> Decimal:
    """Quantize a money amount to 2dp (project convention)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def folio_totals(db: DBSession, booking_id: uuid.UUID) -> tuple[Decimal, Decimal, Decimal]:
    """Return (total_charges, total_paid, balance_due) for a booking.

    ``total_charges = SUM(folio_entries.amount)``,
    ``total_paid = SUM(payments.amount)``, balance is the difference.
    Empty sums are Decimal zero, never None.
    """
    charges = db.scalar(
        select(func.coalesce(func.sum(FolioEntry.amount), Decimal(0))).where(
            FolioEntry.booking_id == booking_id
        )
    )
    paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), Decimal(0))).where(
            Payment.booking_id == booking_id
        )
    )
    total_charges = Decimal(charges) if charges is not None else Decimal(0)
    total_paid = Decimal(paid) if paid is not None else Decimal(0)
    return total_charges, total_paid, total_charges - total_paid


def ensure_initial_charge(
    db: DBSession, booking: Booking, *, actor_user_id: uuid.UUID | None
) -> FolioEntry | None:
    """Create the single initial ROOM_CHARGE from the booking snapshot.

    Idempotent: returns the existing initial entry when one is already
    present. Never touches cancelled bookings (no charge is fabricated
    for them). Runs in the caller's transaction.
    """
    if booking.status == "CANCELLED":
        return None
    existing = db.scalar(
        select(FolioEntry).where(
            FolioEntry.booking_id == booking.id, FolioEntry.is_initial.is_(True)
        )
    )
    if existing is not None:
        return existing
    entry = FolioEntry(
        booking_id=booking.id,
        entry_type=FolioEntryType.ROOM_CHARGE,
        description=(
            f"Room charge — {booking.nights} night(s) @ {_money(booking.night_rate_snapshot)}"
        ),
        quantity=Decimal(booking.nights),
        unit_amount=_money(booking.night_rate_snapshot),
        amount=_money(booking.room_subtotal),
        is_initial=True,
        created_by=actor_user_id,
    )
    db.add(entry)
    try:
        # Savepoint so a racing insert cannot poison the outer transaction:
        # the unique index rejects the loser, which then reads the winner.
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        db.rollback()  # outer transaction still usable after savepoint rollback
        return db.scalar(
            select(FolioEntry).where(
                FolioEntry.booking_id == booking.id, FolioEntry.is_initial.is_(True)
            )
        )
    write_audit(
        db,
        action="FOLIO_INITIALIZED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={
            "entry_id": str(entry.id),
            "booking_id": str(booking.id),
            "amount": str(entry.amount),
        },
    )
    return entry


def adjust_initial_charge_for_resnapshot(
    db: DBSession, booking: Booking, *, actor_user_id: uuid.UUID | None
) -> None:
    """Keep the folio consistent when booking totals get re-snapshotted.

    Called after ``update_booking`` change nights/subtotal. The original
    initial row stays untouched (immutability); a REVERSAL offsets it
    and a new ROOM_CHARGE (``is_initial=False``) carries the new subtotal.
    If no initial entry exists yet (legacy pre-4.1 booking), only the
    initial entry is created.
    """
    initial = db.scalar(
        select(FolioEntry).where(
            FolioEntry.booking_id == booking.id, FolioEntry.is_initial.is_(True)
        )
    )
    if initial is None:
        ensure_initial_charge(db, booking, actor_user_id=actor_user_id)
        return
    new_amount = _money(booking.room_subtotal)
    if _money(initial.amount) == new_amount:
        return
    db.add(
        FolioEntry(
            booking_id=booking.id,
            entry_type=FolioEntryType.REVERSAL,
            description="Room charge superseded by stay-date update",
            quantity=Decimal(1),
            amount=_money(-initial.amount),
            reverses_entry_id=initial.id,
            created_by=actor_user_id,
        )
    )
    db.add(
        FolioEntry(
            booking_id=booking.id,
            entry_type=FolioEntryType.ROOM_CHARGE,
            description=(
                f"Revised room charge — {booking.nights} night(s) "
                f"@ {_money(booking.night_rate_snapshot)}"
            ),
            quantity=Decimal(booking.nights),
            unit_amount=_money(booking.night_rate_snapshot),
            amount=new_amount,
            is_initial=False,
            created_by=actor_user_id,
        )
    )
    write_audit(
        db,
        action="FOLIO_CHARGE_ADJUSTED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={
            "booking_id": str(booking.id),
            "amount": str(new_amount),
        },
    )


def _require_open_folio(booking: Booking) -> None:
    """Ledger mutations are forbidden once the booking is cancelled."""
    if booking.status == "CANCELLED":
        raise FolioClosedError("Booking is cancelled; its folio is read-only history.")


def _charges_after(db: DBSession, booking_id: uuid.UUID, extra_amount: Decimal) -> Decimal:
    """Folio entry total if one more signed entry of ``extra_amount`` lands."""
    current, _, _ = folio_totals(db, booking_id)
    return current + extra_amount


def add_charge(
    db: DBSession,
    booking: Booking,
    *,
    description: str,
    quantity: Decimal,
    unit_amount: Decimal,
    actor_user_id: uuid.UUID,
) -> FolioEntry:
    """Append an ADDITIONAL_CHARGE (amount computed server-side)."""
    _require_open_folio(booking)
    qty = quantity if isinstance(quantity, Decimal) else Decimal(str(quantity))
    rate = unit_amount if isinstance(unit_amount, Decimal) else Decimal(str(unit_amount))
    if qty <= 0:
        raise ValueError("quantity must be greater than zero.")
    amount = _money(qty * rate)
    if amount <= 0:
        raise ValueError("charge amount must be greater than zero.")
    entry = FolioEntry(
        booking_id=booking.id,
        entry_type=FolioEntryType.ADDITIONAL_CHARGE,
        description=description,
        quantity=_money(qty),
        unit_amount=_money(rate),
        amount=amount,
        created_by=actor_user_id,
    )
    db.add(entry)
    db.flush()
    write_audit(
        db,
        action="CHARGE_ADDED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={
            "entry_id": str(entry.id),
            "booking_id": str(booking.id),
            "amount": str(entry.amount),
            "reason": description,
        },
    )
    return entry


def add_discount(
    db: DBSession,
    booking: Booking,
    *,
    amount: Decimal,
    reason: str,
    actor_user_id: uuid.UUID,
) -> FolioEntry:
    """Append a DISCOUNT (ADMIN-only). Never drives the folio negative."""
    _require_open_folio(booking)
    value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    value = _money(value)
    if value <= 0:
        raise ValueError("discount amount must be greater than zero.")
    if _charges_after(db, booking.id, -value) < 0:
        raise NegativeBalanceError("Discount would make the folio total negative.")
    entry = FolioEntry(
        booking_id=booking.id,
        entry_type=FolioEntryType.DISCOUNT,
        description=reason,
        quantity=Decimal(1),
        amount=-value,
        created_by=actor_user_id,
    )
    db.add(entry)
    db.flush()
    write_audit(
        db,
        action="DISCOUNT_APPLIED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={
            "entry_id": str(entry.id),
            "booking_id": str(booking.id),
            "amount": str(entry.amount),
            "reason": reason,
        },
    )
    return entry


def reverse_entry(
    db: DBSession,
    booking: Booking,
    original: FolioEntry,
    *,
    reason: str,
    actor_user_id: uuid.UUID,
) -> FolioEntry:
    """Reverse a folio entry. Original rows are never modified."""
    _require_open_folio(booking)
    if original.booking_id != booking.id:
        raise ValueError("Entry does not belong to this booking.")
    if original.entry_type == FolioEntryType.REVERSAL:
        raise InvalidReversalError("A reversal entry cannot itself be reversed.")
    already = db.scalar(
        select(FolioEntry).where(
            FolioEntry.reverses_entry_id == original.id,
            FolioEntry.entry_type == FolioEntryType.REVERSAL,
        )
    )
    if already is not None:
        raise InvalidReversalError("Entry has already been reversed.")
    delta = _money(-original.amount)
    if _charges_after(db, booking.id, delta) < 0:
        raise NegativeBalanceError("Reversal would make the folio total negative.")
    entry = FolioEntry(
        booking_id=booking.id,
        entry_type=FolioEntryType.REVERSAL,
        description=reason,
        quantity=Decimal(1),
        amount=delta,
        reverses_entry_id=original.id,
        created_by=actor_user_id,
    )
    db.add(entry)
    db.flush()
    write_audit(
        db,
        action="REVERSAL_CREATED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={
            "entry_id": str(entry.id),
            "booking_id": str(booking.id),
            "amount": str(entry.amount),
            "reason": reason,
        },
    )
    return entry
