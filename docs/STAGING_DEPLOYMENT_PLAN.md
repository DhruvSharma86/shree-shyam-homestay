# Pre-Phase 6 Milestone S1 — Managed Hosting Architecture & Deployment Compatibility Audit

Audit only (no deployment, no cloud resources, no purchases). Verified against code at
`0eb0ed2`. Pricing figures below are **estimates** from public search in November 2026 and
are explicitly unverified — confirm them in each provider's dashboard before buying (see §4).

## 1. Backend compatibility (FastAPI)

| Item | Finding |
|---|---|
| Python | `>=3.11` (`pyproject.toml`). Managed Python 3.11+ Pis suffice. |
| Install | `pip install -e .` (prod). No lockfile — builds are **not fully reproducible** (see blockers). |
| Entry point | `app.main:app` — startup must run `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (no `Procfile`/start manifest exists yet; S2 adds one). |
| Env required (prod) | `APP_ENV=production`, `APP_DEBUG=false`, `DATABASE_URL` (PostgreSQL, real pw), `SESSION_SECRET` (strong), `CORS_ORIGINS` (real frontend origin), `TRUSTED_PROXY_ENABLED` (opt-in only), `INITIAL_ADMIN_*` (first boot only). Guards in `app/core/config.py` fail fast on dev defaults. |
| Session/CSRF/CORS | Cookie `HttpOnly; Secure` (non-dev); `SameSite=Lax`; CSRF double-submit; CORS credentials + explicit origin list. SameSite=Lax suits a single-site deployment; a split-domain Vercel+Render design must keep frontend/API on the same site (or same-origin proxy) — see blockers. |
| DB | `psycopg[binary]`, pooled (`pool_size 5`, `max_overflow 10`, `pre_ping`). Read-only (`SELECT 1`) readiness; no writes from health checks. |
| Migrations | `alembic upgrade head` (single head `e2f3a4b5c6d7`). App never migrates on startup. Fresh-PG upgrade verified in CI. |
| Health | `/health/live` (no DB), `/health/ready` (DB → 200/503), `/health` — no secrets in bodies. |
| Proxy assumptions | TLS terminates at the proxy; app binds loopback. `X-Forwarded-For` honoured only with `TRUSTED_PROXY_ENABLED=true` (proxy must strip spoofed headers). |
| Timeouts | Client-side 15s (both Axios clients); provider proxy timeouts must exceed 15s (typical 60s+ OK). |
| Rate limiter | In-process, **single-process only**. Do not run replicas. |
| Filesystem | **None required.** Receipt PDFs are in-memory ReportLab bytes in PostgreSQL; no uploads; no local disk writes. Ephemeral filesystems are safe. |
| Verdict | **Compatible with any managed Python web service** (Render/Railway class) as a single always-on process. |

## 2. Frontend compatibility (Next.js)

| Item | Finding |
|---|---|
| Node / Next / React | Next.js `16.4.5`, React `19.3.0`, `npm` + `package-lock.json`. Requires Node 20+ LTS (Next 16 baseline — set explicitly in S2). |
| Build / start | `npm run build` (`next build`) → `npm run start` (`next start`). **Needs a persistent Node server** (not static export). |
| Env (build-time) | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_API_V1` — public, baked into the bundle; set **before** `next build`. No secrets in any `NEXT_PUBLIC_*` var. `frontend/.env.example` documents them. |
| API access | All client-side (Axios, credentials for staff / bearer-link for guests). No server-side data fetching that would need a service-to-service secret. |
| App Router | App Router with PPR (`cacheComponents` + `partialPrefetching`), dynamic `/guest/[token]` (`instant=false`), `headers()` security rules, static `/admin/*`. Managed Next.js hosts (Vercel) and container-style PaaS (Render/Railway running `next start`) both support this. |
| Origins | Staff = same-site cookies (`SameSite=Lax`); guest = bearer-link (no cookies). No `localhost` hardcode — 3 files fall back to `localhost` only when the public env var is unset (safe for staging once set). No filesystem assumptions (no `fs`, no local disk). |
| Verdict | **Needs a Node server** — compatible with Vercel, Render, or Railway. |

## 3. PostgreSQL requirements

Managed PostgreSQL must support: PostgreSQL 16-class server, `psycopg` v3 binary driver,
`btree_gist` (`CREATE EXTENSION IF NOT EXISTS` + exclusion constraint on
`(room_id, daterange)`), `plpgsql` immutability triggers on `folio_entries`/`payments`/`receipts`,
`FOR UPDATE` row locks, `UUID`, `NUMERIC(12,2)` financials, binary (`bytea`) receipt storage, and `pgcrypto`-free UUID handling (app-generated UUIDs).

- **Render Postgres**: `btree_gist` is listed as supported (official extensions docs) — verify in S2 by running the real migrations.
- **Railway Postgres**: arbitrary `CREATE EXTENSION` is **not guaranteed** (provider feedback threads indicate extensions need image changes) — HIGH risk for the exclusion constraint unless confirmed in S2.
- Triggers/exclusion/dialect are all standard PostgreSQL; no provider-specific SQL beyond the extension.

## 4. Hosting comparison (estimates — verify before buying)

