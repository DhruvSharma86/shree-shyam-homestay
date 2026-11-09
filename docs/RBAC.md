# Role-Based Access Control — Shree Shyam Home Stay

Two roles only: `ADMIN`, `RECEPTIONIST`. **Default deny:** any permission not explicitly granted is denied. Permissions are enforced **server-side on every endpoint** (frontend hiding is UX only).

## 1. Permission matrix

| Capability | ADMIN | RECEPTIONIST |
|---|:---:|:---:|
| Login / logout | ✅ | ✅ |
| View own profile | ✅ | ✅ |
| Create/edit/deactivate ADMIN accounts | ✅ | ❌ |
| Create/edit/deactivate RECEPTIONIST accounts | ✅ | ❌ |
| Reset any user's credentials | ✅ | ❌ |
| Manage hotel information | ✅ | ❌ |
| Manage rooms & room categories | ✅ | ❌ |
| **Configure room prices** | ✅ | ❌ |
| Manage restaurant & cab information | ✅ | ❌ |
| Manage GST / tax settings | ✅ | ❌ |
| View all guests & bookings | ✅ | ✅ (operational subset — see §3) |
| Register guests | ✅ | ✅ |
| Create / modify bookings | ✅ | ✅ |
| Allocate rooms | ✅ | ✅ |
| Check-in / checkout | ✅ | ✅ |
| Record payments | ✅ | ✅ |
| Add additional charges | ✅ | ✅ |
| Apply discounts | ✅ | ❌ (D4: ADMIN-only, Phase 4.1) |
| Generate receipts | ✅ | ✅ |
| Send guest links (WhatsApp) | ✅ | ✅ |
| View financial reports / revenue summaries | ✅ | ❌ |
| View audit logs | ✅ | ❌ |
| Revoke/rotate guest tokens | ✅ | ❌ (receptionist can request) |
| Manage public website content | ✅ | ❌ |
| Export financial data | ✅ | ❌ |

## 2. Permission identifiers (for code)

```
users.manage, users.reset_credentials
hotel.manage, rooms.manage, pricing.manage, tax.manage
content.manage (restaurant/cab/website)
guests.read, guests.write
bookings.read, bookings.write, bookings.checkin, bookings.checkout, bookings.cancel
billing.charges.write, billing.payments.write, billing.discounts.write, billing.receipts.read
reports.financial.read, audit.read
portal.tokens.manage
```

Each endpoint declares the permission it needs; a `require_permission(...)` dependency enforces it. Missing permission → `403` with a standard error envelope.

### Phase 2.1 enforcement (implemented 2026-11-05)
All `/api/v1/admin/{hotel,room-types,rooms,room-rates,tax-settings,restaurant,menu-categories,menu-items,cab-providers}` endpoints require the mapped permission above (ADMIN only). RECEPTIONIST receives 403; unauthenticated receives 401. Public/guest-portal reads are deferred (Phases 5–6). Every mutation writes an audit record (`HOTEL_INFO_UPDATED`, `ROOM_TYPE_CREATED/UPDATED`, `ROOM_CREATED/UPDATED`, `RATE_CREATED`, `TAX_SETTINGS_CREATED`, `RESTAURANT_INFO_UPDATED`, `MENU_CATEGORY_CREATED/UPDATED`, `MENU_ITEM_CREATED/UPDATED`, `CAB_PROVIDER_CREATED/UPDATED`).

