# Windows Desktop Application — Shree Shyam Home Stay

Phase 6.4. The hotel management system is available as a native Windows 11
x64 desktop application — install it, launch it from the Start Menu or the
Desktop shortcut, and use the existing system without a browser.

## Architecture

| Layer | Technology | Role |
|-------|------------|------|
| Desktop shell | Electron 41 | Window, single-instance lock, lifecycle of child processes |
| Frontend | Next.js 16 (standalone output) | The unmodified application UI, served locally |
| Backend | FastAPI + uvicorn, packaged with PyInstaller (onedir) | The existing API, bound to `127.0.0.1` only |
| Database | PostgreSQL 18 (existing local installation) | The existing `shree_shyam` database |
| Installer | electron-builder → NSIS | Assisted per-user installer (`Shree-Shyam-Home-Stay-Setup.exe`) |

Nothing is rebuilt. The desktop application launches **the same** FastAPI
backend and **the same** Next.js frontend the project already uses.

```
┌───────────────────────────────────────────────────────────┐
│ Electron main process (Shree Shyam Home Stay.exe)          │
│  1. resolve %APPDATA%\ShreeShyamHomeStay\config.env       │
│  2. ShreeShyamBackend.exe --check-migration (read-only)    │
│  3. spawn backend  → http://127.0.0.1:8000  (127.0.0.1)    │
│  4. spawn node.exe → http://127.0.0.1:3000  (standalone)   │
│  5. open window with the login page; lock navigation       │
└───────────────────────────────────────────────────────────┘
```

### Why this design

- **Electron**: the existing UI is React/Next.js — no UI rewrite, identical
  behaviour, native window, mature Windows installer tooling.
- **Next.js `output: "standalone"`**: official Next.js mechanism for
  self-contained production servers; traced `node_modules` (~22 MB) instead
  of shipping the full dependency tree.
- **PyInstaller onedir**: ships Python and every dependency so users never
  install Python. The backend binds **only** to `127.0.0.1`.
- **Bundled Node.js LTS (v26.13.1)**: the standalone server runs as a child
  process; no system Node.js installation is required.
- **No bundled PostgreSQL**: the first release targets the user's existing
  local PostgreSQL 18 installation and the existing `shree_shyam` database.

## Prerequisites

Development machine:

