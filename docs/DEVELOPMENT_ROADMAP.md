# Development Roadmap — Shree Shyam Home Stay

> **Current status: Phase 4.2 (Payment recording & check-in management, backend) — ✅ complete.**
> Phases 1–3 are closed and PostgreSQL-verified. Phase 4.1 delivered the append-only folio/ledger foundation; Phase 4.2 adds read-only folio reads with explicit backfill, payment recording with D9 overpayment authorization, ADMIN-only payment reversals, and the `CHECKED_IN` lifecycle with the mandatory one-night CHECK_IN payment rule (stored snapshot), all with booking-row locks and PG trigger immutability — backend tests green; PostgreSQL verified via GitHub Actions (see CI). No checkout settlement, PDFs, frontend or reports in this milestone.

## Phase 0 — Documentation & design ✅ (this milestone)
- [x] README, SRS, Architecture, Database, RBAC, Booking/Billing workflows, Guest portal, API design, Roadmap
- [ ] Stakeholder review; resolve or defer TBD decisions (§10 of SRS)
- **Exit criteria:** docs approved; TBD list triaged into "decide now" vs "defer to phase".

## Phase 1 — Foundation
### Phase 1.1 — Backend foundation ✅ (complete, 2026-11-05)
- [x] Backend scaffold: FastAPI + SQLAlchemy 2.0 (sync, AD-1) + Pydantic v2 + Alembic, `pyproject.toml`, `docker-compose.yml` (Postgres 16)
- [x] Core: env-based settings (`app/core/config.py`), structured JSON logging, error envelope + handlers (`app/core/errors.py`), DB infra (`app/core/db.py`), health endpoints (`/health`, `/health/live`, `/health/ready`)
- [x] Backend test harness (pytest, 14 tests passing), ruff lint clean, `.env.example`, `.gitignore` (root + backend)
- [x] Alembic configured (env-driven URL); no migrations/tables yet by design
- **Exit criteria met:** app starts, health endpoints verified live, tests green, alembic `check` clean (no pending ops).
- ⚠️ **Not done (belongs to 1.2+):** session auth, RBAC middleware, users/sessions models, ADMIN bootstrap, first migration.

### Phase 1.2 — Auth, users, RBAC ✅ (complete, 2026-11-05)
- [x] `users`, `sessions`, `audit_log` models + first Alembic migration (`bb79107c6b65_auth_users_sessions_audit_log.py`); one-time initial ADMIN bootstrap (env credentials, refuses when users exist)
- [x] Session-cookie auth: `POST /api/v1/auth/login|logout|change-password`, `GET /api/v1/auth/me`; Argon2id; idle (30 min) + absolute (12 h) timeouts; generic failure messages; session rotation on login; CSRF (double-submit); per-username login rate limiting
- [x] RBAC: 22 permissions in `app/core/permissions.py`, default-deny mapping (ADMIN = all, RECEPTIONIST = operational subset); `require_permission` dependency enforced server-side; user management endpoints under `users.manage` (create/list/patch/reset-password/deactivate); last-active-ADMIN deactivation blocked
- [x] Audit logging for auth + user-management events (no secrets in metadata); auth/RBAC/bootstrap/audit test suites — **53 passed, 2 skipped** (PostgreSQL tests skip locally, enforced in CI via `--run-postgres-check`)
- [x] CI: `.github/workflows/ci.yml` (ruff + mypy + SQLite tests; Alembic upgrade on clean PostgreSQL + schema verification + PostgreSQL integration tests that FAIL if skipped)
- [ ] Frontend skeleton (Next.js + Tailwind + shadcn/ui) — deferred to Phase 2
- **Exit criteria met (locally):** admin can log in; RBAC denies by default; tests green; migration runs clean on SQLite. ⚠️ **PostgreSQL verification requires the first CI run** (no Docker/PostgreSQL on this dev machine).

## Phase 2 — Hotel configuration & users management
### Phase 2.1 — Hotel configuration & room management ✅ (complete, 2026-11-05)
- [x] Models: `hotel_info` (singleton), `room_types`, `rooms`, `room_rates` (versioned append-only), `tax_settings` (versioned, default NONE), `restaurant_info`, `menu_categories`, `menu_items`, `cab_info` — migration `c2d3e4f5a6b7`
- [x] Admin APIs: `/api/v1/admin/hotel|room-types|rooms|room-rates|tax-settings|restaurant|menu-categories|menu-items|cab-providers` (ADMIN-only RBAC, CSRF, audit on every mutation)
- [x] 91 tests passing locally (SQLite); Alembic upgrade/downgrade clean on persistent SQLite; PostgreSQL verification via GitHub Actions
- **Exit criteria met (backend):** ADMIN can configure everything without code changes/DB edits; receptionist blocked (403) from all config routes; unauthenticated blocked (401). Room numbers, prices, GST rates, contacts remain unseeded/configurable — none invented.