## 3. Receptionist operational subset
Receptionists can see bookings/guests **needed for operations** (today's arrivals, current stays, booking search by name/phone/ref). They see folio & payment details **for the booking they are handling** (required to record payments and print receipts) but **cannot** access aggregate financial reports, revenue summaries, or audit logs.

## 4. Prohibited actions (hard rules)
1. Receptionists MUST NOT modify room pricing, manage users, change system settings, or access administrative financial reports.
2. **No role** may silently delete or overwrite financial records — corrections only via reversal entries (enforced at data model + service layer).
3. No role may access another booking's guest token or bypass token expiry.
4. Admins cannot delete their own last active admin account (prevent lockout) — system MUST block deactivating the final active ADMIN.

## 5. Session & account security — ✅ implemented (Phase 1.2)
- **Argon2id** password hashing (`argon2-cffi`, pinned parameters); minimum password length **10** chars (`ChangePasswordRequest`, user creation, bootstrap).
- Idle session timeout (configurable default **30 min**) + absolute expiry (configurable default **12 h**) — both computed in `get_session_user`; expired/idle sessions auto-revoked.
- Inactive (`is_active = false`) users cannot log in; deactivation revokes live sessions (`revoke_user_sessions`).
- Login attempts rate-limited (**10 failures / 5 min / username**, in-process, configurable); failed logins audit-logged (`AUTH_LOGIN_FAILED`, IP only — never credentials).
- **CSRF:** double-submit cookie (`sshs_csrf` + `X-CSRF-Token` header, constant-time compare) required on all mutating endpoints.
- **Session rotation on login:** pre-login session revoked before a new one is issued (fixation defence).
- Cookies: `HttpOnly`, `SameSite=Lax`, `Secure` outside development, `Path=/`.
- Password change revokes all other live sessions for the user; ADMIN reset likewise.
- Password reset: admin-initiated only (no self-service email flow in v1 — no mail service in scope).
- **No public registration** — accounts are created only via ADMIN endpoints or the one-time bootstrap command.
- Unknown roles receive an **empty permission set** (default-deny); tested in `tests/test_permissions.py`.

### Phase 3.1 guest enforcement (implemented 2026-11-07)
`/api/v1/guests` READ endpoints require `guests.read`; mutating endpoints (`POST`, `PATCH`, `POST /{id}/deactivate`) require `guests.write` + CSRF. Both ADMIN and RECEPTIONIST hold these permissions (operational workflow). Default-deny preserved: unauthenticated → 401. Audit: `GUEST_CREATED`, `GUEST_UPDATED`, `GUEST_DEACTIVATED` appended in the mutation transaction; metadata contains field names and ids only (no names/phones/emails/addresses/notes). Aadhaar/ID documents are not collected in Phase 3.1 (see DATABASE_DESIGN §2.9).

### Phase 3.2 booking enforcement (implemented 2026-11-09)
`/api/v1/bookings` READ endpoints (`GET`, `GET /{id}`, `GET /availability[/{room_id}]`) require `bookings.read`; `POST` and `PATCH /{id}` require `bookings.write` + CSRF; `POST /{id}/cancel` requires `bookings.cancel` + CSRF. Both ADMIN and RECEPTIONIST hold all three in this milestone (operational workflow); `bookings.checkin` / `bookings.checkout` permissions exist for Phase 4 but no endpoints use them yet. Default-deny preserved: unauthenticated → 401, missing CSRF → 403. Audit: `BOOKING_CREATED`, `BOOKING_UPDATED`, `BOOKING_CANCELLED` with `metadata.fields` only (no PII). Booking responses expose `guest_id`/`room_id`, never guest name/phone/email.

### Phase 4.1 billing enforcement (implemented 2026-11-09)
`GET /api/v1/bookings/{id}/folio` and `GET /api/v1/bookings/{id}/payments` require `billing.receipts.read` (both roles, D6). Charge and charge-reversal writes (`POST .../folio/charges`, `POST .../folio/reversals`) require `billing.charges.write` + CSRF (both roles, D3). Discount writes (`POST .../folio/discounts`) require `billing.discounts.write` + CSRF and are **ADMIN-only** (D4) — RECEPTIONIST permission removed from the role set; denied calls return 403 with no ledger or audit rows. `billing.payments.write` exists but gates no endpoint until Phase 4.2 (payment reversals remain ADMIN-reserved per D3). Audit: `FOLIO_INITIALIZED`, `FOLIO_CHARGE_ADJUSTED`, `CHARGE_ADDED`, `DISCOUNT_APPLIED`, `REVERSAL_CREATED` appended in the mutation transaction; metadata carries entry/payment ids, signed amounts and reasons only (no PII). Default-deny preserved: unauthenticated → 401, missing permission → 403, missing CSRF → 403.

## 6. Examples of enforcement checks
| Endpoint | Required permission |
|---|---|
| `PATCH /api/rooms/{id}/rate` | `pricing.manage` (ADMIN only) |
| `POST /api/bookings/{id}/payments` | `billing.payments.write` (both roles) |
| `GET /api/reports/financial` | `reports.financial.read` (ADMIN only) |
| `POST /api/users` | `users.manage` (ADMIN only) |
| `POST /api/bookings/{id}/discounts` | `billing.discounts.write` (+ amount ≤ limit for RECEPTIONIST) |
| `POST /api/v1/guests` | `guests.write` (both roles) |
| `GET /api/v1/guests?q=...` | `guests.read` (both roles) |
| `POST /api/v1/bookings` | `bookings.write` (both roles, CSRF required) |
| `PATCH /api/v1/bookings/{id}` | `bookings.write` (both roles, CSRF required) |
| `POST /api/v1/bookings/{id}/cancel` | `bookings.cancel` (both roles, CSRF required) |
| `GET /api/v1/bookings` / `GET /api/v1/bookings/availability` | `bookings.read` (both roles) |
