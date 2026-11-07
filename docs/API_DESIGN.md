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
| `/guests/{id}/bookings` | GET | Deferred — bookings do not exist yet (Phase 3.2) |

Duplicate rule: exact normalized phone + case-insensitive whitespace-collapsed name on an **active** guest → `409 CONFLICT` with `details.existing_guest_id` (no silent merge). Same phone + different name allowed. Deactivated records never block re-registration. Invalid phone → `422 VALIDATION_ERROR`. Mutations require CSRF and write audit rows (`GUEST_CREATED/UPDATED/DEACTIVATED`) without PII in metadata.

### 3.4 Bookings & availability (`bookings.*`)
| Endpoint | Method | Notes |
|---|---|---|
| `/availability` | GET `?check_in=&check_out=&room_type_id=` | rooms/types free for range |
| `/bookings` | GET (filters), POST create | creates folio + token atomically |
| `/bookings/{id}` | GET, PATCH (dates/room — overlap rechecked) | |
| `/bookings/{id}/check-in` | POST | records check-in payment stage default |
| `/bookings/{id}/checkout` | POST | settlement; returns receipt |
| `/bookings/{id}/cancel` | POST | with reason |
| `/bookings/{id}/no-show` | POST | |
| `/bookings/{id}/guest-link` | GET / POST rotate | rotate = `portal.tokens.manage` (ADMIN) |

### 3.5 Billing (`billing.*`)
| Endpoint | Method | Notes |
|---|---|---|
| `/bookings/{id}/folio` | GET | entries incl. reversals, balance |
| `/bookings/{id}/folio/charges` | POST | additional charge |
| `/bookings/{id}/folio/discounts` | POST | reason required; RBAC limit for RECEPTIONIST |
| `/bookings/{id}/folio/reversals` | POST | `{reverses_entry_id, reason}` |
| `/bookings/{id}/payments` | GET, POST | stage + mode validated |
| `/bookings/{id}/payments/{id}/reverse` | POST | refund/void as reversal entry |
| `/bookings/{id}/receipts` | GET, POST (generate) | PDF download |

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
- Dates: `check_out > check_in`; payments `amount > 0`; discounts require `reason`.
- Phone: normalised to E.164 on write; search tolerant of formatting.
- All IDs are UUIDs; booking refs human-friendly (`SSH-000123`).

## 5. Idempotency & concurrency
- Booking create & payment record accept `Idempotency-Key` header (recommended) to prevent double-submits from retries.
- State transitions use optimistic checks (`WHERE status = expected`) → `409 INVALID_STATE` on mismatch.

## 6. Non-goals
- No GraphQL, no websockets, no webhooks (v1). No public API for third parties.
