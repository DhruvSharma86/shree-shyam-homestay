# Architecture — Shree Shyam Home Stay Management System

## 1. Architecture style
**Modular monolith** (backend) + **separate frontend** app. One deployable backend service, internally organized into domain modules with strict dependency direction. No microservices, no event bus, no queues — unnecessary at 6 rooms.

## 2. System context

```
┌─────────────────┐        ┌──────────────────────┐        ┌──────────────┐
│  Staff browser  │ HTTPS  │  Next.js frontend    │ HTTPS  │  Guest phone │
│ (admin/recept.) │───────▶│  (TypeScript,        │───────▶│  (guest      │
└─────────────────┘        │   Tailwind, shadcn)  │        │   portal)    │
        ▲                  └──────────┬───────────┘        └──────▲───────┘
        │ session cookie              │ fetch /api (cookies)      │ token link
        │                             ▼                           │ (no login)
        │                  ┌──────────────────────┐               │
        └──────────────────│ FastAPI backend      │───────────────┘
                           │ (modular monolith)   │
                           └──────────┬───────────┘
                                      │ SQL
                           ┌──────────▼───────────┐
                           │ PostgreSQL           │
                           └──────────────────────┘

External (later phases): WhatsApp Cloud API (via messaging abstraction), PDF stored on disk/S3 (TBD), Google Maps (frontend embed).
```

## 3. Design principles
1. **Simplicity first.** Prefer the boring solution. No caches, queues, or service meshes until a real need appears.
2. **Money safety.** All financial writes occur in a single DB transaction; posted entries are immutable (reversal entries for corrections).
3. **Fail closed.** RBAC checks default-deny; guest endpoints default-deny unless a valid, unexpired token is presented.
4. **Config over code.** Prices, taxes, contacts, content live in DB/env — never hardcoded.
5. **Audit everything important.** Admin actions, discounts, financial corrections → append-only audit log.
6. **Secure by default.** Session cookies (httpOnly/Secure/SameSite), CSRF on state-changing endpoints, hashed tokens/passwords, parameterized queries via SQLAlchemy.

## 4. Backend module structure (FastAPI)

```
backend/app/
├── main.py               # App factory, middleware, router registration
├── core/
│   ├── config.py         # Settings from env (pydantic-settings)
│   ├── db.py             # Engine/session factory
│   ├── logging.py        # Structured logging setup
│   ├── security.py       # Password hashing, token hashing, session helpers
│   └── errors.py         # API error envelope, exception handlers
├── auth/                 # Login/logout, session middleware, current_user dep
├── rbac/                 # Permission definitions + require_permission dependency
├── users/                # User management (admin)
├── hotel/                # Hotel info, rooms, categories, pricing
├── guests/               # Guest registration/lookup
├── bookings/             # Booking lifecycle, overlap checks
├── billing/              # Folio, charges, payments, discounts, taxes, receipts
├── reports/              # Admin financial/occupancy reports
├── audit/                # Audit log model + writer
├── messaging/
│   ├── base.py           # MessageProvider interface
│   ├── mock.py           # Dev mock (logs only)
│   └── whatsapp.py       # Phase 8 real provider (stub now)
├── guest_portal/         # Public token-scoped endpoints
└── public/               # Public website content endpoints (read-only)
```

**Module rules:**
- A module owns its models/schemas/service functions; cross-module access goes through service functions or repos, not direct table writes.
- Routes are thin: validate (Pydantic) → authorize (RBAC) → call service → serialize.
- Financial logic lives only in `billing` service functions; no other module writes financial tables.

## 5. Frontend structure (Next.js, later phase)

```
frontend/
├── src/app/
│   ├── (public)/         # Marketing site: home, about, rooms, gallery, ...
│   ├── (admin)/          # Staff dashboard (ADMIN + RECEPTIONIST, RBAC-gated nav)
│   └── guest/[token]/    # Guest portal (token in URL)
├── components/ui/        # shadcn/ui components
└── lib/api.ts            # Typed API client (cookies, credentials: 'include')
```

## 6. Data & persistence
- PostgreSQL via SQLAlchemy 2.0 (async or sync — sync is fine at this scale; decide in Phase 1 and keep consistent).
- Alembic for all schema changes. Every migration is reviewed; destructive migrations (column drops) need explicit approval.
- Enum columns for statuses/modes; money as `NUMERIC(12,2)` (never float).
- DB-enforced constraints for overlap prevention, uniqueness, and immutability triggers where practical (see `docs/DATABASE_DESIGN.md`).

## 7. Security architecture
| Concern | Approach |
|---|---|
| Staff auth | Server-side sessions; opaque session ID in httpOnly cookie; session table with expiry + last activity; idle timeout configurable |
| Guest auth | High-entropy token (≥256-bit), stored as hash; token bound to one booking |
| Passwords | argon2id (or bcrypt) via `passlib`/`pwdlib` |
| CSRF | Double-submit cookie or synchronizer token on cookie-authenticated mutating endpoints |
| RBAC | Permission-based (see `docs/RBAC.md`); enforced server-side on every endpoint |
| Rate limiting | On login, guest-token lookup, and messaging endpoints |
| Secrets | Environment variables only; `.env` gitignored; `.env.example` committed with placeholders |
| Audit | Append-only `audit_log` table; written in same transaction as the action where possible |
| Transport | HTTPS in production (reverse proxy / platform TLS); HSTS; secure cookie flags |

## 8. Messaging architecture
```
Service code ──▶ MessageProvider (interface) ──┬─▶ MockProvider (dev, logs)
                                               └─▶ WhatsAppProvider (Phase 8)
```
- Message types: `welcome_with_link`, `checkout_notification`, `receipt_delivery`.
- Outbox-style `message_log` table records attempts/status for visibility and retry (with manual retry by admin; no background worker until needed — or simple immediate send with logged result).
- No credentials in code; WhatsApp config via env vars in Phase 8.

## 9. PDF receipts
- Generated on demand by ReportLab from folio data; stored in object storage/disk (TBD) and/or regenerated on download.
- Receipt includes hotel info (DB-driven), folio lines, taxes (if configured), payments, balance, booking ref.
- Guest can download own receipt via token link; staff can download any receipt.

## 10. Testing & quality
- Backend: pytest — unit tests for billing/overlap logic, API tests for auth/RBAC/workflows.
- Frontend: Vitest + Testing Library; Playwright for critical flows (later).
- CI: lint (ruff), typecheck (mypy/pyright), tests, Alembic migration check.
- Financial invariants covered by dedicated tests (no partial writes, immutability, balance math).

## 11. Deployment (presumed simple)
- `docker-compose.yml`: `db` (Postgres), `backend` (uvicorn), `frontend` (Next.js standalone).
- Single small server or managed platform; backups of Postgres + receipt storage are mandatory from day one (TBD: schedule/tooling).
- No Kubernetes, no micro-frontends, no service mesh.

## 12. Open architectural decisions (TBD)
- AD-1: Sync vs async SQLAlchemy (recommend sync for simplicity; Phase 1).
- AD-2: Receipt storage location (local disk vs S3-compatible) — Phase 5.
- AD-3: Website content management (DB-backed vs static in repo) — Phase 7.
- AD-4: Session store (DB table vs Redis) — DB table is sufficient; revisit only if scale demands.
