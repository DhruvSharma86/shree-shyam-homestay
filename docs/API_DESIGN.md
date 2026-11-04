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

## 2. Authentication
| Endpoint | Method | Notes |
|---|---|---|
| `/api/v1/auth/login` | POST | `{username, password}` → sets session cookie; rate-limited |
| `/api/v1/auth/logout` | POST | revokes server session |
| `/api/v1/auth/me` | GET | current user (id, name, role, permissions) |

Session cookie: `HttpOnly; Secure; SameSite=Lax; Path=/`. Idle + absolute expiry per RBAC doc.

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
| `/hotel` | GET, PATCH | `hotel.manage` |
| `/room-types` | GET, POST, PATCH | `rooms.manage` |
| `/rooms` | GET, POST, PATCH | `rooms.manage` |
| `/rooms/{id}/rates` | GET, POST (new rate version) | `pricing.manage` |
| `/tax-settings` | GET, POST (new version) | `tax.manage` |
| `/content/restaurant` | GET, PATCH | `content.manage` |
| `/content/cab` | GET, PATCH | `content.manage` |
| `/content/public/{page}` | GET, PATCH | `content.manage` |

### 3.3 Guests (`guests.read` / `guests.write`)
| Endpoint | Method | Notes |
|---|---|---|
| `/guests` | GET (search `?q=`), POST | phone-normalised lookup |
| `/guests/{id}` | GET, PATCH | booking history embedded or via `/guests/{id}/bookings` |

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
