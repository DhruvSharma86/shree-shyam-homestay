# Database Design — Shree Shyam Home Stay

PostgreSQL. Money: `NUMERIC(12,2)`. All tables: `id UUID (pk, default gen_random_uuid())`, `created_at`, `updated_at` (where mutable). Soft-deactivation preferred over hard deletes for users/rooms/guests with history.

> **Rule zero:** financial tables (`folio_entries`, `payments`) are **append-only**. Corrections = reversing entries. Enforce with application logic + DB permissions/triggers as defence in depth.

## 1. Entity list

| # | Entity | Purpose |
|---|---|---|
| 1 | `users` | Staff accounts (ADMIN / RECEPTIONIST) |
| 2 | `sessions` | Server-side staff sessions |
| 3 | `hotel_info` | Singleton hotel profile (contact, address, maps link) |
| 4 | `room_types` | Categories: Normal / Deluxe / Super Deluxe |
| 5 | `rooms` | The 6 rooms (label, type, status) |
| 6 | `room_rates` | Nightly price per room type (history-preserving) |
| 7 | `tax_settings` | GST/tax config (singleton or versioned) |
| 8 | `restaurant_info` / `cab_info` | Content for guest portal & website |
| 9 | `guests` | Guest master records |
| 10 | `bookings` | Booking header (guest, room, dates, status, token hash) |
| 11 | `folio_entries` | Charges/discounts/adjustments (append-only) |
| 12 | `payments` | Payments against a booking (append-only) |
| 13 | `audit_log` | Admin action trail (append-only) |
| 14 | `message_log` | WhatsApp/message attempts |
| 15 | `receipts` | Generated PDF receipt metadata |
| 16 | `public_content` | Website content (pages, gallery, facilities, attractions) |

## 2. Entity definitions & key fields

### 2.1 `users` — ✅ implemented (Phase 1.2, migration `bb79107c6b65`)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| username | VARCHAR(64) UNIQUE (indexed) | login id |
| email | VARCHAR(255) UNIQUE NULL | |
| password_hash | TEXT | **Argon2id** (`argon2-cffi`); plaintext never stored/logged |
| full_name | VARCHAR(120) | |
| role | VARCHAR(32) | `ADMIN` / `RECEPTIONIST` (validated at API layer; application enforces the two-role rule) |
| is_active | BOOLEAN DEFAULT TRUE | deactivation instead of delete |
| last_login_at | TIMESTAMPTZ NULL | updated on every login |
| created_by | UUID FK → users NULL | audit trail (NULL for bootstrap admin) |
| created_at / updated_at | TIMESTAMPTZ | server defaults |

### 2.2 `sessions` — ✅ implemented (Phase 1.2)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | opaque session id |
| session_token_hash | TEXT UNIQUE (indexed) | **SHA-256 hash** of cookie token; plaintext never stored |
| user_id | FK → users ON DELETE CASCADE (indexed) | |
| created_at | TIMESTAMPTZ | server default |
| last_seen_at | TIMESTAMPTZ | idle-timeout tracking (30 min default, configurable) |
| expires_at | TIMESTAMPTZ | absolute expiry (12 h default, configurable) |
| revoked_at | TIMESTAMPTZ NULL | logout / expiry / password change / deactivation |
| ip_address / user_agent | VARCHAR(45/512) | security review |
| *(no separate `idle_expiry` column)* | | Idle expiry is computed: `last_seen_at + idle_timeout`, enforced in `app/auth/service.py::get_session_user` |

### 2.3 `hotel_info` — ✅ implemented (Phase 2.1, migration `c2d3e4f5a6b7`)
Singleton row (`singleton_key = 1` UNIQUE). Fields: `id UUID PK`, `singleton_key INT UNIQUE`, `hotel_name VARCHAR(160)` (default "Shree Shyam Home Stay"), `description TEXT NULL`, `address TEXT NULL`, `city VARCHAR(120) NULL`, `state VARCHAR(120) NULL`, `pincode VARCHAR(16) NULL`, `contact_number VARCHAR(24) NULL`, `alternate_contact_number VARCHAR(24) NULL`, `email VARCHAR(255) NULL`, `google_maps_url VARCHAR(1024) NULL`, `website_url VARCHAR(1024) NULL`, `logo_url VARCHAR(1024) NULL`, `check_in_time/check_out_time VARCHAR(8) NULL`, `wifi_ssid VARCHAR(64) NULL`, `wifi_password VARCHAR(128) NULL`, `created_at/updated_at TIMESTAMPTZ`, `updated_by UUID NULL`. Row created on first ADMIN PATCH; updated thereafter. **All values TBD/configurable — none seeded.**

