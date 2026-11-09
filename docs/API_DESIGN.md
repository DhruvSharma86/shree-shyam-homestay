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
| `/bookings/{id}/check-in` | POST | **Deferred** — folio/settlement in Phase 4 |
| `/bookings/{id}/checkout` | POST | **Deferred** — Phase 4 |
| `/bookings/{id}/no-show` | POST | **Deferred** |
| `/bookings/{id}/guest-link` | GET / POST rotate | **Deferred** — guest portal in Phase 5 |

Create body: `{guest_id, room_id, source: PHONE|WALK_IN (default PHONE), check_in_date, check_out_date, number_of_guests (1–20, default 1), notes?}`. Success `201` returns the booking with `booking_ref`, `nights`, `night_rate_snapshot`, `room_subtotal`, `tax_*_snapshot`, `total_amount`. Overlap → `409 CONFLICT`; invalid dates/past dates/inactive guest/maintenance room/no covering rate/mid-stay rate change → `422 VALIDATION_ERROR`. Date convention: check-in inclusive, check-out exclusive. No folio, token, payment, or portal fields exist in this milestone.

### 3.5 Billing (`billing.*`) — ✅ implemented Phase 4.1 (folio/ledger, read-only payments)
| Endpoint | Method | Notes |
|---|---|---|
| `/bookings/{id}/folio` | GET | `billing.receipts.read` (both roles, D6): entries + `total_charges/total_paid/balance_due`; performs backfill-by-demand for pre-4.1 bookings |
| `/bookings/{id}/folio/charges` | POST | `billing.charges.write` (both roles), CSRF; amount computed server-side (`quantity × unit_amount`) |
| `/bookings/{id}/folio/discounts` | POST | `billing.discounts.write` (**ADMIN only**, D4), CSRF; `reason` mandatory; negative-folio rejected (422) |
| `/bookings/{id}/folio/reversals` | POST | `billing.charges.write` (both roles), CSRF; `reason` mandatory; already-reversed/reversal-of-reversal → 422 (D3: payment reversals are ADMIN-only but not implemented yet) |
| `/bookings/{id}/payments` | GET (paginated) | `billing.receipts.read` (both roles); empty until Phase 4.2 writes |
| `/bookings/{id}/payments` | POST | **Deferred to Phase 4.2** (D9 overpayment rule applies there) |
| `/bookings/{id}/payments/{id}/reverse` | POST | **Deferred to Phase 4.2** |
| `/bookings/{id}/receipts` | GET, POST (generate) | **Deferred to Phase 4.3** (ReportLab) |

Financial writes and their audit rows commit in the same transaction; audit metadata carries entry/payment ids, amounts and reasons only (no guest PII). Balances are always derived (`Σ entries − Σ payments`) with `Decimal`; no stored running total.

### 3.6 Reports & audit (ADMIN only)
| Endpoint | Method | Permission |
|---|---|---|
| `/reports/financial` | GET `?from=&to=` | `reports.financial.read` |
| `/reports/occupancy` | GET `?from=&to=` | `reports.financial.read` |
| `/audit-log` | GET `?actor=&action=&from=&to=` | `audit.read` |

### 3.7 Messaging (`billing`/`bookings` context; ADMIN config)
| Endpoint | Method | Notes |
|---|---|---|
| `/bookings/{id}/messages/welcome` | POST | sends link (mock in dev) |
| `/bookings/{id}/messages/checkout` | POST | sends checkout + receipt |
| `/messages` | GET | message_log list (ADMIN) |

### 3.8 Guest portal (no session — token in path)
| Endpoint | Method | Notes |
|---|---|---|
| `/guest/{token}` | GET | portal view (minimal data only) |
| `/guest/{token}/receipt` | GET | final PDF (post-checkout, pre-expiry) |

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

## 6. Non-goals
- No GraphQL, no websockets, no webhooks (v1). No public API for third parties.
