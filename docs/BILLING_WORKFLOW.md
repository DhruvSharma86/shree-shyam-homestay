# Billing Workflow — Shree Shyam Home Stay

**Phase 4.2 status (implemented 2026-11-09, backend only):** payment recording is live — `POST /payments` (CASH/UPI/CARD_POS, ADVANCE/CHECK_IN/CHECKOUT/OTHER, optional reference, D9 overpayment gate, booking-row lock), ADMIN-only payment reversals (`POST /payments/{id}/reverse`), one-night check-in enforcement wired via `stage_paid()`. Settlement, PDFs, messages and reports remain deferred (Phase 4.3–4.4). `GET /folio` is now strictly read-only; legacy initial charges backfill through explicit `POST /folio/initialize`.

One **folio per booking**. All money movement is append-only; corrections use reversal entries. **No silent deletes or overwrites.**

## 1. Folio model

```
Folio (per booking)
├── ROOM_CHARGE        nights × rate_snapshot          (+)
├── ADDITIONAL_CHARGE  restaurant / cab / services     (+)
├── DISCOUNT           approved reductions            (−)
├── TAX                per tax_settings               (+/±)
└── REVERSAL           corrections of any line above   (−/+)
Payments (separate, linked to booking)
├── ADVANCE / CHECK_IN / CHECKOUT — CASH | UPI | CARD_POS
└── Reversal payments (refunds/voids)

Balance due = Σ(folio_entries.amount) − Σ(payments.amount)
```

## 2. Charging flow
1. At booking creation: `ROOM_CHARGE` = nights × snapshotted rate. **Full stay** is charged to the folio up-front (balance due at checkout). — ✅ Implemented in Phase 4.1 (atomic initial entry, partial unique index; explicit backfill via `POST /folio/initialize` since Phase 4.2 — reads never write).
2. During stay: additional charges added by receptionist (restaurant, cab, extra services) with description + amount. Each addition is a folio entry — never edits an existing one. — ✅ Phase 4.1.
3. Nights extension: new `ROOM_CHARGE` entry for extra nights (never modify the original). — Stay-date updates that re-snapshot keep the folio consistent via REVERSAL + revised ROOM_CHARGE (Phase 4.1); additional rows with `is_initial=false` are reserved for later extension flows.
4. Tax: computed at checkout from configured `tax_settings` (or at booking if policy TBD decides otherwise). If GST not applicable → `TAX` entries omitted entirely. — Deferred (D5: NONE default, no tax rows created).

## 3. Payment flow
| Stage | When | Notes |
|---|---|---|
| `ADVANCE` | At booking (phone bookings) | **Deferred — Phase 4.2** |
| `CHECK_IN` | At check-in | **Implemented — Phase 4.2 (D2: mandatory one-night CHECK_IN payment at check-in)** |
| `CHECKOUT` | At checkout | **Deferred — Phase 4.3** |
| `OTHER` | Ad-hoc | **Deferred — Phase 4.2** |

- Modes: `CASH`, `UPI`, `CARD_POS` only (D1, approved). No online payments anywhere.
- Every payment records: amount, mode, stage, receiver (user), timestamp, optional reference. — ✅ Phase 4.2 (stage/mode validated server-side; `received_by` + `received_at` set by the service).
- Partial payments allowed; balance updates immediately.
- **Overpayment:** blocked by default in future payment services (D9); ADMIN may authorize an exception with reason — **Phase 4.2**.

## 4. Discounts
- Discounts are **ADMIN-only** (D4, Phase 4.1) — RECEPTIONIST denied (403).
- Every discount requires a **reason** (free text, mandatory) and is stored as a signed folio entry + audit log entry.
- Discounts can never make the folio negative (system blocks entries that would drive the folio total below zero).
- **Phase 4.2:** refund-linked reversals and ADMIN write-offs (policy TBD).

## 5. Checkout settlement
```
1. Lock booking (status must be CHECKED_IN)
2. Compute: total charges = Σ folio entries; total paid = Σ payments
3. Outstanding = total charges − total paid
4. If outstanding > 0 → record final payment(s) until balance = 0
   (or ADMIN-approved write-off entry — TBD policy)
5. Generate final PDF receipt (ReportLab)
6. Status → CHECKED_OUT; checkout_at = now; guest token expiry = checkout_at + 24h
7. Send checkout WhatsApp + receipt (mock in dev)
8. Steps 2–6 in ONE transaction; message sending after commit
```

## 6. Corrections & reversals (no silent edits)
- **Wrong charge added** → add `REVERSAL` folio entry referencing the original (`reverses_entry_id`), amount = −original. — ✅ Phase 4.1. Already-reversed targets and reversal-of-reversal are rejected (422); the original remains visible on the folio.
- **Wrong payment recorded** → add reversal payment entry (refund/void), linked to original. — **Phase 4.2 (ADMIN-only per D3).**
- Original entries remain visible on the folio (struck through / marked reversed in UI + PDF).
- Reversals require ADMIN if the original payment was already reported in a closed financial period (TBD period-close concept).

## 7. GST / tax behaviour (no assumptions)
- `tax_settings` controls everything: registration flag, GST number, mode (`NONE`/`EXCLUSIVE`/`INCLUSIVE`), rate.
- **The system ships with `tax_mode = NONE` and no rates.** Nothing is invented.
- If EXCLUSIVE: tax added on top of charges. If INCLUSIVE: tax extracted and shown as a memo line (charges unchanged).
- Receipt shows tax breakdown **only if configured**; otherwise receipts omit tax lines entirely.
- Rate history is versioned; changing rates never alters past folios.

## 8. Receipts (PDF)
Generated with ReportLab; contents: hotel info (from DB), booking ref, guest name (primary only), room, dates, folio lines (with reversals marked), tax lines (if configured), payments, balance (0.00 at final), generated timestamp, staff user.
- `PAYMENT` receipt: issued per payment (optional — TBD).
- `FINAL` receipt: issued at checkout; available to guest via portal link and retained by hotel.

## 9. Financial reporting (ADMIN only)
- Daily/monthly revenue, payments by mode, outstanding balances, discount totals, cancellations.
- Reports read from append-only tables — numbers are reproducible and auditable.
- Exports (CSV/PDF) — TBD.

## 10. Worked example (illustrative amounts only)
> 3-night stay, rate snapshot ₹2,000/night (example). Folio: ROOM_CHARGE 3×2,000 = 6,000. Restaurant 450. Discount −200 (reason: "returning guest"). Total = 6,250. Advance 500, check-in 2,000, checkout 3,750 → balance 0. Receipt generated; token expires +24h. *(All figures are placeholders — real rates configured by ADMIN.)*
