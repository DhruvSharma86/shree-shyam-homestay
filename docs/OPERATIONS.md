# Operations — Shree Shyam Home Stay (Priority 6, 2026-11-09)

Operational documentation set. These runbooks assume the deployment topology
in §3 (modular monolith, TLS-terminating reverse proxy, single backend
process, PostgreSQL). Status labels: **PASS** (verified) / **PARTIAL**
(implemented, incompletely verified) / **NOT VERIFIED** (no suitable env) /
**BLOCKED** (external requirement) / **FAIL** (known defect).

## 1. Production Deployment Runbook

### 1.1 Required infrastructure
- Reverse proxy with TLS (one public HTTPS origin for the frontend; proxy `/api/*` to the backend and `/guest/*`, `/admin/*` to Next.js).
- One FastAPI process (single-replica rate limiting).
- PostgreSQL 16 (authoritative; SQLite is dev/test only and rejected in production).
- Hosted static Next.js (or `next start`) + a PostgreSQL client host with `pg_dump`/`pg_restore`.

### 1.2 Environment (placeholders only — see `backend/.env.example`, `frontend/.env.example`)

| Area | Production requirement |
|---|---|
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` (enforced — `true` fails startup) |
| `DATABASE_URL` | PostgreSQL URL with a real password (placeholder `change_me` and SQLite are rejected at startup) |
| `SESSION_SECRET` | Strong random value (dev default is rejected at startup) |
| `CORS_ORIGINS` | Real frontend origin(s), comma-separated; `*` is rejected at startup |
| `TRUSTED_PROXY_ENABLED` | `true` **only** when the proxy strips/overwrites `X-Forwarded-For`; else `false` |
| `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_API_V1` | Public API origin (frontend build-time; restart/rebuild after change) |

### 1.3 Migration sequence (order matters)
1. Provision PostgreSQL (exit 0 on `pg_isready`).
2. `cd backend && alembic upgrade head` — expect single head `e2f3a4b5c6d7`, exit 0. **If this fails, do not start the app** (see §4 incident runbook).
3. `alembic current` must print `e2f3a4b5c6d7 (head)`.
4. Never run `create_all` / hand DDL in production; migrations are the only schema path. The app never runs migrations on startup (verified: no `create_all` in `app/`).

### 1.4 Backend / frontend startup
- Backend: `uvicorn app.main:app --host 127.0.0.1 --port 8000` (bind loopback; proxy-terminated TLS). Production guards in `app/core/config.py` fail fast on insecure settings. Render-ready alternative: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (see `backend/Procfile`, `render.yaml`).
- Frontend: `npm run build && npm run start` (or static export of the built output); ensure `NEXT_PUBLIC_API_BASE_URL` points at the public API origin.
- Dependencies: backend is locked in `backend/uv.lock` (`uv sync --frozen`); frontend uses `package-lock.json` (`npm ci`).

### 1.5 Reverse-proxy requirements
- TLS everywhere (frontend + API + guest links); HTTP→HTTPS redirect.
- `Secure` session cookies follow automatically when `APP_ENV != development` (verify `Set-Cookie` on login in staging).
- Request-size limits: receipt PDFs are DB bytes (tens of KB); set a modest proxy body limit (e.g. 10 MB) and a 60s proxy timeout (app timeout is 15s).
- Keep `uvicorn.access` at WARNING (see §6); do not enable full-URL access logging.
- **Do not run multiple backend replicas**: guest-portal + login rate limiting is in-process per process.

### 1.6 Health-check verification
- `GET /health/live` → `200 {"status":"ok"}` (liveness, no DB).
- `GET /health/ready` → `200 {"status":"ready","database":"ok"}` when PostgreSQL answers; `503` when it does not. Bodies contain no secrets.
- If PostgreSQL is down, readiness is 503 and the proxy must stop routing (or show the maintenance page).

### 1.7 First ADMIN provisioning
- Set `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` / `INITIAL_ADMIN_FULL_NAME` in the **server environment only** (never in git), start once (bootstrap creates the account only when `users` is empty), then unset and restart.
- **No default production admin password exists** — the stack refuses to start with unset bootstrap values in production (verify via the env allowlist at deploy).

### 1.8 Post-deployment smoke checks
1. `GET /health/live` and `/health/ready` (200s).
2. Log in as the new ADMIN; change password (all other sessions are revoked).
3. Create a room rate; create guest + booking (PHONE); record CHECK_IN payment; check in; copy the one-time link.
4. Open the guest link anonymously; confirm overview/menu/cab/wifi load with `cache-control: no-store, private`.
5. Confirm `https://…/guest/…` HTML has no `Cache-Control: public`.

