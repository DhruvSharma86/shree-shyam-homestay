# Booking Workflow — Shree Shyam Home Stay

Bookings originate from **telephone calls or walk-ins only**. No online booking exists anywhere in the system.

## 1. Lifecycle state machine

**Phase 3.2 implemented scope:** `CONFIRMED → CANCELLED` only. The full state machine below is the approved direction; check-in/out, folio, token and no-show transitions arrive in Phases 4–5 and are not implemented yet.

```
                 ┌──────────┐
                 │ CONFIRMED│  (booking created, room reserved)
                 └────┬─────┘
        check-in      │          cancel
              ┌───────▼───────┐        ┌────────────┐
              │  CHECKED_IN   │───────▶│ CANCELLED  │  ← Phase 3.2: only this transition exists
              └───────┬───────┘        └────────────┘
         checkout     │                   (terminal, no reopen; new booking instead)
              ┌───────▼───────┐
              │ CHECKED_OUT   │  (final settlement done; guest token expires +24h)  ← Phase 4
              └───────────────┘

CONFIRMED ──(check-in date passes, no check-in recorded)──▶ NO_SHOW (manual flag by staff)  ← Phase 4
```

| Transition | Who | Preconditions |
|---|---|---|
| → `CONFIRMED` | RECEPTIONIST / ADMIN | Guest exists **and is active**; room available for full date range; rate snapshot taken |
| `CONFIRMED` → `CANCELLED` | RECEPTIONIST / ADMIN | Cancellation policy applied (fees **TBD** — no fee rules invented); room released immediately |
| `CONFIRMED` → `CHECKED_IN` | RECEPTIONIST / ADMIN | **Phase 4 (deferred)** — Today ≥ check-in date; 1-night payment recorded |
| `CHECKED_IN` → `CHECKED_OUT` | RECEPTIONIST / ADMIN | **Phase 4 (deferred)** — balance settled; receipt generated |
| `CONFIRMED` → `NO_SHOW` | RECEPTIONIST / ADMIN | **Phase 4 (deferred)** — manual flag after check-in date passes without arrival |

`CHECKED_OUT`, `CANCELLED`, `NO_SHOW` are terminal — bookings cannot be reopened (a new booking is created instead). Repeated cancels in Phase 3.2 are idempotent (return `200` with status `CANCELLED`, no new audit row). PATCH on a cancelled booking → `422`.

## 2. Creation flow (phone / walk-in)

**Phase 3.2 (implemented):**
```
1. Search guest by phone → found: reuse | not found: register guest (Phase 3.1 API)
2. Reject deactivated guests (422) — reactivate via guest API first
3. Check room availability for [check_in, check_out)   ← GET /bookings/availability
4. Allocate specific room (must be active + AVAILABLE)
5. Snapshot nightly rate (single rate covering the whole stay; mid-stay change → 422)
6. Snapshot tax settings covering check-in (NONE default)
7. Create booking: CONFIRMED, nights + Decimal subtotal/total
```

**Deferred to Phases 4–5:** folio ROOM_CHARGE entry, guest token, advance payments, WhatsApp. Phase 3.2 performs steps 1–7 only (no folio/token/payment). Steps run in one DB transaction; any failure rolls everything back (no orphan rows).

## 3. Overlap prevention
- Availability check: no other booking in status `CONFIRMED` for the same room overlapping `[check_in, check_out)`.
- Overlap test: `existing.check_in < new.check_out AND existing.check_out > new.check_in`.
- Enforced in a transaction with `SELECT … FOR UPDATE` on the room row; PostgreSQL exclusion constraint as backstop (see `docs/DATABASE_DESIGN.md` §2.10) — **implemented in Phase 3.2** (migration `e5f6a7b8c9d0`).
- Double-booking is a **critical defect** — dedicated concurrency tests required (SQLite service test + PostgreSQL threaded test in CI).

## 4. Room allocation rules
- Receptionist allocates a **specific room**; system shows only available rooms for the dates.
- Out-of-service rooms are never offered.
- Room type changes after booking require ADMIN (prerequisite: no overlapping conflict) — TBD whether receptionists may reallocate within same type.

## 5. Date rules
- `check_out_date > check_in_date` enforced (DB + API). Past check-ins rejected (422).
- Nights = `check_out_date − check_in_date`.
- Early check-in / late checkout: allowed operationally; extra-night charges added as folio entries if policy requires (TBD, Phase 4).
- Dates are hotel-local (timezone stored in `hotel_info`; TBD — default IST).

## 6. Cancellation & no-show
- Cancellation policy (fees, advance forfeiture) is **TBD** — the system records the cancellation and can apply a cancellation charge entry, but no policy is invented here.
- Cancelled/no-show bookings release the room immediately for the remaining dates.

## 7. Booking history & search
- Phase 3.2: `GET /bookings?status=&guest_id=&room_id=&check_in_from=&check_in_to=` + pagination (newest first). Guest/room histories are these two filters.
- Search by guest name/phone/ref is deferred (would need a join + PII handling; name/phone search exists on guests).
- Guest history: all bookings for the primary guest, newest first.
- Room history: all bookings for the room (for audit/occupancy).

## 8. Edge cases
| Case | Handling |
|---|---|
| Walk-in for tonight | Same as creation flow; check-in immediately after creation |
| Checked-in guest extends stay | Extend `check_out_date` (overlap-check again); add room-charge folio entry for extra nights |
| Guest changes room mid-stay | Checkout-style folio split is complex — **out of scope v1**; treat as checkout + new booking (TBD) |
| Duplicate guest registration | Phone-normalised lookup; merge flow TBD (no hard delete) |
| Payment taken but booking cancelled | Refund recorded as reversal payment entry; reported in financials |

## 9. Worked example
> Phone booking: guest G, Deluxe room R2, 3 nights (Fri–Mon), rate ₹X/night → folio `ROOM_CHARGE 3 × X`. Advance ₹500 recorded. Token link sent via WhatsApp. Check-in: 1-night payment recorded. Checkout day: final payment for balance → receipt PDF → checkout WhatsApp → token expires +24h. *(₹X is illustrative only; real rates are configured by ADMIN.)*
