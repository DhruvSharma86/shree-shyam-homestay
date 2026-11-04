# Guest Portal — Shree Shyam Home Stay

A read-only, token-secured page per booking. No accounts, no passwords, no PII of other guests.

## 1. Access model
- At booking creation, the system generates a **cryptographically secure token** (≥ 256-bit entropy, e.g. `secrets.token_urlsafe(32)`).
- Only the **hash** (SHA-256 or better) is stored in `bookings.guest_token_hash`. The plaintext token exists only in the generated link.
- Link format: `https://<host>/guest/<token>` (token in path; TLS required in production).
- The token is scoped to **exactly one booking** and grants read access to that booking's portal view only.

## 2. Expiry rules
| Rule | Effect |
|---|---|
| 24 hours after `checkout_at` | Token **permanently invalid** (hard expiry, checked on every request) |
| Booking cancelled / no-show | Token invalid immediately |
| ADMIN revokes/rotates token | Old token invalid; new link issued |
| Booking not yet checked out | Token valid (guest may be mid-stay) |
| *(Optional, TBD)* inactivity cap | e.g. 30 days from creation regardless of checkout — configurable |

Expired/invalid tokens return a generic "link expired or invalid" page (no data, no hints about which case).

## 3. What the guest sees
| Section | Source |
|---|---|
| Personalised welcome (primary guest first name + stay dates) | `guests`, `bookings` |
| Room information (room number, category, amenities — TBD) | `rooms`, `room_types` |
| Stay dates (check-in/out) | `bookings` |
| Restaurant menu + photographs | `restaurant_info` |
| Restaurant contact information | `restaurant_info` |
| Cab company info + external website (link out) | `cab_info` |
| Tourist information | `public_content` / `hotel_info` (TBD content) |
| Hotel contact information | `hotel_info` |
| Wi-Fi SSID + password | `hotel_info` (guest-visible by design) |
| Final receipt (PDF download) — after checkout only | `receipts` (FINAL kind) |
| "Call for booking / assistance" tel: link | `hotel_info` |

## 4. What the guest MUST NEVER see
- ❌ Other guests' names, phones, or booking details
- ❌ Full ID proof details (or even proof type beyond necessity)
- ❌ Other bookings or folio/payment internals of other stays
- ❌ Staff account details, audit logs, financial reports, pricing internals beyond own folio
- ❌ Internal notes (staff notes on booking/guest)
- ❌ Guest's own full phone/email in page source beyond display necessity (minimise)

The portal endpoint joins **only** the one booking identified by the token hash. There is no guest login, no search, no listing.

## 5. Security controls
| Control | Detail |
|---|---|
| Entropy | ≥ 256-bit token; `secrets` module; never sequential/guessable |
| Storage | Hash only; DB leak alone cannot reconstruct portal access |
| Transport | HTTPS only; `Cache-Control: no-store`; no indexing (`X-Robots-Tag: noindex`) |
| Rate limiting | Per-IP + per-token attempts on `/guest/*`; exponential backoff on failures |
| Logging | Log `booking_id` + timestamp on portal access; **never log the full token** |
| WhatsApp delivery | Link sent to the primary guest's phone via messaging abstraction (mock in dev) |
| Revocation | ADMIN can rotate token; old link dies immediately |

## 6. Checkout receipt access
- After checkout, portal shows a "Download final receipt" button (PDF).
- Access remains valid until the 24-hour expiry; afterwards the guest cannot retrieve it (hotel retains its copy).
- Receipt contains only that guest's own stay data.

## 7. Failure / UX states
- Expired/invalid token → generic expired page with hotel contact "call us" option.
- Booking cancelled → generic message + hotel contact.
- Missing content (e.g. restaurant photos not yet configured) → section hidden gracefully (no errors, no placeholders with fake data).

## 8. Open decisions (TBD)
- Whether guests see their running folio/balance mid-stay (recommend: **only final receipt**, to reduce disputes — needs stakeholder sign-off).
- Inactivity cap value; portal language support (English-only initially).
- Whether the token link is regenerated on extension of stay (recommend: same token, expiry recomputed at checkout).