## 2. Backup and Restore Runbook

### 2.1 What to back up
The **entire PostgreSQL cluster** (or at least the `shree_shyam` database): `users`, `bookings`, `folio_entries`, `payments`, `receipts` (immutable PDFs), `guest_portal_tokens` (hashes only), `audit_log`, guests, hotel config, tourism content. Guest portal tokens are hash-only, so a dump does not leak usable links (still treat dumps as confidential).

### 2.2 Frequency for a 6-room homestay
- **Daily** logical dump (after the evening checkouts), retention 30 days.
- **Pre-change dumps** before any migration or bulk edit.
- **Weekly** off-host copy (encrypted USB / private bucket, operator-account ACLs only). Six rooms = small DB; daily + weekly off-host is proportionate. Monthly full restore drill is recommended (see checklist).

### 2.3 Create a backup (example — placeholders, never real passwords)
Secrets live in `PGPASSWORD` (environment), never on the command line or in scripts. The helper scripts enforce this:

```powershell
$env:PGHOST="localhost"; $env:PGPORT="5432"; $env:PGUSER="hotel_app"; $env:PGPASSWORD="<from-secret-store>"; $env:PGDATABASE="shree_shyam"
.\ops\backup-postgres.ps1 -DbName "shree_shyam" -OutputDir "C:\backups\shree-shyam"
```
```bash
export PGHOST=localhost PGPORT=5432 PGUSER=hotel_app PGPASSWORD='<from-secret-store>' PGDATABASE=shree_shyam
./ops/backup-postgres.sh shree_shyam ./backups 30
```
Both check for `pg_dump`, refuse to run without `PGPASSWORD`, verify a non-empty file, prune beyond retention, and print the path (never the password).

### 2.4 Restore into a separate test database (unverified here — no live PostgreSQL was available)
1. Copy the dump off-host decrypt to the operator station.
2. Restore into a **differently named** database (the scripts refuse `shree_shyam` without `--allow-production`/`-AllowProduction`):
```powershell
.\ops\restore-postgres.ps1 -BackupFile "C:\backups\shree-shyam\shree_shyam_backup_20261109_210000.dump" -TargetDb "shree_shyam_restore_test"
```
3. Verify before trusting it:
   - `SELECT count(*) FROM bookings; SELECT count(*) FROM receipts;` (non-zero, matches pre-backup numbers).
   - `ALEMBIC` current == head; audit log intact.
   - `GET /health/ready` 200 against the restored DB.
4. **Do not run a restore against production without a verified dump in hand** — a failed restore leaves no system.

### 2.5 Protect backup files
- Dumps contain guest PII + financial records: NTFS/Unix operator-only ACLs (`chmod 600`), encrypted off-host storage, never emailed unencrypted, never committed to git.
- Retain 30 days on-host; longer only encrypted off-host. Delete expired copies.
- A failed dump (non-zero exit / empty file) is a failed backup: fix `pg_dump`/permissions and re-run; alert the operator.

### 2.6 Primary database lost
1. Restore the newest verified dump into a fresh PostgreSQL.
2. `alembic upgrade head` (no-op if restored dump is current — confirm `alembic current`).
3. Point `DATABASE_URL` at the restored instance; verify `/health/ready`.
4. Data since the last dump is unrecoverable — use `audit_log` + folio/receipt records to reconcile the gap with the operator.

## 3. Booking data (survival notes)
No booking/guest financial data is reconstructible from dumps after the fact — the dump is the only recovery. Receipts are immutable PostgreSQL bytes (no filesystem copy to lose). Portal tokens are hash-only; a dump does not resurrect pre-expiry links.

## 4. Incident Response Runbook

