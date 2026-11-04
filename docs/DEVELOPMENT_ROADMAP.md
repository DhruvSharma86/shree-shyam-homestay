# Development Roadmap — Shree Shyam Home Stay

> **Current status: Phase 1.1 (backend foundation) — ✅ complete.**
> Phase 0 docs reviewed; Phase 1.1 delivered (config, DB infra, logging, error envelope, health endpoints, pytest harness, Alembic, docker-compose Postgres). Next: Phase 1.2 — users/sessions models, session auth, RBAC, audit logging for auth events, first migration.

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

### Phase 1.2 — Auth, users, RBAC (next)
- `users`, `sessions` models + first Alembic migration; env-seeded initial ADMIN bootstrap
- Session-cookie auth (login/logout/me), idle + absolute timeouts, password hashing (argon2id)
- RBAC permission definitions + `require_permission` dependency (default-deny)
- Audit logging for auth events; auth API tests
- Frontend skeleton (Next.js + Tailwind + shadcn/ui) if scheduled here
- **Exit criteria:** admin can log in; RBAC denies by default; tests green; migrations run clean from scratch.

## Phase 2 — Hotel configuration & users management
- `hotel_info`, `room_types`, `rooms`, `room_rates` (versioned), `tax_settings` (versioned, default NONE), `restaurant_info`, `cab_info`
- Admin UI: user management, room/type/price config, hotel info, content config
- Audit logs for all admin config changes
- **Exit criteria:** ADMIN can configure everything without code changes/DB edits; receptionist blocked from all config routes.

## Phase 3 — Guests & bookings
- Guest registration + phone lookup; booking CRUD, availability engine, overlap prevention (app + DB), rate snapshots
- Booking lifecycle (confirm/check-in/checkout/cancel/no-show), booking history/search
- **Exit criteria:** full booking lifecycle works; concurrency test proves no double-booking.

## Phase 4 — Billing, payments, receipts
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
