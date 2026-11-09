# Security — Shree Shyam Home Stay Management System (Priority 3, 2026-11-09)

Code-level audit (source inspection + automated reproduction). This is **not**
a penetration test and is **not** a formal certification.

## 1. Threat model (single-process deployment)

| Element | Assumption |
|---|---|
| Backend | FastAPI, one process, reverse proxy with TLS terminates HTTPS in front (production assumption) |
| Database | PostgreSQL is authoritative; SQLite is local/test only |
| Frontend | Next.js on a separate origin in dev; same TLS boundary in production |
| Guest link | HTTPS-only; raw token appears once at check-in and in the guest URL; hash-only at rest |
| Attackers in scope | Internet brute force of portal tokens; malicious guest A probing booking B; receptionist exceeding RBAC; misconfig/access-log token leakage |
| Out of scope | Host compromise, CDN/caching config beyond app headers, WhatsApp delivery (Phase 7) |

## 2. Confirmed findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| S1 | **High** | Portal brute-force limiter keyed per token hash: every guessed token was a fresh budget entry, so brute force was never throttled and the store grew without bound | **Fixed** — per-IP budget (60 failures / 300s) + bounded 5k-key store with FIFO eviction |
| S2 | **Medium** | External menu photos (`<img src=image_url>`) leaked the guest URL (containing the token) via `Referer` to third-party hosts | **Fixed** — `referrerPolicy="no-referrer"` on menu images + `Referrer-Policy: no-referrer` headers (API + frontend) |
| S3 | **Medium** | Missing security/caching headers on error responses and the guest page (shared-cache/indexing/clickjacking risk) | **Fixed** — backend `SecurityHeadersMiddleware` (nosniff, DENY, no-referrer, Permissions-Policy, portal no-store + `X-Robots-Tag: noindex` + `default-src 'none'` CSP); Next.js `headers()` for `/guest/:path*` (no-store, noindex, same protections) |
| S4 | **Medium** | `_client_ip` trusted `X-Forwarded-For` unconditionally: any client could spoof IPs (rate-limit evasion, audit poisoning) | **Fixed** — honoured only when `trusted_proxy_enabled=True`; default is peer-only |
| S5 | **Low** | In-process limiter store had no bound (DoS via unbounded distinct keys, incl. login usernames) | **Fixed** — same bounded store as S1 (login + portal) |

## 3. Verified safe (not vulnerabilities)

| Area | Evidence |
|---|---|
| Entropy | `secrets.token_urlsafe(32)` (256-bit) for session, portal, CSRF tokens |
| Hashing | SHA-256 hex stored only; `secrets.compare_digest` on compare; raw never in DB/logs/audits (tests: `test_token_rows_store_hash_only`, `test_audit_trail_has_no_raw_tokens_and_no_pii`) |
| Uniqueness | Unique `token_hash` + partial unique active-token index (one active per booking, race-safe via nested transaction) |
| Lifecycle | Strict `checked_out_at + 24h` expiry; cancelled/revoked/rotated-old always generic 404 (tests: `test_generic_404_identical_*`, `test_expiry_24h_after_checkout`) |
| Isolation | All portal routes resolve token → booking; no booking/receipt ID parameters; guest schemas expose stay/menu/cab/wifi/tourism/receipt-ref only (no phones, no internal IDs, no money) |
| Receipt | FINAL bytes + SHA-256 hash immutable; never regenerated on GET; guest/staff share the same bytes; `Content-Disposition: attachment`; no receipt-ID enumeration |
| Staff auth | HttpOnly session cookie, `Secure` outside dev, `SameSite=Lax`, idle + absolute timeouts with in-place revocation, login session rotation, Argon2id passwords, CSRF double-submit (constant-time), backend RBAC authoritative (frontend guards are UX only) |
| Frontend | Token never persisted (in-memory React Query keys only; `page.test` asserts no `localStorage` write); receipt blob URL revoked after download; guest content not in static output (PPR dynamic) |
| Logging | Audit metadata = booking/actor IDs only; unhandled errors log server-side, return generic envelope; `uvicorn.access` silenced to WARNING |

## 4. Rate-limiting assumptions (S1 residual)

- In-process, single-process only; resets on restart; not shared across replicas.
- Portal budget is **per-IP** (60 failed accesses / 300s, `portal_rate_limit_attempts`/`…_window_seconds`). Correct for brute force. Clients behind one NAT share the budget (legitimate guests may see 429 after heavy failures — retry after the window).
- Login budget remains per-username (10 / 300s).
- If the deployment ever runs N backend replicas, move both budgets to shared storage (DB/Redis). Do not multi-replicate without doing so.
- Store is bounded at 5,000 keys (FIFO eviction) to prevent key-minting DoS.

## 5. Production deployment assumptions

- Terminate TLS at the proxy; enable `trusted_proxy_enabled=true` only when the proxy strips/overwrites `X-Forwarded-For`.
- Keep `uvicorn.access` at WARNING or lower. If access logging is ever raised, full portal URLs (with tokens) **will** be written to logs — use a redacting access-log format or disable it.
- `CORS allow_origins` is dev-only (`http://localhost:3000`); harden via env for the production frontend origin.
- No CSP breaks are expected: the API CSP (`default-src 'none'`) applies only to JSON/PDF responses; the frontend sets no `default-src` CSP (intentional — a restrictive CSP was not proven against all pages).

## 6. Residual risks (deferred / accepted)

| Risk | Why accepted |
|---|---|
| Token in URL → browser history, screenshots, shared devices, proxy logs | Inherent to link-based guest access; mitigated by headers/referrer fixes, not eliminated (a magic-link move to POST is out of scope) |
| Content already loaded stays on screen if expiry/revocation happens while open | Data was already authorized when fetched; refetch-after-expiry is denied. A revalidation timer was deferred (UX noise vs. benefit) |
| Per-IP collateral blocking under NAT | Cost of the brute-force fix; short window + tests |
| Access-log token risk if operator raises log level (see §5) | Documentation-controlled; code already silences it |
| No formal penetration test; races covered by partial-index + PG concurrency tests, not exhaustive fuzzing | Stated scope limit |

## 7. Regression tests

- `backend/tests/test_guest_portal_security.py` — limiter (distinct-token throttling, per-IP not per-token, bounded store), XFF spoof default/opt-in, portal success/error headers, staff receipt headers, generic-404 identity, cross-booking/staff-API isolation, expiry receipt block, audit redaction, schema surface, hash-only storage.
- `backend/tests/test_guest_portal.py` — unchanged lifecycle coverage (all still green).
- `frontend/src/app/guest/[token]/page.test.tsx` — no-storage + no-referrer image assertions.
- `frontend/src/headers.test.ts` — Next.js `headers()` contract (guest no-store/noindex + global protections).

## 8. Error handling & retry policy (Priority 5, 2026-11-09)

- Frontend errors are classified (`network` / `timeout` / `server` / `invalid` / `auth` / `forbidden` / `validation` / `conflict` / `generic`) and shown as friendly messages — raw backend details are never mirrored.
- GETs retry only transient network/timeout/5xx outcomes, at most twice (exponential backoff 1s/2s, cap 5s). 404/401/403/422 are never retried, so retrying cannot probe token validity (no new oracle) and the generic 404 behaviour is preserved.
- Mutations never auto-retry: a timeout may mean the server committed the write. Staff-facing copy explains the outcome is unknown and points at the current booking state (no invented idempotency).
- Timeouts are 15s on both Axios clients; connectivity/5xx guest states are distinct from the invalid-link state and each offers manual retry (no full reload, no stale-data promotion).
