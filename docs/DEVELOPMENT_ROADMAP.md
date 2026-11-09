# Development Roadmap — Shree Shyam Home Stay

> **Current status: Phase 5.2 (Guest portal frontend & tourism content) — ✅ complete.**
> Phases 1–4 are closed and PostgreSQL-verified. Phase 5.1 delivered hashed bearer tokens; Phase 5.2 adds the mobile-first guest website (`/guest/[token]`), admin tourism content (`tour_packages`/`local_info`), and staff check-in link delivery (`/admin/bookings`) — backend tests green; frontend tests/build/lint/typecheck clean; PostgreSQL verified via GitHub Actions (see CI). No public marketing site, WhatsApp, online booking/payments or analytics in this milestone. Tax remains default NONE (no GST invented).

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

#### Phase 4.3 — Checkout settlement, final billing & PDF receipts ✅ (complete, 2026-11-09)
- [x] Git hygiene: `*.db`/`*.sqlite*` ignores + `Reject tracked database artifacts` CI guard; no database artifacts tracked (previous leaked scratch files already removed in `9576319`/`11d0a62` — history not rewritten)
- [x] `CHECKED_OUT` lifecycle (`checked_out_at/by`, migration `b9c0d1e2f3a4`), zero-balance-only settlement (positive/negative rejected), booking-row lock, atomic checkout + receipt + `CHECKOUT_COMPLETED`/`RECEIPT_ISSUED` audits, post-checkout service-layer immutability
- [x] Final receipt: `receipts` table (PostgreSQL bytes + SHA-256), ReportLab `INR` formatting, `GET /receipt` + authorized `GET /receipt/download` (`no-store`), historical reproducibility (identical bytes, later config edits don't change issued receipt)
- [x] Tax still default NONE — no GST/percentages invented; receipts show configured tax state without calculating liability (needs a separate approval)
- [x] **189 tests passing, 12 skipped** (SQLite; 4 PG checkout/receipt tests skip locally, enforced in CI); Alembic upgrade/downgrade clean on SQLite; PostgreSQL tests run in CI with fail-if-skip guard
- **Exit criteria met (backend):** settled checkout with immutable receipts, ledger-derived zero balance, auditable downloads, hardened artifact hygiene. No NO_SHOW, reports, messages, portal or frontend.
- Next: Phase 4.4 (financial reporting) — do not start automatically.

#### Phase 4.4 — Financial reporting & reconciliation ✅ (complete, 2026-11-09)
- [x] Receipt preflight: explicit three-state tax wording (NONE vs configured-but-uncalculated vs calculated — never "zero liability"), PostgreSQL receipts immutability (`trg_receipts_immutable`, verified by UPDATE/DELETE rejection)
- [x] `app/reports/` read-only module: financial summary, daily collections (method×stage), payment-method breakdown, live outstanding/credits, period reconciliation, reversals detail, booking status counts, occupancy — all Decimal, no report tables, no guest PII; CSV exports reuse the same queries
- [x] **203 tests passing, 12 skipped** (SQLite; PG reports aggregation + receipts-immutability tests skip locally, enforced in CI); Alembic upgrade/downgrade clean on SQLite; PostgreSQL tests run in CI with fail-if-skip guard
- **Exit criteria met (backend):** reconciliation traceable to source records, outstanding credits distinguished, occupancy defined and timezone-unshifted (UTC, documented), read-only guarantees tested. No dashboards, messaging, portal or frontend.
- Next: Phase 5 (guest portal) — do not start automatically.

### Phase 5.1 — Guest portal foundation ✅ (complete, 2026-11-09)
- [x] 256-bit bearer tokens (URL-safe) issued transactionally at check-in, **SHA-256 hash only** in `guest_portal_tokens` (partial unique: one active per booking); raw token shown once in the check-in response (and on staff rotate), never logged/audited/persisted again
- [x] Lifecycle-derived expiry: open before checkout, expires exactly 24h after `checked_out_at` (strict), cancelled bookings rejected, revocations permanent; ADMIN revoke/rotate/status under `portal.tokens.manage` (audit without raws)
- [x] Unauthenticated read-only portal APIs (`/api/v1/guest-portal/{token}/overview|menu|cab|wifi|receipt|receipt/download`), cache `no-store`, generic 404 (no oracle), in-process brute-force limiter, guest-safe fields (no ids/money/PII), FINAL receipt bytes reused from `receipts`
- [x] **219 tests passing, 16 skipped** (SQLite; PG portal token/isolation/round-trip tests skip locally, enforced in CI); Alembic upgrade/downgrade clean on SQLite; PostgreSQL tests run in CI with fail-if-skip guard
- **Exit criteria met (backend):** hashed-token lifecycle, strict isolation, guest-facing content without internals, auditability. No public marketing site, WhatsApp, online booking, online payments, or frontend portal.
- Next: Phase 5.2 (portal frontend + tourism content) — do not start automatically.

- Folio engine (charges, discounts with limits, reversals), payments (advance/check-in/checkout, cash/UPI/card), transactions
- Tax computation from settings; ReportLab PDF receipts (payment + final)
- **Exit criteria:** end-to-end checkout settlement with reconcile tests; financial immutability tests pass.

## Phase 5 — Guest portal (5.1 foundation ✅, 5.2 frontend + content ✅)
#### Phase 5.1 — Guest portal foundation ✅ (complete, 2026-11-09)
- [x] Secure bearer tokens (256-bit, SHA-256 hash-only, one active per booking), issued transactionally at check-in, raw shown exactly once, ADMIN revoke/rotate/status
- [x] Lifecycle-derived expiry (open pre-checkout, expires exactly 24h after checkout; cancelled/revoked dead), generic 404 (no validity oracle), brute-force limiter
- [x] Read-only portal APIs (`overview/menu/cab/wifi/receipt`) under `/api/v1/guest-portal/{token}/...`, no-store cache, guest-safe fields, FINAL receipt served from stored bytes
- [x] 219 tests passing, 16 skipped locally (PG portal tests enforced in CI); Alembic upgrade/downgrade clean; CI green
- Next: Phase 5.2 (portal frontend + tourism content) — do not start automatically.

#### Phase 5.2 — Guest portal frontend & tourism content ✅ (complete, 2026-11-09)
- [x] Mobile-first guest website (`/guest/[token]`, server/params wrapper + client list) with overview, menu (photos optional), cab call actions (`tel:`), Wi-Fi (copy action), tourism (active rows only), receipt download; no token storage, no staff session, loading/empty/error states
- [x] `tour_packages` + `local_info` admin content ( migration `e2f3a4b5c6d7`), ADMIN CRUD (`content.manage`, CSRF, audit) + guest `/tourism` endpoint (active only, no ids)
- [x] Staff bookings page (`/admin/bookings`): one-night payment + check-in delivery with one-time portal link (copy/dismiss, never persisted; rotation ADMIN-only)
- [x] **16 frontend tests pass**; `next build` clean (partial prerendered guest page, no static guest data); backend 228 passed locally with 16 new PG skips (enforced in CI)
- **Exit criteria met:** guest sees configured stay/menu/cab/tourism/wifi/receipt content with bearer-link security; ADMIN manages tourism content without code changes/DB edits.
- Next: Phase 5.3 (guest experience hardening & operational readiness) — do not start automatically.

#### Phase 5.3 Priority 1 — Receptionist booking access ✅ (complete, 2026-11-09)
- [x] Replaced the exclusive layout-level `RequireAdmin` with layered guards: `RequireStaff` (any authenticated session) wraps `/admin/*`; route-level `RequireAdmin` gates tourism; `AdminShell` navigation filters by role (bookings/dashboard for RECEPTIONIST, all sections for ADMIN)
- [x] Receptionist now reaches `/admin/bookings` (list, one-night payment, check-in, link display + copy) with rotate/revoke controls hidden client-side via `portal.tokens.manage` (backend still denies them independently)
- [x] Frontend tests: `RequireStaff` (loading/anon/roles), shell role navigation, receptionist check-in flow without admin controls, tourism blocked for receptionists, per-role bookings behavior
- **Exit criteria met:** RECEPTIONIST operational booking workflow reachable via UI; ADMIN permissions unchanged; backend RBAC authoritative.
- Next: continue Phase 5.3 (journey/security/mobile hardening) — do not start automatically.

#### Phase 5.3 Priority 2 — End-to-end guest journey audit ✅ (complete, 2026-11-09)
- [x] Journey audited end to end (guest record → booking → payments → check-in (+portal issuance) → portal content → checkout → immutable receipt → 24h expiry), covering all 19 steps (APIs, permissions, DB effects, audits, failure behavior)
- [x] Edge matrix tested: duplicate/concurrent check-in, cancelled bookings, insufficient/excess payments, repeated/admin-cancelled/revoked/rotated tokens, checkout guards (open/duplicate/credit), receipt 404→bytes→hash, expiry boundary at 24h, PG transaction consistency
- [x] Lost-response recovery: transactional commit holds (status + token); repeated check-in → `422`; raw token unrecoverable by design; ADMIN rotation is the documented recovery (receptionists see guidance, not controls); receipts hash-verified at every stage
- [x] Role matrix re-verified (ADMIN full; RECEPTIONIST permitted-subset; RECEPTIONIST blocked from rotation/revocation/tourism at both UI visibility and backend RBAC)
- [x] Frontend tests: 26 tests (receptionist recovery guidance + per-role flows); backend: 219 passed locally, full CI green
- Next: continue Phase 5.3 (security/mobile/error hardening) — do not start automatically.

#### Phase 5.3 Priority 3 — Guest portal security audit ✅ (complete, 2026-11-09)
- [x] Code-level audit (source + automated reproduction, not a penetration test). Confirmed: S1 High per-token limiter bypass → per-IP budget (60/300s) + bounded store; S2 Medium image Referer leak → `no-referrer`; S3 Medium missing headers → backend middleware + Next.js `headers()`; S4 Medium XFF spoofing → `trusted_proxy_enabled` opt-in; S5 Low unbounded store → bounded FIFO.
- [x] Verified safe (not vulnerabilities): entropy/hashing/constant-time compare, hash-only storage + partial unique index, strict 24h expiry, cross-booking isolation (no ID params), guest schemas (no PII/IDs/money), receipt immutability, session/CSRF/RBAC, no frontend token storage.
- [x] Tests: backend `test_guest_portal_security.py` (13) + frontend no-referrer + headers contract. Backend 241 passed/17 skipped; frontend 29/29; ruff/mypy/build clean; no migration.
- **Exit criteria met:** confirmed issues fixed with regression tests; residual risks documented in `docs/SECURITY.md`.
- Next: Phase 5.3 Priority 4 (mobile/error hardening) — do not start automatically.

#### Phase 5.3 Priority 4 — Guest portal mobile & accessibility ✅ (complete, 2026-11-09)
- [x] Responsive fixes: stay grid 1-col on phones (2-col sm+), cab rows stack on phones, `min-w-0`/`flex-1` + `break-words`/`break-all` on long names/passphrases/numbers/descriptions, menu thumbs `shrink-0` + graceful `onError` hide (no distortion, no broken-image icon)
- [x] Touch/keyboard: `min-h-11` (44px) buttons, `focus-visible` rings on Button + Call links, no hover-only controls, Cab Call is a real `tel:` anchor (link semantics) with contextual `aria-label`, Copy/Download buttons carry context labels
- [x] Semantics/screen readers: `<section aria-labelledby>` landmarks (region role) for all six sections, single `h1` + `h2`/`h3` hierarchy, menu alt = dish name, `role="status"` empty states, `role="alert"` invalid-link + receipt-failure, Wi-Fi copy success/failure announcements with insecure-context fallback, reception/tourism phone/email as `tel:`/`mailto:` links
- [x] Security preserved (Priority 3): `referrerPolicy="no-referrer"` kept (test), no token storage (test), no analytics/third-party scripts/deps, no-store/noindex headers untouched
- [x] Tests: frontend 34/34 (5 new: regions/headings/links, Call/Copy/Download names+keyboard, long-string hooks, receipt-failure feedback, invalid-link alert) + no-referrer + headers contract. No backend changes.
- **Exit criteria met:** guest portal usable at 320px–1440px per code-level classes (jsdom cannot measure pixels — see limitations); WCAG 2.2 AA practical coverage automated where jsdom allows.
- Next: Phase 5.3 Priority 5 (error/connectivity) — do not start automatically.

#### Phase 5.3 Priority 5 — Error, connectivity & recovery ✅ (complete, 2026-11-09)
- [x] Error classification (`lib/api.ts`): `network`/`timeout`/`server`/`invalid`/`auth`/`forbidden`/`validation`/`conflict`/`generic` — friendly messages only (no raw backend dumps); guest 404 stays generic (no oracle; 404/401/403/422 never retried)
- [x] Guest connectivity: overview network/timeout/5xx states distinct from invalid-link, each with a "Try again" (refetch, no full reload); per-section retry buttons; receipt 404 → informational Empty vs other kinds → error + retry; invalid links clear that token's cached queries; token-keyed query isolation preserved
- [x] Retry: bounded GET retries (≤2, exponential 1s/2s cap 5s) for network/timeout/5xx only; mutations (`retry: false`) never auto-retry — timeout/network guidance explains the outcome may be unknown and to inspect booking state first (payment/check-in/rotate/revoke)
- [x] Staff: bookings list/detail errors now surfaced with retry (were masked as empty/not-found); fixed stale portal admin URLs in `bookingsApi` (`/guest-portal/admin-rotate|admin-revoke/{id}`); 15s axios timeouts on both clients; receipt blob validated as `application/pdf`
- [x] Security preserved: no retry on 404 (no new oracle), no persisted guest/phone/token, no token logging, no-referrer/no-store headers intact
- [x] Tests: frontend **50/50** (+16: classifier/retry unit tests, network/timeout/503 states, 404 single-attempt, section retry, token isolation, payment unknown-outcome single attempt). Backend portal subset 16 passed (unchanged backend). No offline-device testing performed (mocked failures only).
- **Exit criteria met:** deliberate retry policy + classified recovery covered by automated tests; raw-token recovery model unchanged (ADMIN rotation).
- Next: Phase 5.3 Priority 6 (operational readiness) — do not start automatically.

#### Phase 5.3 Priority 6 — Operational readiness ✅ (complete, 2026-11-09)
- [x] Production guards (fail-fast): `APP_DEBUG`/dev `SESSION_SECRET`/SQLite-or-placeholder `DATABASE_URL`/wildcard-or-empty `CORS_ORIGINS` all rejected at startup in production; `CORS_ORIGINS` now env-driven (single-entry default preserves dev)
- [x] Health/monitoring: liveness (no DB) / readiness (DB connectivity → 503 on failure), no secrets in bodies (tests); schema-readiness deliberately manual (`alembic current` in runbook) to avoid probe flapping
- [x] Backup/restore: `ops/backup-postgres.{ps1,sh}` + `ops/restore-postgres.{ps1,sh}` (explicit targets, password-via-env only, prod-name refusal without `--allow-production`); restore procedure **NOT VERIFIED** (no live PostgreSQL for the restore step; CI fresh-PG migration is the verified path)
- [x] Docs: `docs/OPERATIONS.md` — deployment runbook (env, migration order, startup, proxy/TLS, ADMIN provisioning, smoke checks), backup/restore runbook, incident response (financial rows never edited/deleted), readiness checklist with PASS/PARTIAL/NOT VERIFIED/BLOCKED labels
- [x] Deps: npm `package-lock.json` + `npm audit` 0 vulns; backend `pyproject` bounds only (no lockfile — PARTIAL), no backend scanner in toolchain (NOT VERIFIED)
- [x] Config/health tests: 10 new (`test_operations.py`); full backend 251 passed/17 skipped; frontend 50/50; ruff/mypy/build clean
- **Exit criteria met:** operational posture documented + guarded; verdict — **ready for controlled staging deployment** (production requires prod env, PG restore drill, lockfile/scanner follow-ups — see checklist).
- Phase 5.3 (guest experience hardening & operational readiness) is **closed**. Next: Phase 6 (reports/audit viewer/public website) — do not start automatically.

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
