"""In-process login rate limiting (per username, sliding window).

Scope note: this is a single-process guard — appropriate for the single
backend instance in Phase 1. If the deployment ever runs multiple backend
replicas, move this to shared storage (Redis/DB). It never uses an
external service and resets on process restart.
"""

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings

_attempts: dict[str, deque[datetime]] = defaultdict(deque)


def _prune(key: str, now: datetime) -> None:
    """Drop timestamps outside the sliding window for ``key``."""
    window = timedelta(seconds=get_settings().login_rate_limit_window_seconds)
    bucket = _attempts[key]
    while bucket and bucket[0] <= now - window:
        bucket.popleft()


def register_failed_attempt(username: str) -> None:
    """Record one failed login attempt for ``username``."""
    now = datetime.now(UTC)
    _prune(username, now)
    _attempts[username].append(now)


def is_rate_limited(username: str) -> bool:
    """Return True when ``username`` exceeded the failed-login budget."""
    now = datetime.now(UTC)
    _prune(username, now)
    return len(_attempts[username]) >= get_settings().login_rate_limit_attempts


def clear_attempts(username: str) -> None:
    """Forget all recorded attempts for ``username`` (on success)."""
    _attempts.pop(username, None)
