# Booking Workflow — Shree Shyam Home Stay

Bookings originate from **telephone calls or walk-ins only**. No online booking exists anywhere in the system.

## 1. Lifecycle state machine

```
                 ┌──────────┐
                 │ CONFIRMED│  (booking created, room reserved)
                 └────┬─────┘
        check-in      │          cancel
              ┌───────▼───────┐        ┌────────────┐
              │  CHECKED_IN   │───────▶│ CANCELLED  │
              └───────┬───────┘        └────────────┘
         checkout     │
              ┌───────▼───────┐
              │ CHECKED_OUT   │  (final settlement done; guest token expires +24h)
              └───────────────┘

CONFIRMED ──(check-in date passes, no check-in recorded)──▶ NO_SHOW (manual flag by staff)
```

| Transition | Who | Preconditions |
|---|---|---|
| → `CONFIRMED` | RECEPTIONIST / ADMIN | Guest exists; room available for full date range; rate snapshot taken |
| `CONFIRMED` → `CHECKED_IN` | RECEPTIONIST / ADMIN | Today ≥ check-in date (early check-in allowed with note — TBD policy); 1-night payment recorded |
| `CHECKED_IN` → `CHECKED_OUT` | RECEPTIONIST / ADMIN | Outstanding balance settled (payment or approved write-off — TBD); receipt generated |
| `CONFIRMED` → `CANCELLED` | RECEPTIONIST / ADMIN | Cancellation policy applied (TBD — no fee rules invented) |
| `CONFIRMED` → `NO_SHOW` | RECEPTIONIST / ADMIN | Manual flag after check-in date passes without arrival |

`CHECKED_OUT`, `CANCELLED`, `NO_SHOW` are terminal — bookings cannot be reopened (a new booking is created instead).

## 2. Creation flow (phone / walk-in)

```
1. Search guest by phone → found: reuse | not found: register guest
2. Check room availability for [check_in, check_out)
3. Allocate specific room (or type → system suggests available rooms)
4. Snapshot nightly rate (room_rates current row) into booking.rate_snapshot
5. Create folio: ROOM_CHARGE entry for nights × rate (full stay; balance due at checkout)
6. Generate guest token (crypto-secure), store hash, build portal link
7. Record advance payment if taken (→ payments, stage=ADVANCE)
8. Send welcome WhatsApp with personalised guest link (mock in dev)
9. Booking status = CONFIRMED
```

Steps 4–7 run in **one DB transaction**. Any failure rolls everything back (no orphan folios/tokens).

## 3. Overlap prevention
- Availability check: no other booking in status `CONFIRMED`/`CHECKED_IN` for the same room overlapping `[check_in, check_out)`.
- Overlap test: `existing.check_in < new.check_out AND existing.check_out > new.check_in`.
- Enforced in a transaction with `SELECT ... FOR UPDATE` on the room row; PostgreSQL exclusion constraint as backstop (see `docs/DATABASE_DESIGN.md` §2.10).
- Double-booking is a **critical defect** — dedicated concurrency tests required.

## 4. Room allocation rules
- Receptionist allocates a **specific room**; system shows only available rooms for the dates.
- Out-of-service rooms are never offered.
- Room type changes after booking require ADMIN (prerequisite: no overlapping conflict) — TBD whether receptionists may reallocate within same type.

## 5. Date rules
- `check_out_date > check_in_date` enforced (DB + API).
- Nights = `check_out_date − check_in_date`.
- Early check-in / late checkout: allowed operationally; extra-night charges added as folio entries if policy requires (TBD).
- Dates are hotel-local (timezone stored in `hotel_info`; TBD — default IST).

## 6. Cancellation & no-show
- Cancellation policy (fees, advance forfeiture) is **TBD** — the system records the cancellation and can apply a cancellation charge entry, but no policy is invented here.
- Cancelled/no-show bookings release the room immediately for the remaining dates.

## 7. Booking history & search
- Search by: guest name, phone, booking ref, room, date range, status.
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