### 2.4 `room_types` — ✅ implemented (Phase 2.1)
`id UUID PK`, `name VARCHAR(64) UNIQUE INDEXED` (Normal / Deluxe / Super Deluxe — admin-configurable, no seeds), `description TEXT NULL`, `maximum_occupancy INT DEFAULT 2`, `amenities TEXT NULL`, `is_active BOOL DEFAULT TRUE`, `display_order INT DEFAULT 0`, `created_at/updated_at`. Categories referenced by rooms/bookings are **never deleted** — `is_active=false` only.

### 2.5 `rooms` — ✅ implemented (Phase 2.1)
`id UUID PK`, `room_number VARCHAR(16) UNIQUE INDEXED` (assigned by ADMIN — **never invented**), `room_type_id FK → room_types RESTRICT INDEXED`, `floor INT NULL`, `description TEXT NULL`, `maximum_occupancy INT DEFAULT 2`, `operational_status VARCHAR(16)` ∈ {AVAILABLE, MAINTENANCE, INACTIVE} (validated at API layer; **operational state, NOT booking occupancy**), `is_active BOOL DEFAULT TRUE`, `created_at/updated_at`.

### 2.6 `room_rates` — ✅ implemented (Phase 2.1, versioned/append-only)
`id UUID PK`, `room_type_id FK → room_types RESTRICT INDEXED`, `nightly_rate NUMERIC(12,2) NOT NULL CHECK ≥ 0`, `valid_from DATE`, `valid_until DATE NULL CHECK ≥ valid_from`, `is_active BOOL DEFAULT TRUE`, `created_by UUID NULL`, `created_at`. Price changes create **new rows**; old rows untouched. Overlap prevention: application-level check within the creation transaction (see §2.10 pattern). *Booking snapshots the rate at creation (Phase 3).*

### 2.7 `tax_settings` — ✅ implemented (Phase 2.1, versioned/append-only)
`id UUID PK`, `registration_status VARCHAR(16) DEFAULT 'NONE'`, `tax_type VARCHAR(16) DEFAULT 'NONE'`, `tax_rate NUMERIC(5,2) NULL CHECK ≥ 0` (required when tax_type ≠ NONE), `pricing_mode VARCHAR(16) DEFAULT 'EXCLUSIVE'` ∈ {INCLUSIVE, EXCLUSIVE}, `valid_from DATE`, `valid_until DATE NULL`, `notes TEXT NULL`, `created_by UUID NULL`, `created_at`. **Default = NONE; no GST registration or rate is assumed or seeded.** Overlap prevention same as room_rates. *Invoice/tax calculations belong to Phase 4.*

### 2.8 `restaurant_info` / `cab_info` — ✅ implemented (Phase 2.1)
**restaurant_info** (singleton like hotel_info): `id`, `singleton_key UNIQUE`, `name VARCHAR(160)`, `description TEXT NULL`, `contact_number VARCHAR(24) NULL`, `opening_hours VARCHAR(256) NULL`, `is_active`, timestamps, `updated_by`.
**menu_categories**: `id`, `name VARCHAR(120) UNIQUE INDEXED`, `description TEXT NULL`, `display_order INT`, `is_active`, timestamps.
**menu_items**: `id`, `name VARCHAR(160)`, `description TEXT NULL`, `price NUMERIC(12,2) CHECK ≥ 0`, `image_url VARCHAR(1024) NULL` (**URL only — no binaries in PostgreSQL**), `category_id FK → menu_categories RESTRICT INDEXED`, `is_vegetarian BOOL DEFAULT TRUE`, `is_available BOOL DEFAULT TRUE`, `display_order INT`, timestamps.
**cab_info**: `id`, `company_name VARCHAR(160) INDEXED`, `description TEXT NULL`, `contact_number VARCHAR(24) NOT NULL`, `website_url VARCHAR(1024) NULL` (validated HttpUrl), `service_description TEXT NULL`, `is_active`, `display_order INT`, timestamps. Multiple providers allowed; no booking integration.

