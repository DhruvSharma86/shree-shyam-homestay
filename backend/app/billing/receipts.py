"""Final-receipt service — render ReportLab PDF and persist bytes.

The issued receipt is an immutable snapshot of the ledger at checkout:
PDF bytes are stored in ``receipts.pdf_content`` with a SHA-256 hash,
so later hotel/guest/rate changes cannot alter the issued document.
Money values come from the ledger (never recomputed from mutable data).
"""

import hashlib
import io
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.auth.service import write_audit
from app.billing.service import folio_totals
from app.models.booking import Booking
from app.models.folio_entry import FolioEntry
from app.models.guest import Guest
from app.models.hotel_info import HotelInfo
from app.models.payment import Payment
from app.models.receipt import Receipt, ReceiptKind
from app.models.room import Room
from app.models.room_type import RoomType


def _inr(amount: Decimal) -> str:
    """Format a Decimal as Indian numbering (INR, 2dp, ASCII-safe)."""
    sign = "-" if amount < 0 else ""
    value = abs(amount)
    integer, _, fraction = f"{value:.2f}".partition(".")
    groups: list[str] = []
    rest = integer
    while len(rest) > 3:
        groups.append(rest[-3:])
        rest = rest[:-3]
    groups.append(rest)
    groups.reverse()
    leading = groups[0]
    if len(groups) > 1:
        parts = [leading] + groups[1:]
        grouped = f"{parts[0]},{','.join(parts[1:])}"
    else:
        grouped = leading
    return f"{sign}INR {grouped}.{fraction}"


def build_receipt_context(db: DBSession, booking: Booking) -> dict:
    """Collect everything the receipt needs from the ledger (Decimal-typed)."""
    hotel = db.scalar(select(HotelInfo).where(HotelInfo.singleton_key == 1))
    guest = db.get(Guest, booking.guest_id)
    room = db.get(Room, booking.room_id)
    room_type = db.get(RoomType, booking.room_type_id)
    entries = db.scalars(
        select(FolioEntry)
        .where(FolioEntry.booking_id == booking.id)
        .order_by(FolioEntry.created_at.asc())
    ).all()
    payments = db.scalars(
        select(Payment).where(Payment.booking_id == booking.id).order_by(Payment.created_at.asc())
    ).all()
    total_charges, total_paid, balance_due = folio_totals(db, booking.id)
    return {
        "hotel": hotel,
        "guest_name": guest.full_name if guest else "",
        "room_number": room.room_number if room else "",
        "room_type_name": room_type.name if room_type else "",
        "entries": entries,
        "payments": payments,
        "total_charges": total_charges,
        "total_paid": total_paid,
        "balance_due": balance_due,
    }