### Phase 2.2 — Admin Dashboard & frontend ✅ (complete, 2026-11-06)
- [x] Next.js 16 (TypeScript/Tailwind) frontend under `frontend/`; `/login` + 11 admin routes (`/admin/dashboard|hotel|room-types|rooms|room-rates|tax-settings|restaurant|menu|cab-providers|users|audit-logs`)
- [x] Session-cookie auth (no localStorage), CSRF header interceptor, `RequireAdmin` session restoration + role restriction (receptionists blocked, backend authoritative)
- [x] All Phase 2.1 APIs integrated (hotel, room types, rooms, rates, tax, restaurant/menu, cab, users); audit-logs correctly labelled pending (no read API exists)
- [x] Vitest: 9 tests passing; `tsc --noEmit`, ESLint and `next build` all clean; sidebar + responsive tables for desktop/mobile
- **Exit criteria met:** Admin can manage all hotel configuration without DB/code; no invented metrics/prices/GST/rooms. Unit tests only — no Playwright E2E yet.
- Next: Phase 3 (guests & bookings, backend) — do not start automatically.

#### Phase 3.1 — Guest registration & guest records ✅ (complete, 2026-11-07)
- [x] `guests` model (E.164 phone, whitespace-collapsed name, partial unique index on active phone+name), migration `d4e5f6a7b8c9`
- [x] APIs: `POST/GET /api/v1/guests`, `GET/PATCH /api/v1/guests/{id}`, `POST /api/v1/guests/{id}/deactivate` (both roles via `guests.read/write`, CSRF, audit `GUEST_CREATED/UPDATED/DEACTIVATED` without PII)
- [x] Search (`?q=` name/email/phone, pagination + total, `include_inactive`), duplicate rule (active phone+name → 409), re-registration after deactivation allowed
- [x] Aadhaar/document handling **explicitly deferred** (no image/number stored; legal/encryption/retention design still required)
- [x] **125 tests passing, 3 skipped** (SQLite); Alembic upgrade/downgrade clean on persistent SQLite; PostgreSQL integration tests exist and run in CI (fail-if-skip guard) — awaiting first CI run
- **Exit criteria met:** register, retrieve, search, update, deactivate with audit; no booking/billing/portal/frontend changes.

#### Phase 3.2 — Booking management ✅ (complete, backend only)
- [x] `bookings` model + migration `e5f6a7b8c9d0` (FKs: guest/room/room-type RESTRICT; check constraints; PostgreSQL exclusion constraint `excl_bookings_room_daterange` via `btree_gist`, partial `status <> 'CANCELLED'`)
- [x] APIs: `POST/GET /api/v1/bookings`, `GET/PATCH /api/v1/bookings/{id}`, `POST /api/v1/bookings/{id}/cancel`, `GET /api/v1/bookings/availability[/{room_id}]` (both roles via `bookings.read/write/cancel`, CSRF, audit `BOOKING_CREATED/UPDATED/CANCELLED` without PII)
- [x] Date convention `[check_in, check_out)`, overlap/conflict rules, maintenance/inactive-room rejection, past-date rejection, cancelled-release + idempotent cancel
- [x] Rate snapshot (single-rate policy, mid-stay change → 422) + tax snapshot (NONE default); `Decimal` money; deactivated guests cannot book; no folio/token/payment/portal/check-in/out — all deferred
- [x] Concurrency: room-row `FOR UPDATE` + PostgreSQL exclusion constraint; threaded PostgreSQL test + SQLite DB-guard test
- **Exit criteria met (backend):** phone/walk-in creation, list/filter, retrieval, update, cancel, availability, audit; no check-in/checkout/billing/frontend changes.
- Next: Phase 4 (billing, payments, receipts) — do not start automatically.

### Phase 3 — Guests & bookings ✅ (complete)
- Phase 3.1 guests + Phase 3.2 bookings delivered. No Phase 3 work remains.

## Phase 4 — Billing, payments, receipts
#### Phase 4.1 — Billing architecture & folio foundation ✅ (complete, 2026-11-09)
- [x] `folio_entries` + `payments` models, migration `f6a7b8c9d0e1`, PG immutability triggers (`trg_folio_entries_immutable`, `trg_payments_immutable`), downgrade drops triggers first
- [x] Initial ROOM_CHARGE created exactly once per booking (booking-creation transaction, partial unique index `ux_folio_initial_room_charge`, savepoint-guarded, backfill-by-demand on first `GET /folio` for pre-4.1 bookings, stays consistent across stay-date updates via REVERSAL + revised charge)
- [x] APIs: `GET /bookings/{id}/folio`, `POST .../folio/charges`, `POST .../folio/discounts` (ADMIN-only, D4), `POST .../folio/reversals`, `GET /bookings/{id}/payments` (read-only; both roles per D6)
- [x] Balance derived (`Σ entries − Σ payments`, Decimal, zero-safe); discounts/reversals cannot make the folio negative; corrections are reversal rows only; audit `FOLIO_INITIALIZED`/`FOLIO_CHARGE_ADJUSTED`/`CHARGE_ADDED`/`DISCOUNT_APPLIED`/`REVERSAL_CREATED` without PII
- [x] **168 tests passing, 8 skipped** (SQLite; 2 PG billing tests skip locally, enforced in CI); Alembic upgrade/downgrade clean on SQLite; PostgreSQL tests run in CI with fail-if-skip guard
- **Exit criteria met (backend):** folio view with derived balance, atomic initial charge, append-only ledger, reversible charges, immutable PG store, RBAC/audit. No payment writing, check-in/out, settlement, receipts, frontend or reports.
- Next: Phase 4.2 (payment recording) — do not start automatically.