### 2.9 `guests` — ✅ implemented (Phase 3.1, migration `d4e5f6a7b8c9`)
`id UUID PK`, `full_name VARCHAR(160) INDEXED` (stored whitespace-collapsed), `phone VARCHAR(24) INDEXED` (stored **E.164 normalized**), `email VARCHAR(255) NULL INDEXED`, `address TEXT NULL`, `notes TEXT NULL`, `is_active BOOL DEFAULT TRUE INDEXED`, `created_at/updated_at TIMESTAMPTZ`, `created_by/updated_by UUID NULL`.
Duplicate rule: one **active** guest per `(phone, lower(full_name))` — stored names are whitespace-collapsed by the service on write, so the index matches the application rule. Enforced by service check + partial unique expression index `ix_guests_phone_name_active (phone, lower(full_name)) WHERE is_active` (PostgreSQL `is_active = TRUE`, SQLite `is_active = 1`). Same phone + different name allowed; exact match → `409` with `existing_guest_id`. Deactivated guests never block re-registration. Soft-deactivation only; never hard-deleted.
**Aadhaar deferred (not in Phase 3.1):** no image, number, or `id_proof_type/number` columns exist. Full ID-proof handling requires legal review, private encrypted storage, access control and retention rules — a separate approved milestone. `id_proof_type/number` are therefore **not** collected. See SRS §3.3 note.

### 2.10 `bookings` (core) — ✅ implemented (Phase 3.2, migration `e5f6a7b8c9d0`)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| booking_ref | VARCHAR(16) UNIQUE INDEXED | server-generated `SSH-XXXXXXXX` (UUID-derived; unique without counters) |
| guest_id | FK → guests RESTRICT INDEXED | must be an **active** guest at creation |
| room_id | FK → rooms RESTRICT INDEXED | allocated room (must be active + AVAILABLE) |
| room_type_id | FK → room_types RESTRICT INDEXED | stamped from the room at creation/reallocation |
| status | VARCHAR(16) INDEXED | `CONFIRMED` or `CANCELLED` only (Phase 3.2) |
| source | VARCHAR(16) | `PHONE` or `WALK_IN` (no online source exists) |
| check_in_date | DATE INDEXED | inclusive |
| check_out_date | DATE | exclusive; CHECK `check_out_date > check_in_date` |
| nights | INT CHECK ≥ 1 | `(check_out − check_in).days`, computed server-side |
| number_of_guests | INT CHECK ≥ 1 | expected guests (1–20) |
| notes | TEXT NULL | staff notes |
| night_rate_snapshot | NUMERIC(12,2) CHECK ≥ 0 | nightly rate at booking time (Decimal; never recomputed from mutable rates) |
| rate_id | UUID NULL | `room_rates.id` version used |
| room_subtotal | NUMERIC(12,2) CHECK ≥ 0 | `night_rate_snapshot × nights` (Decimal, 2dp) |
| tax_type_snapshot | VARCHAR(16) | `NONE` default when no tax settings exist |
| tax_rate_snapshot | NUMERIC(5,2) NULL | copied tax rate; NULL when NONE |
| tax_pricing_mode_snapshot | VARCHAR(16) | `INCLUSIVE`/`EXCLUSIVE` (`EXCLUSIVE` default) |
| total_amount | NUMERIC(12,2) CHECK ≥ 0 | `== room_subtotal` in Phase 3.2; tax computation belongs to billing (Phase 4) |
| created_by / updated_by | UUID NULL | staff user ids |
| created_at / updated_at | TIMESTAMPTZ | `CURRENT_TIMESTAMP` defaults |
| cancelled_at | TIMESTAMPTZ NULL | set on cancellation |
| cancellation_reason | TEXT NULL | optional reason (policy TBD) |

Not in Phase 3.2 (deferred): `guest_token_hash`, `checkout_at`, folio/payment links — added by later milestones. No guest PII is copied into the booking; `guest_id` is the only link.

**Overlap prevention (defence in depth, Phase 3.2 choice):**
1. Application check on create/modify (SELECT FOR UPDATE on the room row, then verify no overlapping active booking) — serialises concurrent staff attempts per room.
2. PostgreSQL exclusion constraint `excl_bookings_room_daterange`: `EXCLUDE USING gist (room_id WITH =, daterange(check_in_date, check_out_date, '[)') WITH &&) WHERE (status <> 'CANCELLED')`, requiring the `btree_gist` extension. Added in the migration (raw SQL; the ORM model intentionally omits it so SQLite test schemas still build). Integrity errors map to `409 CONFLICT`.
3. Unique partial index alone is insufficient for ranges — the app check + transaction is the primary guard; the exclusion constraint is the backstop.

SQLite has no exclusion constraint; its guard is the service-level room-row lock (writes are serialised). Availability queries use the same `[check_in, check_out)` predicate everywhere (`existing.check_in < new.check_out AND existing.check_out > new.check_in`); cancelled bookings are excluded from both.

