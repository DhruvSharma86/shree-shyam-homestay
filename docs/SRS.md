# Software Requirements Specification — Shree Shyam Home Stay Management System

| | |
|---|---|
| Project | Shree Shyam Home Stay — Management System |
| Version | 0.1 (documentation phase) |
| Status | Draft for stakeholder review |
| Source | Product brief: 6-room homestay, phone/walk-in bookings only |

**Conventions:** `MUST` = mandatory, `SHOULD` = expected, `TBD` = unknown/pending decision (§10). Nothing in this document invents prices, GST rates, addresses, or contact details — all are configurable or TBD.

---

## 1. Introduction

### 1.1 Purpose
Specify the requirements for a lightweight management system covering: user management, room inventory, guest registration, bookings (phone/walk-in), billing/folio, payments, receipts, a token-secured guest portal, WhatsApp notifications, and administrative/financial reporting.

### 1.2 Scope
**In scope:** admin + receptionist dashboards, booking lifecycle, billing, guest portal (read-only token access), public marketing website (advertisement only), PDF receipts, WhatsApp messaging abstraction with mock provider, audit logs, RBAC, structured logging, automated tests, Alembic migrations.

**Out of scope:** online booking, online payments, microservices, multi-property support, housekeeping/maintenance ticketing, CRM/marketing automation, real WhatsApp integration (Phase 7, after mock is proven).

### 1.3 Definitions
| Term | Meaning |
|---|---|
| Folio | Booking-wise itemised ledger of charges and payments |
| Primary guest | The single guest of record per booking |
| Guest token | Cryptographically secure, single-booking access token for the guest portal |
| Mock WhatsApp provider | Development-only messaging implementation that logs instead of sending |

## 2. Overall description

### 2.1 Product perspective
Modular monolith backend (FastAPI) + separate Next.js frontend, PostgreSQL database, deployed as two services (plus DB). All access is via authenticated web sessions; guests access only via token link.

### 2.2 Operating context
- 6 rooms; categories: Normal, Deluxe, Super Deluxe (distribution TBD)
- Bookings arrive by phone or walk-in; receptionist creates them in-system
- One night's room charge is collected at check-in; balance at checkout
- Financial records must be retained and auditable; never silently deleted/overwritten

### 2.3 Constraints
- C-1: No online booking or online payment may be implemented.
- C-2: The system MUST NOT hardcode room prices, GST rates, contact details, or addresses.
- C-3: Financial records MUST NOT be silently deleted or overwritten (append-only; corrections via reversal/adjustment entries).
- C-4: Guest portal MUST NOT expose sensitive guest data (other guests, full IDs, other bookings, financial internals).
- C-5: Guest links MUST expire 24 hours after checkout.
- C-6: Secrets come only from environment variables; none may be committed.

## 3. Functional requirements

### 3.1 Authentication & users
| ID | Requirement |
|---|---|
| FR-AUTH-01 | The system MUST authenticate staff via server-side sessions (httpOnly, Secure, SameSite cookies). |
| FR-AUTH-02 | Passwords MUST be hashed with a strong adaptive hash (e.g. argon2id/bcrypt). |
| FR-AUTH-03 | ADMIN MUST be able to create, edit, deactivate, and reset credentials for ADMIN and RECEPTIONIST accounts. |
| FR-AUTH-04 | Users MUST have a lifecycle state (active / inactive); inactive users cannot log in. |
| FR-AUTH-05 | Sessions MUST expire after inactivity (configurable timeout) and support explicit logout. |

### 3.2 Hotel, room, and pricing configuration (ADMIN only)
| ID | Requirement |
|---|---|
| FR-CFG-01 | ADMIN MUST be able to edit hotel information (name, address, contacts, maps link — all initial values TBD). |
| FR-CFG-02 | Rooms MUST be configurable: number/label, room type/category, status. Categories: Normal, Deluxe, Super Deluxe. |
| FR-CFG-03 | Nightly room prices MUST be configurable per category/room and MUST NOT be hardcoded. Price changes MUST NOT retroactively alter existing bookings (price snapshot at booking). |
| FR-CFG-04 | ADMIN MUST be able to manage restaurant info (menu, photos, contact) and cab info (company, external website), and system settings including tax/GST config. |
| FR-CFG-05 | Changes to pricing/tax settings SHOULD be audit-logged with before/after values. |

### 3.3 Guest management — ✅ implemented Phase 3.1 except Aadhaar (deferred)
| ID | Requirement |
|---|---|
| FR-GST-01 | Receptionists MUST be able to register guests (name, phone, ID details as available, address optional). **Done for name/phone/address/email**; ID details/Aadhaar image **deferred** (see below). |
| FR-GST-02 | Each booking has exactly one primary guest; the system SHOULD support lookup of a returning guest by phone number to avoid duplicates. **Done**: `GET /api/v1/guests?q=` (name/email/phone) + duplicate rule (active phone + normalized name → 409). |
| FR-GST-03 | Guest records MUST NOT be hard-deleted if they have bookings (retain for financial/audit integrity). **Done**: soft-deactivation only (`POST /{id}/deactivate`); no DELETE endpoint. |

