"""Password hashing and token hashing primitives.

Passwords use Argon2id (via the ``argon2-cffi`` backend). Session and guest
tokens are high-entropy random values; **only their SHA-256 hash is ever
stored** — the plaintext exists only in the cookie / URL given to the client.

No secret is ever logged anywhere in this module.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2id with OWASP-recommended parameters for interactive logins.
# Note: argon2-cffi defaults are already strong; parameters are pinned
# explicitly so they do not drift silently between library versions.
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password with Argon2id. Never returns plaintext."""
    return _ph.hash(plaintext)


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored Argon2id hash."""
    try:
        return _ph.verify(stored_hash, plaintext)
    except (VerifyMismatchError, ValueError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Return True when the stored hash uses outdated parameters."""
    try:
        return _ph.check_needs_rehash(stored_hash)
    except ValueError:
        return True


def generate_session_token() -> str:
    """Generate a new opaque session token (256-bit entropy, URL-safe)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a token (what we persist)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate a new CSRF token (double-submit cookie pattern)."""
    return secrets.token_urlsafe(32)


def compare_tokens(a: str, b: str) -> bool:
    """Constant-time comparison for token material."""
    return secrets.compare_digest(a, b)
