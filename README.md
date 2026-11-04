# Shree Shyam Home Stay — Management System

A lightweight, secure, and maintainable management system for a small homestay with **6 rooms**.

> **Status:** Documentation / Architecture phase. **No application code has been written yet.**
> Do not begin Phase 1 implementation until the documents in `docs/` are reviewed and approved.

---

## 1. What this system is

| | |
|---|---|
| **Property** | Shree Shyam Home Stay |
| **Size** | 6 rooms |
| **Room categories** | Normal, Deluxe, Super Deluxe (distribution across 6 rooms is **configurable — pending decision**, see `docs/SRS.md`) |
| **Bookings** | Telephone / walk-in only. **No online booking.** |
| **Users** | Two roles only: `ADMIN`, `RECEPTIONIST` |
| **Guest access** | Per-booking, cryptographically secure token link; expires 24 hours after checkout |

This is **not** an enterprise PMS. No microservices, no overengineering. A modular monolith backend + a separate Next.js frontend.

## 2. Technology stack (fixed)

| Layer | Technology |
|---|---|
| Frontend | Next.js (TypeScript), Tailwind CSS, shadcn/ui |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Database | PostgreSQL |
| Migrations | Alembic |
| Auth | Secure server-side session cookies (not JWT in localStorage) |
| PDF | ReportLab |
| Messaging | WhatsApp Cloud API abstraction with a development mock provider (real integration = later phase) |
| Testing | pytest (backend), Vitest/Playwright as needed (frontend) |
| Logging | Structured (JSON) logging |
| VCS | Git |

## 3. Repository layout (planned)

```
.
├── README.md
├── docs/
│   ├── SRS.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE_DESIGN.md
│   ├── RBAC.md
│   ├── BOOKING_WORKFLOW.md
│   ├── BILLING_WORKFLOW.md
│   ├── GUEST_PORTAL.md
│   ├── API_DESIGN.md
│   └── DEVELOPMENT_ROADMAP.md
├── backend/            # FastAPI modular monolith (Phase 1+)
│   ├── app/
│   └── alembic/
├── frontend/           # Next.js app (later phase)
└── docker-compose.yml  # Postgres + backend + frontend for local dev
```

## 4. Documentation index

| Document | Purpose |
|---|---|
| `docs/SRS.md` | Functional & non-functional requirements, assumptions, open decisions |
| `docs/ARCHITECTURE.md` | System architecture, module boundaries, security & data principles |
| `docs/DATABASE_DESIGN.md` | Entities, relationships, constraints, indexes, migrations |
| `docs/RBAC.md` | Role permissions, permission checks, prohibited actions |
| `docs/BOOKING_WORKFLOW.md` | Booking lifecycle, state machine, overlap prevention |
| `docs/BILLING_WORKFLOW.md` | Folio, payments, discounts, taxes, checkout settlement |
| `docs/GUEST_PORTAL.md` | Token security, expiry, guest-visible data, privacy boundaries |
| `docs/API_DESIGN.md` | REST API conventions, endpoints, auth, errors, versioning |
| `docs/DEVELOPMENT_ROADMAP.md` | Phased delivery plan with exit criteria and risks |

**Read in that order.** `SRS.md` is the source of truth for *what*; `ARCHITECTURE.md` for *how*.

## 5. What is deliberately NOT built

- ❌ Online booking / payment gateway
- ❌ Microservices, queues, message brokers, event streaming
- ❌ Multi-property / multi-tenant support
- ❌ Hardcoded room prices, GST rates, phone numbers, addresses (all configurable)
- ❌ Silent deletion/overwrite of financial records

## 6. Unknown values (never invent these)

The following are **pending business decisions** and must remain configurable in the system — see `docs/SRS.md §10`:

- Room count per category (of the 6 rooms) and nightly price per category
- Hotel address, phone, email, Google Maps link
- GST registration status, GST number, GST rates, tax-inclusive/exclusive behaviour
- Check-in / check-out times, cancellation & no-show policy
- Discount authority limits
- Restaurant menu, photos, contact; cab company details and external website
- Wi-Fi SSID/password, tourist information content

## 7. Quick start (once Phase 1 begins)

```bash
# 1. Start Postgres
docker compose up -d db

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env        # fill DATABASE_URL, SESSION_SECRET, etc. — never commit .env
alembic upgrade head
uvicorn app.main:app --reload

# 3. Frontend (later phase)
cd frontend && npm install && npm run dev
```

> ⚠️ **Never commit credentials.** All secrets come from environment variables (`.env` files are gitignored; only `.env.example` with placeholder values is committed).

## 8. Current phase

**Phase 0 — Documentation & design.** Next step is stakeholder review of `docs/`, then Phase 1 (foundation) per `docs/DEVELOPMENT_ROADMAP.md`.