**Aadhaar/document deferral (Phase 3.1 decision):** SRS FR-GST-01 mentions "ID details as available" and the business brief mentions an Aadhaar photograph, but no compliant, approved design exists for collecting/retaining Aadhaar data under the Aadhaar Act, 2016 and IT Act (private encrypted storage, consent, access controls, retention/purge, breach handling). Collecting full Aadhaar images/numbers without that design would be unlawful risk, so Phase 3.1 stores **no** Aadhaar image, number, or ID-proof type/number. A separate, legally reviewed document-handling milestone is required before any collection. DATABASE_DESIGN §2.9 records this explicitly.

### 3.4 Booking
| ID | Requirement |
|---|---|
| FR-BKG-01 | The system MUST support booking creation for phone/walk-in requests with: guest, room (or room type with allocation), check-in date, check-out date, expected guests, source (phone/walk-in), and notes. |
| FR-BKG-02 | The system MUST prevent overlapping bookings for the same room (database-enforced). |
| FR-BKG-03 | The system MUST expose room availability for arbitrary date ranges. |
| FR-BKG-04 | Booking MUST support a lifecycle status (see `docs/BOOKING_WORKFLOW.md`). |
| FR-BKG-05 | The system MUST support check-in, checkout, cancellation, and no-show handling per workflow rules. |
| FR-BKG-06 | Booking history MUST be viewable per guest and per room. |
| FR-BKG-07 | A booking's room rate MUST be snapshotted at creation (see FR-CFG-03). |

**Phase 3.2 status (implemented 2026-11-09, backend only):** FR-BKG-01 (guest/room/dates/guests/source/notes), FR-BKG-02 (app lock + PostgreSQL exclusion constraint), FR-BKG-03 (availability endpoints), FR-BKG-04 (minimal `CONFIRMED → CANCELLED` lifecycle), FR-BKG-06 (guest/room-filtered list + pagination), FR-BKG-07 (single-rate snapshot + tax snapshot; mid-stay rate changes rejected rather than blended). FR-BKG-05 is **partial**: cancellation implemented; check-in/checkout/no-show, folio creation, tokens, payments and portal links are deferred to Phases 4–5 (see ROADMAP). A deactivated guest cannot be booked until reactivated via the guest API. No online-booking source exists; the website remains advertisement-only.

**Phase 4.1 status (implemented 2026-11-09, backend only):** one logical folio per booking (append-only `folio_entries` + separate `payments` table created); `ROOM_CHARGE` initialization in the booking transaction; charges/discounts/reversals APIs; derived balance (`Σ entries − Σ payments`, Decimal); PG immutability triggers (SQLite documented limitation); D1 modes `CASH/UPI/CARD_POS`; D4 discounts ADMIN-only; D6 both-role folio read. Payment creation, check-in/checkout, settlement, PDFs, messages and reports are deferred (Phases 4.2–4.4).

**Phase 4.2 status (implemented 2026-11-09, backend only):** `GET /folio` made read-only (side effect corrected); explicit `POST /folio/initialize` (auditable backfill, idempotent); payment recording (`POST /payments`, modes + stages + references), D9 overpayment gate (ADMIN + mandatory reason), ADMIN-only payment reversal (D3); `CHECKED_IN` lifecycle with mandatory one-night CHECK_IN payment (D2, stored snapshot). Checkout settlement, PDFs, messages and reports remain deferred (Phases 4.3–4.4).

### 3.5 Billing & payments
| ID | Requirement |
|---|---|
| FR-BIL-01 | Each booking MUST have a folio with room charges, additional charges, discounts, payments, and balance. |
| FR-BIL-02 | Additional charges MUST be recordable (e.g. restaurant, cab, extra services) with description and amount. |
| FR-BIL-03 | Discounts MUST require appropriate permission (ADMIN-only beyond a configurable threshold — TBD). |
| FR-BIL-04 | Payments MUST be recordable as cash, UPI, or card/POS, and as advance, at check-in, or at checkout. |
| FR-BIL-05 | One night's room amount SHOULD be collected at check-in; the remaining balance at checkout (configurable policy, TBD). |
| FR-BIL-06 | Financial operations MUST run in database transactions; partial writes MUST NOT persist. |
| FR-BIL-07 | Posted financial entries MUST NOT be edited/deleted in place; corrections MUST use reversal/adjustment entries (audit trail preserved). |
| FR-BIL-08 | Tax/GST configuration MUST be adjustable by ADMIN; the system MUST NOT assume GST registration or rates (TBD whether GST applies). |
| FR-BIL-09 | The system MUST generate a PDF receipt (ReportLab) for payments and final checkout settlement. |