| Symptom | First actions |
|---|---|
| App unavailable | `GET /health/live` (process up?). If live-200, the process is up: check `/health/ready` + proxy logs. Restart the single process (`uvicorn`); do not run migrations as a fix. |
| Database unavailable | `/health/ready` must be 503 (no fake healthy). Check PG logs/disc; restore from newest dump; `alembic upgrade head` only if the dump predates head (verify `alembic current`). |
| Failed migration | Do not start the app. Read the alembic output; if a partial migration left the schema mid-way, Restore-from-dump then re-run `alembic upgrade head` once. Never edit `alembic_version` by hand. |
| Suspected portal token exposure | Classify scope: bookmarked/shared link ≠ DB hash leak. Rotate the affected booking(s) (ADMIN rotate — old links die immediately) and revoke where no guest needs access. Audit shows `PORTAL_TOKEN_ISSUED/REVOKED` (ids only). Host/DB exposure is out of scope for this runbook — escalate. |
| Suspected staff compromise | Deactivate the account (ADMIN users flow), `revoke_user_sessions` runs on deactivate/password-change; force password reset; review `AUTH_LOGIN_FAILED` + `audit_log` for the window. |
| Lost guest portal link | Receipt/concierge: ADMIN rotates the link (old one dies); receptionist asks an ADMIN (no self-recovery by design). |
| Incorrect payment entry | **Never edit/delete financial rows.** Reverse the payment (ADMIN-only linked reversal) and record the correct payment; the pair remains linked and auditable. |
| Receipt download failure | Check `/health/ready`, then the booking's `GET /bookings/{id}/receipt` (staff) vs portal `/receipt` (guest, 404-gated until checkout). Blob validation rejects JSON error bodies; re-check the portal link expiry (24h post-checkout). |
| Backup failure | Non-zero exit / empty file = no backup. Fix host/permissions, re-run, and keep the previous good dump until a new one verifies non-empty. |
| Suspected data corruption | Freeze writes; dump whatever exists; restore newest verified dump + reconcile via `audit_log`/folio; never hand-edit `folio_entries`/`payments`/`receipts` (immutable). |

## 5. Production Readiness Checklist

| Area | Status | Evidence |
|---|---|---|
| Single Alembic head, linear chain | **PASS** | `alembic heads` → `e2f3a4b5c6d7`; CI fresh-PG upgrade + schema verify green |
| Fresh-PG migration from zero | **PASS** (CI) | CI job `Alembic migrations + PostgreSQL integration tests` green on final commit |
| App never mutates schema at startup | **PASS** | No `create_all` in `app/`; startup has no migration call |
| Startup fails on insecure prod config | **PASS** (new) | `test_valid_production_config_passes` + 5 rejection tests |
| Liveness vs readiness split, no secrets | **PASS** | `test_health_*` (3 tests) |
| Database failure → unhealthy readiness | **PASS** | monkeypatched-DB 503 test |
| Backup/restore scripts present + guarded | **PASS** (scripts) | Guard behaviour exercised (missing file, prod-name refusal); real PG restore **NOT VERIFIED** (no live DB) |
| Schema-readiness probe (migration head in readiness) | **NOT VERIFIED** | Readiness is connectivity-only; runbook requires manual `alembic current` — deliberate (no flap risk) |
| Python lockfile | **PARTIAL** | `pyproject.toml` bounds only; no lockfile → `pip install` is not fully reproducible |
| Node lockfile | **PASS** | `package-lock.json` present; `npm audit` → 0 vulnerabilities |
| Backend vulnerability scanner | **NOT VERIFIED** | No `pip-audit` in toolchain; external DB unavailable offline |
| Backend dep vulnerabilities (real scan) | **NOT VERIFIED** | Same as above — npm audit 0 ≠ backend safe |
| Frontend dep vulnerabilities (npm audit) | **PASS** | `npm audit --omit=dev` → 0 vulnerabilities (2026-11-09) |
| Rate limiting multi-replica | **BLOCKED** if scaled | In-process single-process by design; scaling without shared storage is unsafe |
| Production deployment (public server) | **NOT VERIFIED** | No public infrastructure touched in this milestone |
| Guest portal token exposure from dumps | **PASS** | Hash-only at rest; dump leaks no usable links |

## 6. Logging & Monitoring
- Structured JSON logs (stdout) at `LOG_LEVEL`; `uvicorn.access` WARNING (never log full portal URLs with tokens). Exceptions are logged server-side with the generic error envelope returned (no stacks to clients).
- Monitoring is health-endpoint polling (live/ready) + backup exit codes. No tracing/monitoring platform — deliberately proportionate for 6 rooms.
