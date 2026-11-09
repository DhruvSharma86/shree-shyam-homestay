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

### Phase 5.2 content enforcement (implemented 2026-11-09)
`/api/v1/admin/{tour-packages,local-info}` GET/POST/PATCH require `content.manage` (**ADMIN-only**); RECEPTIONIST → 403, unauthenticated → 401, missing CSRF → 403. Audits `TOUR_PACKAGE_CREATED/UPDATED`, `LOCAL_INFO_CREATED/UPDATED` carry names/titles only (no guest PII). The guest tourism endpoint requires no permission (bearer-link-only; active rows only).

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
`GET /api/v1/bookings/{id}/folio` and `GET /api/v1/bookings/{id}/payments` require `billing.receipts.read` (both roles, D6). Charge and charge-reversal writes (`POST .../folio/charges`, `POST .../folio/reversals`) require `billing.charges.write` + CSRF (both roles, D3). Discount writes (`POST .../folio/discounts`) require `billing.discounts.write` + CSRF and are **ADMIN-only** (D4) — RECEPTIONIST permission removed from the role set; denied calls return 403 with no ledger or audit rows. Audit: `FOLIO_INITIALIZED`, `FOLIO_CHARGE_ADJUSTED`, `CHARGE_ADDED`, `DISCOUNT_APPLIED`, `REVERSAL_CREATED` appended in the mutation transaction; metadata carries entry/payment ids, signed amounts and reasons only (no PII). Default-deny preserved: unauthenticated → 401, missing permission → 403, missing CSRF → 403.

### Phase 4.2 payment & check-in enforcement (implemented 2026-11-09)
`POST /api/v1/bookings/{id}/payments` requires `billing.payments.write` + CSRF (both roles); the overpaying calls are additionally gated: RECEPTIONIST always 422, ADMIN needs a non-empty `overpayment_reason` (audited `OVERPAYMENT_AUTHORIZED`). Payment reversal (`POST .../payments/{payment}/reverse`) requires the same permission **plus an explicit ADMIN role check** (D3 — backend permission + role gate; RECEPTIONIST → 403). `POST /api/v1/bookings/{id}/check-in` requires `bookings.checkin` + CSRF (both roles). `POST /api/v1/bookings/{id}/folio/initialize` requires `billing.charges.write` + CSRF (both roles). All payment mutations audit `PAYMENT_RECORDED` (with `PAYMENT_REVERSED`, `OVERPAYMENT_AUTHORIZED`, `GUEST_CHECKED_IN` for the related flows): ids, modes, stages, amounts, reasons — never guest PII. Default-deny preserved throughout.

### Phase 4.3 checkout & receipt enforcement (implemented 2026-11-09)
`POST /api/v1/bookings/{id}/check-out` requires `bookings.checkout` + CSRF (both roles). `GET /api/v1/bookings/{id}/receipt` and `GET /api/v1/bookings/{id}/receipt/download` require `billing.receipts.read` (both roles, D6) — staff-only, no public links; downloads audit `RECEIPT_DOWNLOADED`. Checkout audits `CHECKOUT_COMPLETED` and `RECEIPT_ISSUED` in the settlement transaction; metadata carries booking/receipt ids and totals/hash only (no PII). Financial reports remain ADMIN-only (`reports.financial.read`).

### Phase 4.4 report enforcement (implemented 2026-11-09)
Every `/api/v1/reports/*` endpoint (financial summary/collections/methods/outstanding/reconciliation/reversals, bookings summary/occupancy, and both CSV exports) requires `reports.financial.read`, which is **ADMIN-only** — RECEPTIONIST receives 403 and unauthenticated 401 (default-deny preserved). Reports are GET-only (no mutation endpoints exist), so CSRF does not apply (no state change). No guest PII is returned (only booking references, room numbers, statuses).

### Phase 5.1 guest portal enforcement (implemented 2026-11-09)
`/api/v1/guest-portal/{token}/*` routes **require no staff session and no RBAC permission** (bearer-link isolation: unresolved/expired/revoked/cancelled tokens all get the same generic 404; a brute-force limiter guards guessing). Staff administration under `/api/v1/guest-portal/admin-status|admin-revoke|admin-rotate/{booking_id}` requires `portal.tokens.manage` (**ADMIN-only**), with CSRF on the two mutation routes. Today `portal.tokens.manage` grants in practice: status (never raw), permanent revoke, rotate (raw token shown once). Audits: `PORTAL_TOKEN_ISSUED` / `PORTAL_TOKEN_REVOKED` (booking id only — never the raw token, never guest PII). Default-deny preserved: unauthenticated staff routes → 401, RECEPTIONIST → 403, missing CSRF → 403. Existing ADMIN/RECEPTIONIST roles and permissions are otherwise untouched; no guest-facing permission is required or added.

### Phase 5.3 Priority 1 route-guard correction (implemented 2026-11-09)
The `/admin/*` area no longer uses the single exclusive `RequireAdmin` layout guard: `RequireStaff` (any authenticated session, via the shared `useSession()` hook) wraps the shell, `AdminShell` filters navigation by role (RECEPTIONIST sees Dashboard + Bookings; ADMIN sees all sections), and route-level `RequireAdmin` gates `/admin/tourism`. RECEPTIONIST regains the permitted operational UI (`bookings.*` list/check-in/payments + link display) with rotate/revoke controls hidden client-side by `portal.tokens.manage` (the backend still denies them with 403). ADMIN behavior is unchanged.
- Rationale: backend RBAC already granted receptionist booking/billing operations; only the frontend guard blocked them. Frontend visibility mirrors backend permissions only (UX affordance); backend remains authoritative.

### Phase 4.4 report enforcement (implemented 2026-11-09)
Every `/api/v1/reports/*` endpoint (financial summary/collections/methods/outstanding/reconciliation/reversals, bookings summary/occupancy, and both CSV exports) requires `reports.financial.read`, which is **ADMIN-only** — RECEPTIONIST receives 403 and unauthenticated 401 (default-deny preserved). Reports are GET-only (no mutation endpoints exist), so CSRF does not apply (no state change). No guest PII is returned (only booking references, room numbers, statuses).

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
