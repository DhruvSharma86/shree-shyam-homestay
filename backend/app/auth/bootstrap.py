"""One-time initial ADMIN bootstrap.

Run once after the first migration, with credentials supplied via
environment variables (never CLI args, never hardcoded):

    INITIAL_ADMIN_USERNAME=... INITIAL_ADMIN_PASSWORD=... \\
        python -m app.auth.bootstrap

Safety properties:
- Refuses to run when ANY user already exists (no overwrite, no repeat).
- Requires both username and password (MIN 10 chars) from the environment.
- Password is hashed with Argon2id; the plaintext is never printed/logged.
- The action is audit-logged with a NULL actor (system event).
"""

import sys

from app.core.config import get_settings
from app.core.db import get_engine, session_scope
from app.core.logging_config import configure_logging, get_logger
from app.core.security import hash_password
from app.models.user import User, UserRole

logger = get_logger(__name__)


def bootstrap_initial_admin() -> int:
    """Create the initial ADMIN account. Returns a process exit code."""
    settings = get_settings()
    configure_logging(settings.log_level)

    username = settings.initial_admin_username.strip()
    password = settings.initial_admin_password

    if not username or not password:
        print(
            "ERROR: INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD must be "
            "set in the environment.",
            file=sys.stderr,
        )
        return 2
    if len(password) < 10:
        print("ERROR: INITIAL_ADMIN_PASSWORD must be at least 10 characters.", file=sys.stderr)
        return 2

    get_engine()  # Fail fast if the database is unreachable.
    from sqlalchemy import func, select

    from app.auth.service import write_audit

    with session_scope() as db:
        existing = db.scalar(select(func.count()).select_from(User))
        if existing:
            print(
                "ERROR: Users already exist. Bootstrap is one-time and will "
                "not overwrite existing accounts.",
                file=sys.stderr,
            )
            return 1

        admin = User(
            username=username,
            password_hash=hash_password(password),
            full_name=settings.initial_admin_full_name.strip() or "Hotel Administrator",
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        db.add(admin)
        db.flush()
        write_audit(
            db,
            action="ADMIN_BOOTSTRAPPED",
            resource_type="user",
            resource_id=str(admin.id),
            actor_user_id=None,
            metadata={"username": username},
        )

    print(f"Initial ADMIN '{username}' created. You can now log in.")
    logger.info("Initial admin bootstrap complete", extra={"context": {"username": username}})
    return 0


if __name__ == "__main__":
    raise SystemExit(bootstrap_initial_admin())