def render_receipt_pdf(
    booking: Booking, receipt_ref: str, context: dict, checked_out_at: datetime
) -> bytes:
    """Render the final receipt PDF (in-memory) from the ledger snapshot.

    Amounts are ``Decimal`` from the ledger; no prices/rates are looked
    up here. Only configured, present hotel fields are printed — nothing
    is invented.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    hotel: HotelInfo | None = context["hotel"]
    doc_buf = io.BytesIO()
    doc = SimpleDocTemplate(doc_buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    story = []
    hotel_name = hotel.hotel_name if hotel else "Shree Shyam Home Stay"
    story.append(Paragraph(f"<b>{hotel_name}</b>", styles["Title"]))
    if hotel is not None:
        contact_bits = [
            part
            for part in (
                hotel.contact_number,
                hotel.email,
                hotel.address,
                hotel.city,
                hotel.pincode,
            )
            if part
        ]
        for bit in contact_bits:
            story.append(Paragraph(bit, styles["Normal"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"Final Receipt &mdash; {receipt_ref}", styles["Heading2"]))
    summary = [
        ["Booking ref", booking.booking_ref],
        ["Guest", context["guest_name"]],
        ["Room", f"{context['room_number']} ({context['room_type_name']})"],
        ["Check-in", booking.check_in_date.isoformat()],
        ["Check-out date", booking.check_out_date.isoformat()],
        ["Nights", str(booking.nights)],
        ["Checked out at", checked_out_at.isoformat()],
    ]
    for label, value in summary:
        story.append(Paragraph(f"<b>{label}:</b> {value}", styles["Normal"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>Charges</b>", styles["Heading3"]))
    charge_rows = [["Charge", "Qty", "Unit amount", "Amount"]]
    for entry in context["entries"]:
        unit = _inr(entry.unit_amount) if entry.unit_amount is not None else ""
        charge_rows.append([entry.entry_type, str(entry.quantity), unit, _inr(entry.amount)])
    table = Table(charge_rows, repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    story.append(table)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("<b>Payments</b>", styles["Heading3"]))
    payment_rows = [["Date", "Mode", "Stage", "Reference", "Amount"]]
    for payment in context["payments"]:
        if payment.is_reversal:
            continue
        payment_rows.append(
            [
                payment.received_at.isoformat() if payment.received_at else "",
                payment.mode,
                payment.payment_stage,
                payment.reference_note or "",
                _inr(payment.amount),
            ]
        )
    payments_table = Table(payment_rows, repeatRows=1)
    payments_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    story.append(payments_table)
    reversal_rows = [["Date", "Mode", "Stage", "Amount"]]
    for payment in context["payments"]:
        if not payment.is_reversal:
            continue
        reversal_rows.append(
            [
                payment.received_at.isoformat() if payment.received_at else "",
                payment.mode,
                payment.payment_stage,
                f"({_inr(payment.amount)})",
            ]
        )
    if len(reversal_rows) > 1:
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph("<b>Payment reversals (credits, not new money)</b>", styles["Heading3"])
        )
        rev_table = Table(reversal_rows, repeatRows=1)
        rev_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
        story.append(rev_table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>Totals</b>", styles["Heading3"]))
    if booking.tax_type_snapshot == "NONE":
        story.append(
            Paragraph(
                "TAX: does not apply under the approved configuration (default NONE). "
                "No tax amount has been calculated or charged in this receipt.",
                styles["Normal"],
            )
        )
    else:
        rate = booking.tax_rate_snapshot
        story.append(
            Paragraph(
                f"TAX: a tax configuration exists ({booking.tax_type_snapshot} at {rate}% "
                f"per night, {booking.tax_pricing_mode_snapshot}); its calculation is not "
                "implemented yet, so no tax amount or liability has been determined or charged "
                "in this receipt.",
                styles["Normal"],
            )
        )
    totals = [
        ["Total charges", _inr(context["total_charges"])],
        ["Net payments", _inr(context["total_paid"])],
        ["Outstanding balance", _inr(context["balance_due"])],
    ]
    totals_table = Table(totals)
    totals_table.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    story.append(totals_table)
    story.append(Spacer(1, 6 * mm))
    story.append(
        Paragraph(
            "This receipt is generated from the final ledger snapshot at checkout "
            "and does not change with later configuration edits.",
            styles["Normal"],
        )
    )
    doc.build(story)
    return doc_buf.getvalue()


def create_final_receipt(
    db: DBSession,
    booking: Booking,
    *,
    actor_user_id: uuid.UUID,
    checked_out_at: datetime,
) -> Receipt:
    """Render and persist the immutable FINAL receipt (caller's transaction)."""
    existing = db.scalar(
        select(Receipt).where(Receipt.booking_id == booking.id, Receipt.kind == ReceiptKind.FINAL)
    )
    if existing is not None:
        return existing
    context = build_receipt_context(db, booking)
    receipt_ref = f"RCPT-{uuid.uuid4().hex[:8].upper()}"
    pdf_bytes = render_receipt_pdf(booking, receipt_ref, context, checked_out_at)
    receipt = Receipt(
        booking_id=booking.id,
        receipt_ref=receipt_ref,
        kind=ReceiptKind.FINAL,
        content_hash=hashlib.sha256(pdf_bytes).hexdigest(),
        pdf_content=pdf_bytes,
        generated_by=actor_user_id,
    )
    db.add(receipt)
    db.flush()
    write_audit(
        db,
        action="RECEIPT_ISSUED",
        resource_type="booking",
        resource_id=str(booking.id),
        actor_user_id=actor_user_id,
        metadata={
            "receipt_id": str(receipt.id),
            "booking_id": str(booking.id),
            "receipt_ref": receipt_ref,
            "content_hash": receipt.content_hash,
        },
    )
    return receipt


def get_final_receipt(db: DBSession, booking_id: uuid.UUID) -> Receipt | None:
    """Return the FINAL receipt for a booking, if one has been issued."""
    return db.scalar(
        select(Receipt).where(Receipt.booking_id == booking_id, Receipt.kind == ReceiptKind.FINAL)
    )
