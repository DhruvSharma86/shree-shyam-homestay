# API Design — Shree Shyam Home Stay

REST over HTTPS. JSON. Cookie-based session auth for staff; token-in-URL for guests. Versioned from day one.

## 1. Conventions
- Base path: `/api/v1` (breaking changes → `/api/v2`; additive changes stay in v1).
- Resource naming: plural nouns, kebab-case URLs, snake_case JSON fields.
- Success: resource object or `{ "data": ..., "meta": {...} }` for lists; pagination via `?page=&page_size=` (default 20, max 100) with `total` in meta.
- Errors: standard envelope, never stack traces:
```json
{ "error": { "code": "BOOKING_OVERLAP", "message": "Room already booked for these dates.", "details": { } } }
```
- HTTP codes: `200` ok, `201` created, `204` no content, `400` validation, `401` unauthenticated, `403` forbidden (RBAC), `404` not found / **generic for guest-portal misses**, `409` conflict (overlap, invalid state transition), `422` business-rule violation, `429` rate limited, `500` internal.
- All timestamps ISO-8601 UTC; dates as `YYYY-MM-DD`; money as string/number with 2 decimals (never float math client-side — server computes balances).
- CSRF: required on all cookie-authenticated mutating requests (double-submit token).
- Health: `GET /healthz` (liveness), `GET /readyz` (DB reachable).

## 2. Authentication — ✅ implemented (Phase 1.2)
| Endpoint | Method | Notes |
|---|---|---|
| `/api/v1/auth/login` | POST | `{username, password}` → session + CSRF cookies; rate-limited (10 fails/5 min/username → 429); rotates pre-login session; generic `INVALID_CREDENTIALS` 401 |
| `/api/v1/auth/logout` | POST | revokes server session + clears cookies; CSRF required (idempotent) |
| `/api/v1/auth/me` | GET | current user `{user, permissions}`; 401 when unauthenticated |
| `/api/v1/auth/change-password` | POST | `{current_password, new_password≥10}`; revokes other sessions; CSRF required |
| `/api/v1/users` | GET / POST | list / create accounts (**`users.manage`, ADMIN only**); POST 201 |
| `/api/v1/users/{id}` | GET / PATCH / DELETE | fetch / update (name, email, active) / deactivate (**`users.manage`**; last-active-ADMIN guard → 409) |
| `/api/v1/users/{id}/reset-password` | POST | ADMIN-initiated reset (**`users.reset_credentials`**); revokes target sessions |