#### Phase 4.2 — Payment recording & check-in management ✅ (complete, 2026-11-09)
- [x] `GET /folio` made read-only (Phase 4.1 side effect corrected, verified by ledger/audit count tests); explicit idempotent `POST /folio/initialize` as the auditable backfill (never for cancelled bookings)
- [x] Payment recording: `POST /payments` (CASH/UPI/CARD_POS × ADVANCE/CHECK_IN/CHECKOUT/OTHER, optional reference, server-validated mode/stage), D9 overpayment gate (ADMIN + mandatory reason, `OVERPAYMENT_AUTHORIZED` audited), ADMIN-only payment reversal (D3) as linked reversal rows with net paid recomputation; duplicate/cross/self reversals → 422
- [x] `CHECKED_IN` lifecycle (`checked_in_at/by`, migration `a8b9c0d1e2f3`) with mandatory D2 one-night CHECK_IN rule against the stored `night_rate_snapshot` (wrong-stage/partial → 422), booking-row locks for payment/check-in concurrency (PG test: one of two racing full payments wins)
- [x] **179 tests passing, 10 skipped** (SQLite; PG payment/concurrency tests skip locally, enforced in CI); Alembic upgrade/downgrade clean on SQLite; PostgreSQL tests run in CI with fail-if-skip guard
- **Exit criteria met (backend):** payments recorded and reversed (ADMIN), overpayment gated, check-in enforced, GET read-only, RBAC/audit. No checkout settlement, PDFs, messages, frontend or reports.
- Next: Phase 4.3 (settlement, checkout and receipts) — do not start automatically.

- Folio engine (charges, discounts with limits, reversals), payments (advance/check-in/checkout, cash/UPI/card), transactions
- Tax computation from settings; ReportLab PDF receipts (payment + final)
- **Exit criteria:** end-to-end checkout settlement with reconcile tests; financial immutability tests pass.

## Phase 5 — Guest portal
- Token generation/hashing, `/guest/{token}` views, 24h post-checkout expiry, receipt download
- Rate limiting, no-store cache headers, expiry UX
- **Exit criteria:** security checklist (no PII leakage, token can't be guessed/reconstructed) reviewed.

## Phase 6 — Reports, audit viewer, public website
- Admin financial/occupancy reports; audit-log viewer
- Public marketing site (Home/About/Rooms/Gallery/Facilities/Restaurant/Attractions/Contact, Maps embed, tel: links) — **no booking functionality**
- **Exit criteria:** receptionists cannot reach report routes; website has zero booking controls.

## Phase 7 — Messaging (mock → real)
- Message abstraction + mock provider wired (welcome link, checkout, receipt) with message_log — starts as soon as Phase 3 bookings exist
- (Later, same phase) Real WhatsApp Cloud API provider + env credentials + template approval
- **Exit criteria:** all message flows exercised end-to-end against mock; real provider behind feature flag.

## Phase 8 — Hardening & go-live
- Security review (auth, RBAC, token handling, CSRF, rate limits), backup/restore drill, logging/alerting basics
- UAT with hotel staff (booking → checkout → receipt → portal), training notes
- **Exit criteria:** backup tested; UAT sign-off; go-live checklist complete.

## Risk register
| Risk | Impact | Mitigation |
|---|---|---|
| Double-booking race condition | High | Transaction + FOR UPDATE + exclusion constraint + concurrency tests |
| Financial data loss/corruption | High | Append-only ledger, transactions, tested backups |
| Guest token leak (WhatsApp forwards, logs) | Medium | Hashed storage, 24h expiry, revocation, no token logging |
| GST misconfiguration | Medium | Versioned settings, no defaults, admin-only, audit trail |
| Scope creep to "online booking" | Medium | Hard constraint in SRS; website is advertisement-only |
| Overengineering | Medium | Modular monolith; no queues/caches/microservices |
| PII exposure (ID proofs) | Medium | Minimise collection; redact in logs; consider encryption at rest |

## Dependencies between phases
Phase 1 → 2 → 3 → 4 are strictly sequential (each builds on prior models). Phase 5 depends on 3+4. Phase 6 website part is independent and can parallelise with 3–5. Phase 7 mock can start with Phase 3; real WhatsApp is last.

## Suggested sequencing
1. Review docs (Phase 0 exit) — **immediate next step**
2. Phase 1 foundation
3. Phases 2–4 core system (the money path gets the most testing)
4. Phase 5 guest portal, Phase 6 website/reports
5. Phase 7 messaging, Phase 8 hardening/go-live
