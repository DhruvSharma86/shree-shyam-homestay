# Frontend — Shree Shyam Home Stay (admin)

Next.js (App Router) + TypeScript + Tailwind CSS + TanStack Query + React Hook Form + Zod.

## Setup

```bash
cd frontend
npm install --legacy-peer-deps
cp .env.example .env.local   # set NEXT_PUBLIC_API_BASE_URL to your FastAPI origin
npm run dev                  # http://localhost:3000
```

## Commands

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server |
| `npm run build` | Production build (type-checks + lints) |
| `npm run lint` | ESLint |
| `npm run test` | Vitest (unit + component) |

## API integration

- Base URL: `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`) + `NEXT_PUBLIC_API_V1` (`/api/v1`).
- Axios instance in `src/lib/api.ts` with `withCredentials: true`; CSRF token read from the `sshs_csrf` cookie and sent as `X-CSRF-Token` on mutations.
- Server state via TanStack Query; forms via React Hook Form + Zod (`src/schemas`); client auth state via Zustand (`src/stores/auth.ts`).
- No tokens in localStorage; backend HttpOnly cookies are the only session carrier.

## Authentication flow

1. `POST /auth/login` → HttpOnly session + CSRF cookies; response includes `user` + `permissions`.
2. Protected routes use `RequireAdmin`: `GET /auth/me` on load (session restoration after refresh); unauthenticated → `/login`; non-admin → access-restricted screen; backend is authoritative (403 from API also handled).
3. `POST /auth/logout` → cookies cleared, store cleared, redirect to `/login`.

## Routes

| Route | Purpose |
|---|---|
| `/login` | Staff sign-in |
| `/admin/dashboard` | Configuration summary (no invented metrics) |
| `/admin/hotel` | Hotel profile |
| `/admin/room-types` | Room categories |
| `/admin/rooms` | Rooms (operational status) |
| `/admin/room-rates` | Nightly rates (₹, append-only history) |
| `/admin/tax-settings` | Tax versions (default NONE) |
| `/admin/restaurant` | Restaurant info |
| `/admin/menu` | Menu categories + items (image URLs only) |
| `/admin/cab-providers` | Cab partners |
| `/admin/users` | Staff accounts |
| `/admin/audit-logs` | Pending — no read API yet (labelled, not wired) |

Receptionist dashboard is a later milestone (not implemented here).