### 3.6 Guest portal
| ID | Requirement |
|---|---|
| FR-PORTAL-01 | Every booking MUST receive a unique, cryptographically secure guest access token at creation. |
| FR-PORTAL-02 | Tokens MUST be stored hashed (never in plaintext) and be single-booking scoped. |
| FR-PORTAL-03 | The portal MUST show: personalised welcome, room info, stay dates, restaurant menu/photos/contact, cab info + external website, tourist info, hotel contact, Wi-Fi details, and final receipt after checkout. |
| FR-PORTAL-04 | Guest links MUST expire 24 hours after checkout (and SHOULD expire after a configurable inactivity window regardless of checkout). |
| FR-PORTAL-05 | The portal MUST NOT expose sensitive guest information or other guests'/bookings' data. |
| FR-PORTAL-06 | ADMIN MUST be able to revoke/rotate a guest token (e.g. lost phone, suspected leak). |

### 3.7 Checkout
| ID | Requirement |
|---|---|
| FR-OUT-01 | At checkout the system MUST compute final charges and outstanding balance. |
| FR-OUT-02 | The system MUST record the final payment, generate the PDF receipt, and make it available to the guest. |
| FR-OUT-03 | The system MUST send a WhatsApp checkout notification (via messaging abstraction; mock in development). |
| FR-OUT-04 | The hotel's own copy of financial records MUST be retained indefinitely (subject to legal retention rules — TBD). |

### 3.8 Public website (advertisement only)
| ID | Requirement |
|---|---|
| FR-WEB-01 | The website MUST include: Home, About, Rooms, Gallery, Facilities, Restaurant, Nearby attractions, Contact, Google Maps embed, and "Call for Booking" (tel: link). |
| FR-WEB-02 | The website MUST NOT implement online booking or payment. |
| FR-WEB-03 | Website content (photos, text, contacts) MUST be editable without code changes where practical (CMS or DB-backed content — TBD). |

### 3.9 WhatsApp messaging
| ID | Requirement |
|---|---|
| FR-MSG-01 | The system MUST define a messaging abstraction supporting: welcome message, personalised guest link delivery, checkout message, PDF receipt delivery. |
| FR-MSG-02 | A mock provider MUST log messages in development; no API credentials may be invented or committed. |
| FR-MSG-03 | Real WhatsApp Cloud API integration is explicitly deferred (Phase 7, after the mock provider is proven). |
| FR-MSG-04 | Message attempts SHOULD be logged with status (queued/sent/failed) for retry visibility. |

### 3.10 Admin reporting, audit & financial reports
| ID | Requirement |
|---|---|
| FR-REP-01 | ADMIN MUST be able to view all guests, bookings, and occupancy summaries. |
| FR-REP-02 | ADMIN MUST be able to view financial reports (revenue, payments by mode, outstanding balances). RECEPTIONIST MUST NOT access these. |
| FR-REP-03 | Important administrative actions (user changes, price/tax changes, discounts, voids) MUST be audit-logged (who, what, when, before/after). |
| FR-REP-04 | Audit logs MUST be append-only and admin-viewable. |

## 4. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | **Security:** session cookies httpOnly/Secure/SameSite; CSRF protection; input validation (Pydantic); output encoding; rate limiting on auth and guest-token endpoints. |
| NFR-02 | **Performance:** 6-room property — trivial load; API p95 < 300 ms for standard endpoints on modest hardware. |
| NFR-03 | **Maintainability:** modular monolith; clear module boundaries; no circular dependencies; documented APIs. |
| NFR-04 | **Testability:** automated backend tests (unit + API); financial logic must have deterministic tests. |
| NFR-05 | **Observability:** structured JSON logs with request IDs; health/readiness endpoints. |
| NFR-06 | **Data integrity:** FK constraints, unique constraints, check constraints, DB-enforced no-overlap; Alembic migrations for every schema change. |
| NFR-07 | **Privacy:** collect minimal guest PII; mask/redact in logs; token links show minimal data. |
| NFR-08 | **Portability:** run via docker-compose for local dev and small single-server deployment. |

## 5. Assumptions
- A-1: Single property, single deployment; no multi-tenancy.
- A-2: Staff devices are modern browsers; no native mobile apps.
- A-3: Internet access exists for WhatsApp API and Google Maps (deferred to later phases).
- A-4: Phone numbers are the practical guest identifier (normalized E.164).

## 6. Dependencies
- PostgreSQL (managed or dockerized); Next.js frontend build; ReportLab; WhatsApp Cloud API (later).

## 7. Traceability
Each FR maps to database entities (`docs/DATABASE_DESIGN.md`), permissions (`docs/RBAC.md`), workflows (`docs/BOOKING_WORKFLOW.md`, `docs/BILLING_WORKFLOW.md`), and API endpoints (`docs/API_DESIGN.md`). Coverage is reviewed in the implementation handoff report.
