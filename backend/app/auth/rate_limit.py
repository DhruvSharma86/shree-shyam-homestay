"""In-process rate limiting (sliding windows, bounded memory).

Scope note: this is a single-process guard — appropriate for the single
backend instance in Phase 1. If the deployment ever runs multiple backend
replicas, move this to shared storage (Redis/DB). It never uses an
external service and resets on process restart.

Two budgets are enforced:
- login: per-username failed-login budget.
- portal: per-IP failed-portal-access budget (Priority 3 audit). The
  previous per-token key was a bypass: every guessed token hashed to a
  fresh key, so brute force was never throttled and the map grew without
  bound. IP keying closes that hole at the cost of sharing the budget
  across clients behind one NAT (documented trade-off).

Memory is bounded: the store keeps at most ``MAX_TRACKED_KEYS`` entries;
when full, the oldest-inserted key is evicted (FIFO). This prevents an
attacker minting unbounded keys (random tokens, random usernames, spoofed
IPs) to exhaust process memory.
"""

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings

MAX_TRACKED_KEYS = 5000

_attempts: dict[str, deque[datetime]] = defaultdict(deque)


def _prune(key: str, now: datetime, window: timedelta) -> None:
    """Drop timestamps outside the sliding window for ``key``."""
    bucket = _attempts[key]
    while bucket and bucket[0] <= now - window:
        bucket.popleft()


def _ensure_capacity(key: str) -> None:
    """Evict oldest keys until there is room for ``key`` (bounded memory)."""
    if key in _attempts or len(_attempts) < MAX_TRACKED_KEYS:
        return
    while len(_attempts) >= MAX_TRACKED_KEYS:
        oldest = next(iter(_attempts))
        _attempts.pop(oldest, None)


def _register(key: str, window_seconds: int) -> None:
    """Record one failure for ``key`` inside its sliding window."""
    now = datetime.now(UTC)
    window = timedelta(seconds=window_seconds)
    _ensure_capacity(key)
    _prune(key, now, window)
    _attempts[key].append(now)


def _is_limited(key: str, attempts: int, window_seconds: int) -> bool:
    """Return True when ``key`` has blown its failed-access budget."""
    now = datetime.now(UTC)
    window = timedelta(seconds=window_seconds)
    if key not in _attempts:
        return False
    _prune(key, now, window)
    return len(_attempts[key]) >= attempts


def _clear(key: str) -> None:
    """Forget all recorded attempts for ``key`` (on success)."""
    _attempts.pop(key, None)


# --- Login (per-username) ------------------------------------------------------


def register_failed_attempt(username: str) -> None:
    """Record one failed login attempt for ``username``."""
    _register(username, get_settings().login_rate_limit_window_seconds)


def is_rate_limited(username: str) -> bool:
    """Return True when ``username`` exceeded the failed-login budget."""
    s = get_settings()
    return _is_limited(username, s.login_rate_limit_attempts, s.login_rate_limit_window_seconds)


def clear_attempts(username: str) -> None:
    """Forget all recorded attempts for ``username`` (on success)."""
    _clear(username)


# --- Guest portal (per-IP) -----------------------------------------------------


def portal_key_for_ip(client_ip: str | None) -> str:
    """Return the rate-limit key for a portal client IP (never a token)."""
    return f"portal-ip:{client_ip or 'unknown'}"


def register_portal_attempt(client_ip: str | None) -> None:
    """Record one failed (unresolvable token) portal attempt from an IP."""
    _register(portal_key_for_ip(client_ip), get_settings().portal_rate_limit_window_seconds)


def is_portal_rate_limited(client_ip: str | None) -> bool:
    """Return True when this IP has blown its failed-portal-access budget."""
    s = get_settings()
    return _is_limited(
        portal_key_for_ip(client_ip),
        s.portal_rate_limit_attempts,
        s.portal_rate_limit_window_seconds,
    )
