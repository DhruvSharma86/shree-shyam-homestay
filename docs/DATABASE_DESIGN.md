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

### 2.3 `hotel_info` (singleton row — enforced by id check or unique `singleton_key`)
`id`, `name` (default "Shree Shyam Home Stay"), `address_text`, `phone`, `email`, `website_url`, `maps_url`, `check_in_time`, `check_out_time`, `wifi_ssid`, `wifi_password`, timezone. **All values TBD/configurable — no invented data.**

### 2.4 `room_types`
`id`, `code UNIQUE` ('NORMAL','DELUXE','SUPER_DELUXE'), `name`, `description`, `is_active`.

### 2.5 `rooms`
`id`, `room_number VARCHAR(16) UNIQUE` (e.g. "101"), `room_type_id FK`, `status ENUM('ACTIVE','OUT_OF_SERVICE')`, `max_occupancy INT`, `notes`.

### 2.6 `room_rates` (rate history — price changes create new rows)
`id`, `room_type_id FK`, `nightly_price NUMERIC(12,2) NOT NULL`, `effective_from DATE`, `effective_to DATE NULL` (open-ended = current), `currency CHAR(3) DEFAULT 'INR'`, `created_by FK`, `created_at`.
*Booking snapshots the rate at creation (see `bookings.rate_snapshot`).*

### 2.7 `tax_settings` (versioned or singleton — versioned recommended for audit)
`id`, `is_gst_registered BOOL` (TBD — **never assume**), `gst_number VARCHAR(32) NULL`, `tax_mode ENUM('NONE','EXCLUSIVE','INCLUSIVE')`, `gst_rate_percent NUMERIC(5,2) NULL`, `effective_from/to`, `created_by`, `created_at`.
*No default rate is seeded. If not GST-registered, `tax_mode='NONE'`.*

### 2.8 `restaurant_info` / `cab_info`
`id`, plus restaurant: `menu_text`/`menu_items JSONB`, `photos JSONB` (URLs/keys), `contact_name`, `contact_phone`, `timings`; cab: `company_name`, `contact_phone`, `website_url`, `notes`. All TBD.

### 2.9 `guests`
`id`, `full_name VARCHAR(160)`, `phone VARCHAR(24)` (normalized), `email NULL`, `id_proof_type NULL` (e.g. Aadhaar/Passport — values TBD), `id_proof_number NULL` (stored minimally; consider encryption at rest — see security risks in SRS handoff), `address NULL`, `notes NULL`, `created_at/updated_at`.
*Index on `phone` for returning-guest lookup. No hard delete if bookings exist.*

### 2.10 `bookings` (core)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| booking_ref | VARCHAR(16) UNIQUE | human ref, e.g. `SSH-000123` |
| guest_id | FK → guests | primary guest |
| room_id | FK → rooms | allocated room |
| source | ENUM('PHONE','WALK_IN') | no online source exists |
| status | ENUM(see workflow) | `CONFIRMED, CHECKED_IN, CHECKED_OUT, CANCELLED, NO_SHOW` |
| check_in_date | DATE | |
| check_out_date | DATE | must be > check_in_date |
| rate_snapshot | NUMERIC(12,2) | nightly rate at booking time |
| guest_token_hash | TEXT UNIQUE | hash of guest portal token; plaintext never stored |
| checkout_at | TIMESTAMPTZ NULL | actual checkout timestamp (drives 24h token expiry) |
| created_by | FK → users | |
| created_at / updated_at | TIMESTAMPTZ | |

**Overlap prevention (defence in depth):**
1. Application check on create/modify (SELECT FOR UPDATE on room row, then verify no overlapping active booking).
2. PostgreSQL exclusion constraint using `daterange` if the btree_gist extension is acceptable, **or** a serializable transaction + advisory lock per room.
3. Unique partial index alone is insufficient for ranges — the app check + transaction is the primary guard; exclusion constraint is the backstop.

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
- Check constraints: `check_out_date > check_in_date`; `payments.amount > 0`; `folio_entries.amount <> 0`.
- Unique: `users.username`, `rooms.room_number`, `bookings.booking_ref`, `bookings.guest_token_hash`.
- Indexes: `bookings(room_id, status, check_in_date, check_out_date)`, `payments(booking_id)`, `folio_entries(booking_id)`, `guests(phone)`, `audit_log(created_at)`, `sessions(user_id)`.

## 5. Migrations
- Alembic autogenerate is a starting point only — **every migration reviewed manually** before merge.
- Destructive changes require a written note in the migration + SRS/Open-Decisions reference.
- Seed data: roles/room types only. **No seeded prices, GST rates, contacts, or content.**

## 6. Retention
- Financial + audit data: retained indefinitely (legal retention TBD).
- Sessions: purge expired/revoked after 30 days (configurable).
- Message logs: retain ≥ 1 year (TBD).