### 2.11 `folio_entries` (append-only)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| booking_id | FK → bookings | |
| entry_type | ENUM('ROOM_CHARGE','ADDITIONAL_CHARGE','DISCOUNT','TAX','REVERSAL') | |
| description | VARCHAR(255) | |
| quantity | NUMERIC(10,2) DEFAULT 1 | nights / units |
| unit_amount | NUMERIC(12,2) | |
| amount | NUMERIC(12,2) | signed; negative for discounts/reversals |
| reverses_entry_id | FK → folio_entries NULL | for REVERSAL entries |
| created_by | FK → users | |
| created_at | TIMESTAMPTZ | immutable |

Positive = charge; negative = discount/reversal (keeps balance math simple: balance = Σ entries − Σ payments).

### 2.12 `payments` (append-only)
`id`, `booking_id FK`, `amount NUMERIC(12,2) > 0`, `mode ENUM('CASH','UPI','CARD_POS')`, `payment_stage ENUM('ADVANCE','CHECK_IN','CHECKOUT','OTHER')`, `reference_note NULL`, `received_by FK → users`, `received_at`, `reversed_payment_id NULL` + optional `reversal` rows for refunds/voids (model TBD in billing workflow doc).
*No UPDATE/DELETE allowed post-commit except via reversal rows.*

### 2.13 `audit_log` (append-only) — ✅ implemented (Phase 1.2)
`id UUID PK`, `actor_user_id FK → users ON DELETE SET NULL NULL` (NULL = system events such as bootstrap), `action VARCHAR(64) INDEXED` (`AUTH_LOGIN`, `AUTH_LOGOUT`, `AUTH_LOGIN_FAILED`, `PASSWORD_CHANGED`, `PASSWORD_RESET`, `USER_CREATED`, `USER_UPDATED`, `USER_DEACTIVATED`, `SESSIONS_REVOKED`, `ADMIN_BOOTSTRAPPED`, later: `RATE_CHANGED`, `DISCOUNT_APPLIED`, `PAYMENT_REVERSED`, ...), `resource_type VARCHAR(64)`, `resource_id VARCHAR(128)`, `metadata_json JSON NULL` (**safe, non-secret context only** — never passwords/tokens), `ip_address VARCHAR(45) NULL`, `created_at TIMESTAMPTZ INDEXED`. Write path: `app/auth/service.py::write_audit`.

### 2.14 `message_log`
`id`, `booking_id FK NULL`, `channel VARCHAR(16)` ('WHATSAPP'), `message_type VARCHAR(32)`, `recipient_phone`, `status ENUM('QUEUED','SENT','FAILED','MOCKED')`, `provider_message_id NULL`, `error TEXT NULL`, `created_at`.

### 2.15 `receipts`
`id`, `booking_id FK`, `kind ENUM('PAYMENT','FINAL')`, `file_path VARCHAR(512)`, `generated_by FK`, `created_at`.

### 2.16 `public_content`
`id`, `page VARCHAR(32)` ('home','about','rooms','gallery','facilities','restaurant','attractions','contact'), `title`, `body`, `image_urls JSONB`, `sort_order`, `updated_at`. Seeded empty; content is TBD.

## 3. Relationships (ER summary)

```
users ──< sessions
users ──< bookings (created_by)
users ──< payments (received_by)
users ──< audit_log (actor)

room_types ──< rooms ──< bookings
room_types ──< room_rates
tax_settings (versioned)

guests ──< bookings (primary guest)
bookings ──< folio_entries
bookings ──< payments
bookings ──< receipts
bookings ──< message_log
```

## 4. Integrity rules
- FK constraints everywhere; `ON DELETE RESTRICT` for financial/guest history.
- Check constraints: bookings `check_out_date > check_in_date`, `nights >= 1`, `number_of_guests >= 1`, money `>= 0`; (Phase 4 adds `payments.amount > 0`, `folio_entries.amount <> 0`).
- Unique: `users.username`, `rooms.room_number`, `bookings.booking_ref` (Phase 5 adds `bookings.guest_token_hash`).
- Indexes: `bookings(room_id, status, check_in_date, guest_id, room_type_id)`; `guests(phone)`, `audit_log(created_at)`, `sessions(user_id)`; (Phase 4 adds `payments(booking_id)`, `folio_entries(booking_id)`).
- PostgreSQL-only: exclusion constraint `excl_bookings_room_daterange` on `bookings` (see §2.10); not present in SQLite/ORM metadata.

## 5. Migrations
- Alembic autogenerate is a starting point only — **every migration reviewed manually** before merge.
- Destructive changes require a written note in the migration + SRS/Open-Decisions reference.
- Seed data: roles/room types only. **No seeded prices, GST rates, contacts, or content.**

## 6. Retention
- Financial + audit data: retained indefinitely (legal retention TBD).
- Sessions: purge expired/revoked after 30 days (configurable).
- Message logs: retain ≥ 1 year (TBD).