| | A — Render (all) | B — Railway (all) | C — Vercel + (Render/Railway) |
|---|---|---|---|
| 1. Compatibility | Full: Python + Node + PG on one platform | Full for app; PG extension risk (above) | Full: Vercel is the natural Next.js home; backend still Python/PG on a PaaS |
| 2. Setup | Lowest (native PG + services) | Low (add-on PG) | Highest (two dashboards, CORS/cookie topology) |
| 3. Free/trial | Free services spin down; free PG expires 30 days (docs) — staging only | Trial credits; usage-based after | Hobby free for frontend; backend/PG paid |
| 4. Est. monthly* | ~$13–30 (starter web + basic PG estimates) | ~$10–40+ (usage-based; PG est. $10–40) | ~$0–20 (Hobby) + backend/PG ≈ A/B |
| 5. Persistence | Paid PG persists; free PG expires | Trial/PG persists while paid | Vercel stateless; PG wherever the backend lives |
| 6. HTTPS | Yes | Yes | Yes |
| 7. Custom domain | Yes | Yes | Yes (Vercel DNS vs proxy — pick one) |
| 8. Env mgmt | Dashboard env vars | Dashboard env vars | Split across two dashboards |
| 9. GitHub deploy | Native | Native | Native |
| 10. Logs | Dashboard logs | Dashboard logs | Split logs (harder to correlate) |
| 11. Backup/restore | PITR on paid tiers; manual dumps | Manual dumps | Same as backend host |
| 12. Ops complexity | Lowest (one vendor) | Low (one vendor) | Highest (two vendors, cookie topology) |
| 13. Cookies/CSRF | Same-site `Lax` natural | Same-site `Lax` natural | Split origins complicate `Lax`/CORS |
| 14. Guest security | `no-store`/headers unaffected | Same | Same, plus origin-join risk |
| 15. Scale limits | Single process (fits limiter; no replicas) | Single process | Single backend process |

\* Estimates only (from November 2026 public snippets; plan limits change without notice). Confirm in pricing dashboards in S2 before any purchase.

## 5. Deployment blockers (confirmed defects vs risks)

| ID | Severity | Status | Blocker |
|---|---|---|---|
| B1 | **HIGH** | Confirmed gap (not a bug) | No production start manifest (`Procfile`/start command) — S2 must add `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. |
| B2 | **HIGH** | Confirmed gap | No backend lockfile — `pip install` is unreproducible (Python builds may drift). S2 should generate and pin a lockfile. |
| B3 | **HIGH** | Confirmed risk | `btree_gist` on managed PG (Railway uncertain; Render supported) — S2 must run real migrations against the staging PG before any data. |
| B4 | **MEDIUM** | Risk | Split-site cookies (Option C): staff `SameSite=Lax` + `CORS_ORIGINS` must line up; single-vendor (A/B) avoids it. |
| B5 | **MEDIUM** | Risk | Node version unspecified — S2 must pin Node 20+ LTS for the Next build. |
| B6 | **MEDIUM** | Risk | `NEXT_PUBLIC_*` are build-time — wrong API URL at build time requires a rebuild (S2 documents the order). |
| B7 | **LOW** | Risk | No request-body size limit in app (proxy limit recommended; receipt PDFs are small). |
| B8 | **LOW** | Risk | Free-tier spin-down/30-day PG expiry make free plans unsuitable for a real staging demo (handled by starting on the smallest paid tier). |

## 6. Recommendation

**Option A — Render (all three services on one platform) for staging.** It is the simplest
technically suitable choice for a six-room homestay: one vendor, one dashboard, same-site
cookies (CSRF/CORS natural), supported `btree_gist`, GitHub deploys, and the smallest
operational surface. Option B is an acceptable fallback only if S2 proves the extension +
triggers run cleanly. Option C is the most operationally complex (two dashboards, split
cookie topology) and is not recommended for this stack. Run one backend process and one
Next server; do not scale replicas (the in-memory limiter).

## 7. S2 preparation checklist

### Tasks OpenCode can perform
- [ ] Add backend start manifest and pin/verify Python 3.11+ runtime.
- [ ] Generate + pin a backend lockfile; re-test install from lockfile.
- [ ] Pin Node 20+ LTS in manifests; verify clean `npm ci && npm run build` from a fresh checkout.
- [ ] Produce staging `.env` templates (placeholders) for backend + frontend (incl. `CORS_ORIGINS`, `TRUSTED_PROXY_ENABLED`, pre-build `NEXT_PUBLIC_*` order).
- [ ] Run local migration dry-run (`alembic upgrade head` on SQLite + `./alembic --sql` review) and document the expected migration output.
- [ ] Verify health-endpoint contract (`/health/live`, `/health/ready`) against the staging URLs once live.
- [ ] Update `docs/OPERATIONS.md` with the staging URLs and smoke-check results.

### Tasks requiring the project owner (do not share secrets in chat)
- [ ] Create the Render account and connect the GitHub repository.
- [ ] Provision managed PostgreSQL (confirm `btree_gist` + triggers on the real migrations).
- [ ] Enter secrets in the provider dashboard (`DATABASE_URL`, `SESSION_SECRET`, `CORS_ORIGINS`, `NEXT_PUBLIC_*`, initial ADMIN bootstrap).
- [ ] Confirm the paid starter tier before any purchase.

## 8. Expected staging validation (S2 smoke)
1. `GET /health/live` + `/health/ready` → 200 (ready only with DB up).
2. Fresh staging DB: `alembic upgrade head` exit 0, single head `e2f3a4b5c6d7`.
3. ADMIN login → change password → create rate/guest/booking → CHECK_IN payment → check in → copy one-time link.
4. Anonymous guest link: overview/menu/cab/wifi load with `cache-control: no-store, private`; images show dish alt text; `.guest` HTML has `no-store` + `noindex`.
5. Logout → staff 401 without session; receptionist rotate/revoke → 403.

## 9. Remaining production launch blockers
Real PG restore drill (NOT VERIFIED), backend lockfile (PARTIAL), backend vuln scan (NOT VERIFIED),
and staging smoke pass (§8) must all complete before any production go-live. Phase 6 remains
not started.
