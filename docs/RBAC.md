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
| Apply discounts | ✅ | ⚠️ up to configurable limit (TBD); beyond limit → ADMIN only |
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

## 3. Receptionist operational subset
Receptionists can see bookings/guests **needed for operations** (today's arrivals, current stays, booking search by name/phone/ref). They see folio & payment details **for the booking they are handling** (required to record payments and print receipts) but **cannot** access aggregate financial reports, revenue summaries, or audit logs.

## 4. Prohibited actions (hard rules)
1. Receptionists MUST NOT modify room pricing, manage users, change system settings, or access administrative financial reports.
2. **No role** may silently delete or overwrite financial records — corrections only via reversal entries (enforced at data model + service layer).
3. No role may access another booking's guest token or bypass token expiry.
4. Admins cannot delete their own last active admin account (prevent lockout) — system MUST block deactivating the final active ADMIN.

## 5. Session & account security
- Argon2id/bcrypt password hashing; minimum password length policy (configurable, e.g. ≥ 10 chars).
- Idle session timeout (configurable default 30 min) + absolute expiry (configurable default 12 h).
- Inactive (`is_active = false`) users cannot log in; existing sessions revoked on deactivation.
- Login attempts rate-limited; failed logins audit-logged.
- Password reset: admin-initiated only (no self-service email flow in v1 — no mail service in scope).

## 6. Examples of enforcement checks
| Endpoint | Required permission |
|---|---|
| `PATCH /api/rooms/{id}/rate` | `pricing.manage` (ADMIN only) |
| `POST /api/bookings/{id}/payments` | `billing.payments.write` (both roles) |
| `GET /api/reports/financial` | `reports.financial.read` (ADMIN only) |
| `POST /api/users` | `users.manage` (ADMIN only) |
| `POST /api/bookings/{id}/discounts` | `billing.discounts.write` (+ amount ≤ limit for RECEPTIONIST) |
