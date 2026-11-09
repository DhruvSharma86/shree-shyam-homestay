# Local Setup — Shree Shyam Home Stay (Windows, development)

Run the full stack locally before choosing an online host.

- Frontend: http://localhost:3000 (`next dev`)
- Backend: http://localhost:8000 (`uvicorn`, docs at `/docs`)
- Database: PostgreSQL on `localhost:5432`

Nothing here is production-ready — this is development/staging validation only.

## 1. Prerequisites (verified 2026-11-10 on this machine)

| Tool | Required | Detected |
|---|---|---|
| Python 3.11 | ≥3.11 | 3.11.15 ✅ |
| uv | `uv.lock`-based install | 0.12.0 ✅ |
| Node.js | ≥20 (engines pin) | 26.13.0 ✅ (≥20; upper bound removed in S2 review) |
| npm | lockfile present | 11.20.0 ✅ |
| PostgreSQL | 16-class server, `btree_gist` | Service `postgresql-x64-18` Running, `pg_isready` accepting on :5432 ✅ |
| Docker | optional (not required; no compose file in scope) | not installed (not needed) |
| Disk | — | 599 GB free on C: ✅ |

Ports 3000 and 8000 are free. Install nothing via this guide toward production; use the commands below.

## 2. Database setup

PostgreSQL is **required for full verification**: the booking exclusion constraint
(`btree_gist`), immutability triggers (`folio_entries`/`payments`/`receipts`), and
`FOR UPDATE` locking do not degrade silently — the app tests them on PG in CI.
SQLite (`DATABASE_URL=sqlite:///./dev.db`) is an explicitly documented fallback for
limited UI/API preview only (PG-only constraints are skipped there).

1. Confirm PostgreSQL accepts connections:
   ```powershell
   pg_isready -h localhost -p 5432
   ```
2. Create a local database and role (run as a superuser, e.g. `postgres`):
   ```sql
   CREATE ROLE hotel_app LOGIN PASSWORD '<choose-local-password>'
     WITH CREATEDB NOSUPERUSER;
   CREATE DATABASE shree_shyam OWNER hotel_app;
   ```
   Replace `<choose-local-password>` with your own local password. `btree_gist` is
   created by the migration itself (`CREATE EXTENSION IF NOT EXISTS btree_gist`) —
   the DB owner must be allowed to create extensions (true for the database owner).
3. Never overwrite or delete an existing database without identifying it first
   (`psql -l`). This guide assumes a **fresh, empty** `shree_shyam`.

## 3. Environment setup

Neither `backend/.env` nor `frontend/.env.local` exists yet — create them from the templates.
Never overwrite an existing `.env` (inspect it first); never commit `.env` (gitignored).

**Backend** (`backend/.env`, copy `backend/.env.example`):
```ini
APP_ENV=development
APP_DEBUG=false
DATABASE_URL=postgresql+psycopg://hotel_app:<local-password>@localhost:5432/shree_shyam
SESSION_SECRET=local-dev-secret-change-me-0123456789
CORS_ORIGINS=http://localhost:3000
TRUSTED_PROXY_ENABLED=false
INITIAL_ADMIN_USERNAME=
INITIAL_ADMIN_PASSWORD=
INITIAL_ADMIN_FULL_NAME=Hotel Administrator
```
(All other keys take code defaults. `SESSION_SECRET` must be strong in any
non-local deployment; local dev may use the placeholder above.)

**Frontend** (`frontend/.env.local`, copy `frontend/.env.example`):
```ini
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_V1=/api/v1
```

## 4. Backend installation

```powershell
cd backend
uv sync --frozen --extra dev
```
Locked install from `uv.lock` (52 packages). Runtime-only install (no dev tools):
`uv sync --frozen --no-dev`.

## 5. Migrations

```powershell
cd backend
alembic upgrade head
```
Exactly one head expected: `e2f3a4b5c6d7`. Verify:
```powershell
alembic current
```
Fresh-DB only. Never run against a database you have not identified; check
`SELECT count(*) FROM alembic_version;` first if unsure. The app never migrates
on startup (no `create_all` in `app/`).

## 6. ADMIN provisioning (first local account)

The mechanism exists and is safe — no SQL improvisation:

```powershell
cd backend
$env:INITIAL_ADMIN_USERNAME = "<choose-username>"
$env:INITIAL_ADMIN_PASSWORD = "<choose-password-at-least-10-characters>"
uv run --frozen python -m app.auth.bootstrap
Remove-Item Env:\INITIAL_ADMIN_USERNAME, Env:\INITIAL_ADMIN_PASSWORD
```
Properties (verified in `app/auth/bootstrap.py`): refuses if **any** user exists
(one-time, no overwrite), requires username + ≥10-char password via environment only
(never CLI args), Argon2id-hashed, audit-logged as `ADMIN_BOOTSTRAPPED`, never
printed. The account cannot be created twice; afterwards, additional staff are
created via the ADMIN Users UI (never direct SQL).

## 7. Startup

Start the services in separate terminals (or via the helper, which starts only
one service at a time and never migrates unless asked):

```powershell
# Terminal 1 — backend (from repo root)
.\ops\start-local.ps1 -Service backend
# adds `alembic upgrade head` before starting only with -Migrate

# Terminal 2 — frontend
.\ops\start-local.ps1 -Service frontend
```
Manual equivalents:
```powershell
cd backend; $env:DATABASE_URL="postgresql+psycopg://hotel_app:<pwd>@localhost:5432/shree_shyam"
cd backend; uv run --frozen python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend; npm ci; npm run dev
```
`NEXT_PUBLIC_*` are **build-time** in production but read at `next dev` start locally —
restart the frontend after editing them. Backend settings reload on restart
(`get_settings()` is process-cached; `python -m uvicorn --reload` picks up code, not env).

## 8. Local URLs

| Surface | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/api/v1 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health · `/health/live` · `/health/ready` |

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `pg_isready` refuses | Start the `postgresql-x64-18` (or equivalent) service in Services. |
| Auth to PG hangs | Password auth: supply `PGPASSWORD` (env) or set `PGPASSWORD` for `psql`; never pass it on the command line in scripts. |
| `alembic` refuses / wrong head | Ensure `DATABASE_URL` points at the intended DB; `alembic current` must show `e2f3a4b5c6d7`. |
| Login 401 after boot | Bootstrap env unset or wrong host (`DATABASE_URL` mismatch) — re-check `.env` (never print it). |
| Frontend shows errors but backend works | `NEXT_PUBLIC_API_BASE_URL` unset at `next dev` start — fix `.env.local` and restart frontend. |
| Port 3000/8000 busy | `Get-NetTCPConnection -LocalPort 3000,8000` to find the owner; stop that process. |
| Node EBADENGINE warnings | `engines: >=20` now includes Node 26 — warnings from an older checkout disappear after `npm ci`. |

## 10. Shutdown

`Ctrl+C` in each terminal. The database persists (PostgreSQL). Do not delete
`backend/.venv`, `node_modules`, or `.env` unless you intend a full local reset.

## 11. Data protection warnings

- `.env` files, passwords, dumps (`ops/*.dump`), and `*.db` are **gitignored** —
  never commit them. CI rejects tracked DB artifacts.
- `ops/backup-postgres.*` dumps contain guest + financial data: restrict ACLs,
  keep off-host encrypted, 30-day retention.
- Never directly edit/delete rows in `folio_entries`, `payments`, or `receipts`
  (immutable; corrections are reversal rows via the API/UI).
- Portal tokens are hash-only, but full URLs (with tokens) still appear in
  browser history — keep `uvicorn.access` at WARNING.