Session cookie: `HttpOnly; Secure (non-dev); SameSite=Lax; Path=/`. CSRF: double-submit (`sshs_csrf` cookie + `X-CSRF-Token` header) on all mutating endpoints. Error codes: `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `CSRF_FAILED` (403), `INVALID_CREDENTIALS` (401), `RATE_LIMITED` (429). No public registration endpoint exists.

## 3. Endpoint catalogue

### 3.1 Users (ADMIN: `users.manage`)
| Endpoint | Method | Permission |
|---|---|---|
| `/users` | GET list, POST create | `users.manage` |
| `/users/{id}` | GET, PATCH, DELETE (deactivate) | `users.manage` |
| `/users/{id}/reset-password` | POST | `users.reset_credentials` |
| `/users/{id}/sessions/revoke` | POST | `users.manage` |

### 3.2 Hotel, rooms, pricing, tax, content (ADMIN: respective `*.manage`)
| Endpoint | Method | Permission |
|---|---|---|
| `/admin/hotel` | GET, PATCH | `hotel.manage` |
| `/admin/room-types` | GET, POST | `rooms.manage` |
| `/admin/room-types/{id}` | GET, PATCH | `rooms.manage` (deactivation via `is_active=false`) |
| `/admin/rooms` | GET (paginated), POST | `rooms.manage` |
| `/admin/rooms/{id}` | GET, PATCH | `rooms.manage` (`operational_status` ∈ AVAILABLE/MAINTENANCE/INACTIVE) |
| `/admin/room-rates` | GET, POST | `pricing.manage` (append-only versions; overlaps → 409) |
| `/admin/room-rates/{id}` | GET | `pricing.manage` |
| `/admin/tax-settings` | GET, POST | `tax.manage` (append-only versions; default NONE = empty list) |
| `/admin/restaurant` | GET, PATCH | `content.manage` |
| `/admin/menu-categories` | GET, POST | `content.manage` |
| `/admin/menu-categories/{id}` | PATCH | `content.manage` |
| `/admin/menu-items` | GET (paginated, `?category_id=`), POST | `content.manage` |
| `/admin/menu-items/{id}` | PATCH | `content.manage` |
| `/admin/cab-providers` | GET, POST | `content.manage` |
| `/admin/cab-providers/{id}` | PATCH | `content.manage` |

Public/guest-portal read endpoints for the above are deferred (Phases 5–6). `wifi_password` is write-only in the PATCH body and never echoed in responses.

### 3.3 Guests (`guests.read` / `guests.write`) — ✅ implemented (Phase 3.1)
| Endpoint | Method | Notes |
|---|---|---|
| `/guests` | GET, POST | GET: `?q=` searches name/email/phone, `?page=&page_size=`, `?include_inactive=`; sorted `created_at` desc; POST: phone normalized to E.164 |
| `/guests/{id}` | GET, PATCH | PATCH covers `full_name, phone, email, address, notes` only; `is_active` rejected (422) |
| `/guests/{id}/deactivate` | POST | Soft-deactivation, idempotent; audit `GUEST_DEACTIVATED` |
| `/guests/{id}/bookings` | GET | Deferred — use `GET /bookings?guest_id=` (Phase 3.2) instead |

Duplicate rule: exact normalized phone + case-insensitive whitespace-collapsed name on an **active** guest → `409 CONFLICT` with `details.existing_guest_id` (no silent merge). Same phone + different name allowed. Deactivated records never block re-registration. Invalid phone → `422 VALIDATION_ERROR`. Mutations require CSRF and write audit rows (`GUEST_CREATED/UPDATED/DEACTIVATED`) without PII in metadata.

### 3.4 Bookings & availability (`bookings.*`) — ✅ implemented (Phase 3.2, backend only)
| Endpoint | Method | Notes |
|---|---|---|
| `/bookings/availability` | GET `?check_in=&check_out=` | list of `{room_id, available}` for all active AVAILABLE rooms |
| `/bookings/availability/{room_id}` | GET `?check_in=&check_out=` | single-room `{room_id, available, check_in_date, check_out_date}` |
| `/bookings` | GET (filters), POST create | GET filters: `status, guest_id, room_id, check_in_from, check_in_to` + pagination; POST creates CONFIRMED booking with rate/tax snapshot |
| `/bookings/{id}` | GET, PATCH (dates/room/notes/guests — overlap rechecked) | cancelled bookings: PATCH → 422 |
| `/bookings/{id}/cancel` | POST | idempotent, never deletes; `{reason}` optional |
| `/bookings/{id}/check-in` | POST | ✅ Phase 4.2: CONFIRMED → CHECKED_IN (mandatory one-night CHECK_IN payment, `bookings.checkin`) |
| `/bookings/{id}/check-out` | POST | ✅ Phase 4.3: CHECKED_IN → CHECKED_OUT (zero balance + FINAL receipt, `bookings.checkout`) |
| `/bookings/{id}/no-show` | POST | **Deferred** |
| `/bookings/{id}/guest-link` | GET / POST rotate | **Deferred** — guest portal in Phase 5 |

Create body: `{guest_id, room_id, source: PHONE|WALK_IN (default PHONE), check_in_date, check_out_date, number_of_guests (1–20, default 1), notes?}`. Success `201` returns the booking with `booking_ref`, `nights`, `night_rate_snapshot`, `room_subtotal`, `tax_*_snapshot`, `total_amount`. Overlap → `409 CONFLICT`; invalid dates/past dates/inactive guest/maintenance room/no covering rate/mid-stay rate change → `422 VALIDATION_ERROR`. Date convention: check-in inclusive, check-out exclusive. No folio, token, payment, or portal fields exist in this milestone.

### 3.5 Billing (`billing.*`) — ✅ implemented Phases 4.1–4.2 (payments + check-in in 4.2)
| Endpoint | Method | Notes |
|---|---|---|
| `/bookings/{id}/folio` | GET | `billing.receipts.read` (both roles, D6): entries + `total_charges/total_paid/balance_due`; **read-only since Phase 4.2** (no writes, no audit rows) |
| `/bookings/{id}/folio/initialize` | POST | `billing.charges.write`, CSRF: idempotent, auditable initial-charge backfill for pre-4.1 bookings (never for cancelled ones) |
| `/bookings/{id}/folio/charges` | POST | `billing.charges.write` (both roles), CSRF; amount computed server-side (`quantity × unit_amount`) |
| `/bookings/{id}/folio/discounts` | POST | `billing.discounts.write` (**ADMIN only**, D4), CSRF; `reason` mandatory; negative-folio rejected (422) |
| `/bookings/{id}/folio/reversals` | POST | `billing.charges.write` (both roles), CSRF; `reason` mandatory; already-reversed/reversal-of-reversal → 422 |
| `/bookings/{id}/payments` | POST | `billing.payments.write` (both roles), CSRF: `{amount>0, mode CASH|UPI|CARD_POS, payment_stage ADVANCE|CHECK_IN|CHECKOUT|OTHER, reference_note?, overpayment_reason?}`; overpay blocked unless ADMIN + reason (D9) |
| `/bookings/{id}/payments/{payment_id}/reverse` | POST | `billing.payments.write` **plus ADMIN role gate** (D3), CSRF; `{reason}` mandatory; dup/cross/self → 422 |
| `/bookings/{id}/payments` | GET (paginated) | `billing.receipts.read` (both roles) |
| `/bookings/{id}/receipts` | GET, POST (generate) | superseded by the dedicated endpoints below (see §5d) |
| `/bookings/{id}/receipt` | GET (metadata) | `billing.receipts.read` (both roles): `receipt_ref`, `kind`, `content_hash` |
| `/bookings/{id}/receipt/download` | GET (PDF) | `billing.receipts.read` (both roles, auth, `no-store` cache): stored FINAL bytes |

Financial writes and their audit rows commit in the same transaction; audit metadata carries entry/payment ids, amounts, modes, stages and reasons only (no guest PII). Balances are always derived with `Decimal` (total_paid is net of reversal records); no stored running total.

### 3.6 Reports (ADMIN only — `reports.financial.read`, read-only) — ✅ Phase 4.4
| Endpoint | Method | Notes |
|---|---|---|
| `/reports/financial/summary` | GET `?from_date=&to_date=` | ledger measures for the period (UTC) — see §5e |
| `/reports/financial/collections` | GET `?from_date=&to_date=` | daily × (method, stage) collections |
| `/reports/financial/collections/export.csv` | GET | same source, deterministic CSV |
| `/reports/financial/payment-methods` | GET `?from_date=&to_date=` | whole-period method breakdown |
| `/reports/financial/outstanding` | GET `?page=&page_size=` | **live snapshot** folios with non-zero balances |
| `/reports/financial/outstanding/export.csv` | GET | same source, deterministic CSV |
| `/reports/financial/reconciliation` | GET `?from_date=&to_date=` | period charges vs originals vs reversals vs net |
| `/reports/financial/reversals` | GET `?from_date=&to_date=&page=&page_size=` | linked charge + payment reversal rows |
| `/reports/bookings/summary` | GET `?from_date=&to_date=` | status counts for stays overlapping the period |
| `/reports/bookings/occupancy` | GET `?from_date=&to_date=` | occupied vs available room-nights |
| `/audit-log` | GET `?actor=&action=&from=&to=` | **Deferred** — audit rows exist, the viewer in Phase 6 |

### 3.7 Messaging (`billing`/`bookings` context; ADMIN config)
| Endpoint | Method | Notes |
|---|---|---|
| `/bookings/{id}/messages/welcome` | POST | sends link (mock in dev) |
| `/bookings/{id}/messages/checkout` | POST | sends checkout + receipt |
| `/messages` | GET | message_log list (ADMIN) |

### 3.8 Guest portal (no session — token in path, Phase 5.1)
| Endpoint | Method | Notes |
|---|---|---|
| `/guest-portal/{token}/overview` | GET | stay fields + hotel contact (no ids/money/PII) |
| `/guest-portal/{token}/menu` | GET | active categories + visible items |
| `/guest-portal/{token}/cab` | GET | active cab providers |
| `/guest-portal/{token}/wifi` | GET | SSID/password only when configured |
| `/guest-portal/{token}/tourism` | GET | active tour packages + local information |
| `/guest-portal/{token}/receipt` | GET | final receipt metadata (404 until issued) |
| `/guest-portal/{token}/receipt/download` | GET | stored FINAL PDF bytes for this booking only |
| `/bookings/{id}/guest-portal` | GET | staff status (ADMIN `portal.tokens.manage`) — never raw |
| `/bookings/{id}/guest-portal/revoke` | POST | staff revoke (ADMIN; see §5f) |
| `/bookings/{id}/guest-portal/rotate` | POST | staff re-issue raw-once (ADMIN; see §5f) |

### 3.9 Public website (unauthenticated, read-only)
| Endpoint | Method | Notes |
|---|---|---|
| `/public/{page}` | GET | home/about/rooms/gallery/facilities/restaurant/attractions/contact |
| `/public/rooms` | GET | room types + nightly rates (configurable; shown only if ADMIN enables — TBD) + "call for booking" info |

## 4. Validation rules (Pydantic v2)
- Dates: `check_out > check_in`; bookings in the past rejected; overlap on the same room rejected (`409`).
- Phone: normalised to E.164 on write; search tolerant of formatting.
- All IDs are UUIDs; booking refs look like `SSH-XXXXXXXX` (`booking_ref`, server-generated from UUID).
- Money: `night_rate_snapshot`, `room_subtotal`, `total_amount` are `NUMERIC(12,2)` computed with Python `Decimal` (`rate × nights`, quantised to 2dp); no float money math anywhere.

## 5. Idempotency & concurrency
- Booking create & payment record accept `Idempotency-Key` header (recommended) to prevent double-submits from retries. **Not yet implemented** — Phase 3.2 relies on room-row locks + PostgreSQL exclusion constraint instead.
- State transitions use explicit status checks: `CONFIRMED → CANCELLED` only; cancel is idempotent; PATCH on cancelled → `422 VALIDATION_ERROR` (Phase 3.2). CHECKED_IN/OUT and NO_SHOW are not defined in this milestone.

## 5a. Phase 3.2 booking behaviour (implemented)
- **Lifecycle:** `CONFIRMED` on create → `CANCELLED` via `POST /bookings/{id}/cancel`; no other transitions. Cancelled rows remain for audit/history and never block availability; cancel is idempotent.
- **Availability:** `[check_in, check_out)` — `existing.check_in < new.check_out AND existing.check_out > new.check_in`; same-day checkout/check-in is allowed. Inactive/MAINTENANCE rooms rejected. `GET /bookings/availability[/{room_id}]` reports `available: bool`.
- **Double-booking prevention:** service `SELECT … FOR UPDATE` on the room row + PostgreSQL exclusion constraint `excl_bookings_room_daterange` (gist, `room_id WITH =`, `daterange(check_in_date, check_out_date, '[)') WITH &&`, `WHERE status <> 'CANCELLED'`, requires `btree_gist`). Constraint is added by migration `e5f6a7b8c9d0`, not by `Base.metadata.create_all`. Integrity errors → `409 CONFLICT`. SQLite has no exclusion constraint; the service row lock is its guard (documented in the migration).
- **Rate snapshot (single-rate policy):** exactly one active `room_rates` version must cover the whole stay (`valid_from ≤ check_in`, `valid_until ≥ checkout − 1day`). A rate version starting inside the stay → `422` ("adjust rate validity, one rate must cover the entire stay") — never blended silently. No covering rate → `422` (no prices invented). Later rate changes never rewrite existing snapshots.
- **Tax snapshot:** `tax_settings` covering check-in is copied (`tax_type_snapshot`, `tax_rate_snapshot`, `tax_pricing_mode_snapshot`); when none is configured → `NONE/null/EXCLUSIVE` with `total == room_subtotal`. Tax amounts are calculated in billing (Phase 4), not here.
- **Guest integration:** booking requires an **active** existing guest; deactivated/missing guest → `422` (guest must be reactivated via guest API first — no silent rebooking, no auto-creation). Responses contain `guest_id` only (no name/phone/email).
- **Permissions & CSRF:** GETs need `bookings.read`, create/update need `bookings.write`, cancel needs `bookings.cancel`; all mutations require CSRF. Audit: `BOOKING_CREATED/UPDATED/CANCELLED` with `metadata.fields` only (no PII).

## 5b. Phase 4.1 billing behaviour (implemented)
- **Initial ROOM_CHARGE:** created exactly once per booking in the booking-creation transaction from `room_subtotal` (`quantity=nights`, `unit_amount=night_rate_snapshot`) — never recomputed from mutable rates, never merely derived at read time. Partial unique index `ux_folio_initial_room_charge` + savepoint-guarded insert. `GET /folio` backfills pre-4.1 bookings idempotently (documented in DATABASE_DESIGN §2.11); cancelled bookings never get a charge.
- **Ledger math:** `folio_totals()` = `(Σ entries.amount, Σ payments.amount, difference)` with `Decimal` (`ROUND_HALF_UP`, 2dp, zero-safe); no stored running total.
- **Charges:** `ADDITIONAL_CHARGE = quantity × unit_amount` computed server-side; `≤ 0` or empty description → `422`.
- **Discounts:** ADMIN-only (`billing.discounts.write`, D4); `reason` mandatory; blocked (422) when they would make `Σ entries < 0`.
- **Reversals:** `REVERSAL = −original.amount` with `reverses_entry_id` + reason; original untouched; repeated/reversal-of-reversal → `422`.
- **Phase 4.2/4.3 deferred:** payment writing, check-in/checkout, settlement, PDFs, overpayment rule enforcement (D9 applies there).

## 5c. Phase 4.2 payment & check-in behaviour (implemented)
- **Read-only folio GET:** `GET /folio` never writes (verified by ledger/audit count assertions). Backfill moved to explicit `POST /folio/initialize`.
- **Payments:** staff-recorded `CASH|UPI|CARD_POS` with `ADVANCE|CHECK_IN|CHECKOUT|OTHER` stages; validation of mode/stage in the router (Pydantic literals — unknown values → 422), amount > 0, optional `reference_note` (UPI UTR/POS ref). Balance is derived under a **booking-row `SELECT … FOR UPDATE` lock** inside the transaction, so two racing payments cannot both overpay (PG test asserts exactly one succeeds).
- **Overpayment (D9):** when `total_paid + new > total_charges`, RECEPTIONIST → 422 always; ADMIN without a non-empty `overpayment_reason` → 422; ADMIN with reason → allowed and `OVERPAYMENT_AUTHORIZED` is audited with the reason.
- **Reversal (D3):** ADMIN-only (role gate on `billing.payments.write`); original row untouched; new row (`is_reversal`, positive amount, `reverses_payment_id`, reason in `reference_note`); duplicate/cross-booking/self-reversal → 422; net paid total recalculates immediately.
- **Check-in:** `CONFIRMED → CHECKED_IN` under the same booking lock; cancelled/already-checked-in → 422; timestamp + actor stored (`checked_in_at`, `checked_in_by`); `GUEST_CHECKED_IN` audit (amounts only); requires **net CHECK_IN-stage payments ≥ `night_rate_snapshot`** (D2) — snapshot, not today's rate, never charges/discounts; wrong-stage amounts don't count. `CHECKED_OUT`/settlement remain Phase 4.3.

## 5d. Phase 4.3 checkout & receipt behaviour (implemented)
- **Checkout:** `POST /bookings/{id}/check-out` (`bookings.checkout`, both roles, CSRF) — `CHECKED_IN` only; cancelled → 422; CONFIRMED → 422; already `CHECKED_OUT` → 422 (duplicate). Transition + `checked_out_at/by` + audits + receipt persistence commit atomically under a booking-row `SELECT … FOR UPDATE` lock (concurrent checkouts: exactly one wins).
- **Settlement:** balance is re-derived from the ledger (authoritative `folio_totals()` — no recompute, no stored total). Positive balance → 422 listing the amount. Negative balance (credit) → 422 pending the refund/write-off workflow (not implemented).
- **Immutability after checkout:** every folio/payment mutation checks `CHECKED_OUT` via the folio-closed guard (→ 409) in the service layer; PATCH on a checked-out booking stays blocked with the pre-existing non-CONFIRMED rule (422).
- **Receipt:** FINAL receipt rendered in-memory by ReportLab (hotel fields only when configured; `INR` grouping, 2dp Decimals, Helvetica embedded font; tax configuration shown as a three-state note when the tax snapshot ≠ NONE (§7 — no liability calculated, D5), PDF bytes stored in PostgreSQL with `content_hash` (partial unique on FINAL per booking). Same bytes on every download; no filesystem paths, no traversal surface, `application/pdf`, `attachment; filename="RCPT-XXXXXXXX.pdf"`, `Cache-Control: no-store`. `GET /receipt` returns metadata; `GET /receipt/download` audits `RECEIPT_DOWNLOADED` first, then serves the stored bytes.
- **Failure semantics:** a PDF render failure aborts the transaction — no status change, no receipt, no checkout (recoverable by retrying after fixing the cause).

## 5e. Phase 4.4 reporting (implemented)
- **Date model:** `from_date/to_date` are calendar dates interpreted as a **half-open UTC range** `[from, to + 1 day)` — an entry received exactly on `to` belongs to the period. `hotel_info` carries no timezone setting, so UTC is the documented assumption (no IST inference).
- **Formulas:** `financial_summary` groups entry amounts by kind (`room_charges`, `additional_charges`, `discounts`, `charge_reversals`, `gross_charges` = room + additional) and computes `net_payments` (received originals minus received reversals) and `outstanding = charges − net` **for the period**. These are ledger measures, not accrued revenue: `gross_charges`/`net_payments` are gross of any other accounting treatment, and no tax accrual is computed (D5 — tax config NONE by default).
- **Collections / methods:** reversal rows always reduce the same (date, method/stage) they belong to (originals and reversals are shown separately **and netted** — a reversal is never counted as fresh money). `collections/export.csv` and `outstanding/export.csv` reuse the exact same service queries as the JSON reports; columns are enums/dates/numbers only (no free text), so formula injection is impossible; sanitized anyway for defence in depth. `Cache-Control: no-store`.
- **Outstanding:** a **live snapshot** (current ledger state, not a historical reconstruction), non-cancelled bookings with balance ≠ 0, sorted most-owed first, paginated; checked-out (settled) bookings have zero balance by construction and never appear. Credits (`balance < 0`) are reported as `credit_total`, clearly distinct from outstanding dues.
- **Reconciliation:** period-only traceability: `charge_entries = Σ entries`, `original_payments`, `reversal_payments`, `net_payments`, `outstanding_in_period`, `credit_in_period`, plus row counts; discrepancies would be visible here rather than silently adjusted (no repair is performed).
- **Bookings:** stays overlapping `[from, to + 1)` under the `[check-in, check-out)` convention; cancelled counted separately. **Occupancy:** occupied = stay-segment nights of non-cancelled bookings clipped to the range (double bookings are structurally impossible on one room); capacity = active + AVAILABLE rooms × days in range (assumes every active room was available all period — maintenance schedules are not stored, a documented limitation).

## 5f. Phase 5.1 guest portal behaviour (implemented)
- **Issuance:** the token is created transactionally with check-in (`check_in_booking`), not at booking creation (FR-PORTAL-01 superseded as above). The check-in response is the only response to ever contain `portal_access_token` (shown once; rotate behaves the same).
- **Expiry:** `checked_out_at + 24h`, derived at read time (strict: at the deadline, access is already dead). Open-ended before checkout; cancelled bookings always dead (resolution step), regardless of stored rows.
- **Responses:** all guest-portal JSON + the portal receipt PDF carry `Cache-Control: no-store, private`. Overview never contains guest phone/ids, money, folio/payment history, audit rows or other guests. Wi-Fi SSID/password appear only when configured on the hotel profile (never invented).
- **Security:** SHA-256 hash-only storage; constant-time compare on resolution; one generic `404 NOT_FOUND / Portal page not found.` for unknown/revoked/expired/cancelled; brute-force guard via the shared login limiter (hash-keyed, 10 failures/5 min); tokens never appear in logs, errors or audit metadata beyond their ids (audits: `PORTAL_TOKEN_ISSUED/REVOKED`).
- **Deferred:** tourism/tour-package content (no model yet — admins have no content table to edit; a 5.2 milestone must add it rather than this one pretending); WhatsApp delivery of links (Phase 7 mock); guest portal frontend; inactivity-window expiry (FR-PORTAL-04 "should").

## 6. Non-goals
- No GraphQL, no websockets, no webhooks (v1). No public API for third parties.
