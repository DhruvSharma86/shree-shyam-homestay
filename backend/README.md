# Backend — Shree Shyam Home Stay Management System

FastAPI backend (modular monolith) for the Shree Shyam Home Stay Management
System. **Phase 1.1: foundation only** — configuration, database
infrastructure, structured logging, error envelope, health endpoints, and
the pytest harness. No business logic yet (no bookings, guests, payments,
auth, or frontend — those arrive in later phases).

## Stack

Python 3.11 · FastAPI · SQLAlchemy 2.0 (sync, per architecture decision
AD-1) · Pydantic v2 · pydantic-settings · psycopg v3 (PostgreSQL driver) ·
Alembic

## Layout

```
backend/
├── app/
│   ├── main.py            # App factory: settings → logging → app → routers
│   ├── core/
│   │   ├── config.py      # Env-based Settings (pydantic-settings)
│   │   ├── db.py          # Engine/session factory, Base, connection check
│   │   ├── logging_config.py  # JSON structured logging
│   │   └── errors.py      # Error envelope + exception handlers
│   └── api/
│       └── health.py      # GET /health, /health/live, /health/ready
├── alembic/               # Alembic env (URL from env) + version template
├── tests/                 # pytest suite (SQLite in-memory by default)
├── .env.example           # Template — copy to .env, never commit .env
└── pyproject.toml         # Dependencies + pytest/ruff config
```

## Setup

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS/Linux:         source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env        # fill in real values
```

## Run

```bash
# PostgreSQL required for real runs. In production the default DATABASE_URL
# points at the docker-compose `db` service.
uvicorn app.main:app --reload
```

## Health endpoints

Health endpoints deliberately live **outside** `/api/v1` so orchestrators and
monitors can probe them without knowing the API version.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Aggregate: service status + database connectivity |
| `GET /health/live` | Liveness: process is up (no dependencies checked) |
| `GET /health/ready` | Readiness: verifies database connectivity via `SELECT 1`; 503 when unreachable |

## Tests

```bash
pytest
```

Tests use in-memory SQLite by default (no live Postgres needed). To run
against PostgreSQL instead:

```bash
DATABASE_URL=postgresql+psycopg://hotel_app:change_me@localhost:5432/shree_shyam_test pytest
```

## Migrations (Alembic)

```bash
alembic upgrade head     # apply
alembic revision -m "describe change"   # generate (from Phase 1.2 onward)
alembic downgrade -1     # roll back one
```

The database URL always comes from the `DATABASE_URL` environment variable
(loaded via application settings). Phase 1.1 ships **no migrations and no
tables** — the first migration arrives with the users/sessions models in
Phase 1.2.

## Configuration

All settings are environment variables — see `.env.example`. Key variables:
`APP_ENV`, `APP_DEBUG`, `LOG_LEVEL`, `DATABASE_URL`, `SESSION_SECRET`,
`SESSION_*`, `INITIAL_ADMIN_*` (bootstrap, Phase 1.2).

> ⚠️ Never commit a real `.env` file. Only `.env.example` (placeholders) is
> version-controlled.

## Error format

Every API error follows this envelope (see `docs/API_DESIGN.md`):

```json
{ "error": { "code": "NOT_FOUND", "message": "Human-readable message." } }
```

Stack traces are never returned to clients; unexpected errors are logged
server-side and returned as `INTERNAL_ERROR`.

## Logging

Single-line JSON per record: timestamp, level, logger, message, optional
`context` dict (via `extra={"context": {...}}`), and exception details.
Never log secrets, passwords, or tokens.