- Windows 11 x64 (target), Node.js ≥ 20 (developed on v26), Python 3.11 +
  [uv](https://docs.astral.sh/uv/) (the backend's `.venv` is created by `uv`).
- PostgreSQL 18 installed and running for the packaged app to use (the app
  checks this at launch).

End-user machine (the installed application):

- Windows 10/11 x64.
- PostgreSQL installed and running with the `shree_shyam` database and its
  existing schema. **PostgreSQL is NOT bundled and the installer never
  creates, drops or alters databases.**

## Configuration & secrets

The installed application reads its configuration exclusively from a
per-user file outside the installation directory:

```
%APPDATA%\ShreeShyamHomeStay\config.env
```

Example (values redacted):

```ini
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/shree_shyam
SESSION_SECRET=<generated automatically>
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Rules enforced by the desktop shell:

- **No `.env` is shipped in the installer.** No credentials are baked into
  binaries, the installer or the repository.
- If `config.env` is missing on first launch, a **first-run setup screen**
  asks for the database host/port/name/user/password. A strong
  `SESSION_SECRET` is generated on save.
- `SESSION_SECRET` is required; if it is absent from an existing
  `config.env`, a strong one is generated, persisted, and reused on
  subsequent launches (sessions survive restarts).
- If `SESSION_SECRET` is missing and cannot be persisted, the app refuses
  to start rather than fall back to a default secret.
- Configuration pointing at the disposable recovery databases
  (`sshs_drill_source*`, `sshs_drill_restore*`) is **rejected outright**.
- Secrets are never logged, never sent to the renderer, and never included
  in `config.env` written by the installer (it contains none).
- Logs: `%APPDATA%\ShreeShyamHomeStay\logs\{desktop,backend,frontend}.log`.
  Backend access logs are disabled so guest-portal bearer links never
  reach log files.

For development the unpackaged shell can fall back to `backend/.env` when
`config.env` is absent (a warning is logged). The packaged application
never uses `backend/.env`.

## Database migration behaviour

The application never migrates automatically.

On every launch the desktop shell runs:

```
ShreeShyamBackend.exe --check-migration
```

which (read-only) compares the database's `alembic_version` against the
migration head bundled into the executable, using a socket preflight and a
5-second connect timeout — an unreachable database fails fast (~3 s) instead
of hanging. Results are `up_to_date` / `upgrade_required` / `error`.

- `up_to_date` → the application starts normally.
- `upgrade_required` → the application **does not start** and shows the
  current vs expected revision plus backup-first upgrade instructions.
- `error` → the application shows a "cannot connect to PostgreSQL" screen.

If a future release includes schema changes, the supported upgrade path is:

1. Back up the database (see `docs/OPERATIONS.md` — `ops/backup-postgres.ps1`).
2. From a source checkout: `cd backend && alembic upgrade head`.
3. Start the desktop application.

The backend's established Alembic migration system remains the only schema
mechanism. Nothing is stamped, dropped, recreated or overwritten.

## Ports & processes

| Port | Process | Notes |
|------|---------|-------|
| 8000 | FastAPI (`ShreeShyamBackend.exe`) | `127.0.0.1` only |
| 3000 | Next.js standalone (bundled `node.exe`) | `127.0.0.1` via standalone server |

Behaviour when a port is occupied:

- The application checks ports before spawning anything.
- If port 8000 serves a **Shree Shyam backend** and a matching stale PID
  file exists, that orphan is terminated and startup continues.
- Anything else on ports 8000/3000 (e.g. the development servers) is
  **never terminated** — the application shows a clear "port in use" error
  and exits without changing anything.
- The single-instance lock (`requestSingleInstanceLock`) focuses the
  existing window on a second launch instead of duplicating processes.
- On close (window X / Alt-F4), the frontend and backend trees are killed
  (`taskkill /T /F`, hidden). PID files in `%APPDATA%\ShreeShyamHomeStay`
  are removed. Verified: no orphan processes after shutdown.

Startup logging goes to `logs\desktop.log`; the child process log goes to
`logs\backend.log` / `logs\frontend.log` (rotated above 1 MB).

## Security posture

- `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`.
- Renderers get no filesystem, process or secret access; the only IPC is a
  status-channel subscription and the first-run form submit (validated,
  TCP-probed server-side).
- Navigation is locked to the app origin; `window.open` is denied;
  `<webview>` attach is prevented; DevTools only with
  `SHREE_SHYAM_DESKTOP_DEV=1`.
- First-party shell pages (loading/setup/error) ship a restrictive CSP:
  `default-src 'none'` + inline `style`/`script` only on those local files.
- The window/backed calls are loopback-only; no other origin is allowed.
- Uninstall (`deleteAppDataOnUninstall: false`) never removes
  `%APPDATA%\ShreeShyamHomeStay` and never touches PostgreSQL or the
  `shree_shyam` database.

## Development commands

```powershell
cd desktop

npm install                 # one-time (Electron + electron-builder)
npm run dev                 # desktop development mode (uses backend/.env or config.env)
npm test                    # desktop unit tests (node:test)

# Build pipeline (from the repo root; see desktop/scripts/)
powershell -File desktop/scripts/build-backend.ps1    # PyInstaller onedir → desktop/.cache/staging/backend
node      desktop/scripts/prepare-frontend.mjs        # standalone → desktop/.cache/staging/frontend
powershell -File desktop/scripts/fetch-node-runtime.ps1   # official Node x64 → desktop/.cache/staging/node

# Full build
powershell -File desktop/scripts/build-installer.ps1  # frontend build → backend → staging → NSIS
npm run dist                                        # electron-builder only (staging must exist)
```

Expected output:

```
desktop\dist\Shree-Shyam-Home-Stay-Setup.exe
```

Sanity checks for the build machine:

```powershell
# migration probe (exit 0 = up to date)
backend\packaging\dist\ShreeShyamBackend\ShreeShyamBackend.exe --check-migration
```

## Installing, upgrading, uninstalling

- **Install**: run `Shree-Shyam-Home-Stay-Setup.exe`. Assisted (non-one-click)
  per-user install; adds a Desktop shortcut and a Start Menu entry.
- **Upgrade**: install the newer `Shree-Shyam-Home-Stay-Setup.exe` over the
  existing installation. Application binaries are replaced; `config.env`,
  logs and the PostgreSQL database are untouched.
- **Uninstall**: Settings → Apps → *Shree Shyam Home Stay*, or run
  `Uninstall Shree Shyam Home Stay.exe`. Removes the application only;
  `%APPDATA%\ShreeShyamHomeStay` and the database survive.

First run on a machine that never had this app:

1. Install PostgreSQL 18 and create/restore the `shree_shyam` database.
2. Launch the app → the first-run screen collects the connection details
   (host/port/database/user/password). A strong `SESSION_SECRET` is
   generated.
3. To create the first administrator on a fresh database (existing
   production systems already have one): from a source checkout,
   `cd backend`, set `INITIAL_ADMIN_USERNAME`/`INITIAL_ADMIN_PASSWORD`,
   run `alembic upgrade head` and `python -m app.auth.bootstrap`. The
   desktop app itself never bootstraps or resets credentials.

## Troubleshooting

| Symptom | Likely cause / action |
|---------|----------------------|
| "Port 8000 is in use" / "Port 3000 is in use" | Another app holds the port. Close it or free the port. Desktop never kills unknown processes. |
| "Cannot connect to PostgreSQL" on every launch | PostgreSQL service stopped, or `DATABASE_URL` in `config.env` wrong. Start the `postgresql-x64-18` service / fix the file. |
| "Database upgrade required" | The bundled schema is newer than the database. Back up, `alembic upgrade head`, relaunch. No auto-migration ever runs. |
| Blank window / app exits silently | See `logs\desktop.log`. Set `SHREE_SHYAM_DESKTOP_DEV=1` and relaunch for DevTools. |
| Frontend stuck on "Loading…" | Check `logs\frontend.log` and `logs\backend.log`; ensure port 3000/8000 free. |
| Login fails | Account/password issue against the real `shree_shyam` users table; desktop never resets passwords. |

## Known limitations (first release)

- Requires the existing local PostgreSQL 18 + `shree_shyam`; PostgreSQL is
  **not** bundled and the installer never alters it.
- Single local machine usage; the backend binds to loopback only.
- No auto-update yet; upgrades are manual (re-run the installer).
- Installer is unsigned (no code-signing certificate configured) —
  SmartScreen may warn on first run.
- `"Menu"`, `"Cab Providers"`, public-website work are unchanged and out of
  scope.
- The desktop shell's renderer tests are unit-level (node:test); end-to-end
  rendering is verified manually/by smoke test, not in CI.

## Verification (Phase 6.4 acceptance)

Smoke-tested on Windows 11 x64:

- Installed via NSIS; Start Menu + Desktop (OneDrive) shortcut created.
- App launches; backend `/health/ready` → 200 (`environment: production`);
  frontend serves login (200).
- ADMIN login works against an **isolated scratch database** (user
  `desktopsmoke`); dashboard, navigation and ADMIN-only Audit Logs render.
- No login performed against the real `shree_shyam` (read-only smoke only).
- Graceful shutdown via WM_CLOSE leaves zero child processes and no PID files;
  reopening works.
- PostgreSQL-unreachable scenario: app fails fast with a clear error screen.
- `shree_shyam` was not modified; no sessions written to it.

## Recommended next milestone

A signed build + automated end-to-end packaging tests in CI (build the NSIS
installer in a `windows-latest` job, install it, launch headless with a
scratch PostgreSQL service, run a WebDriverIO/Playwright smoke suite), plus
code signing to remove SmartScreen friction.
