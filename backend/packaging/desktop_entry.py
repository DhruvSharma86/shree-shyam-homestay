"""Packaged desktop entry point (PyInstaller).

Modes:
- (default)           Start the ASGI server on ``127.0.0.1`` only.
- ``--check-migration``  Compare the database's ``alembic_version`` with the
                        migration head bundled into this executable. Prints a
                        single JSON line and exits:
                          0 — database is up to date
                          3 — schema upgrade required
                          4 — check failed (database unreachable / not migrated)
- ``--version``       Print the package version and exit 0.

Configuration is provided exclusively through environment variables (the
desktop launcher passes ``DATABASE_URL``, ``SESSION_SECRET``, ...) — never
from a ``.env`` file shipped inside the installation. ``Settings`` still
supports a local ``.env`` for development convenience, but it is not
required.
"""

from __future__ import annotations

import json
import os
import sys

_PACKAGE_VERSION = "0.1.0"


def _base_dir() -> str:
    """Directory that contains the bundled application/resources."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return str(meipass)
    return os.path.dirname(os.path.abspath(__file__))


def check_migration() -> int:
    """Report alembic migration status as JSON. Never raises."""
    try:
        import socket

        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url

        from app.core.config import get_settings

        settings = get_settings()
        url = make_url(settings.database_url)

        # Preflight for network databases: a closed/unreachable host must
        # fail fast, never hang the desktop startup flow.
        if url.get_backend_name() != "sqlite":
            host = url.host or "localhost"
            port = int(url.port or 5432)
            try:
                with socket.create_connection((host, port), timeout=5):
                    pass
            except OSError:
                print(
                    json.dumps(
                        {
                            "status": "error",
                            "message": "Database is not reachable.",
                        }
                    )
                )
                return 4
            connect_args = {"connect_timeout": 5}
        else:
            connect_args = {"check_same_thread": False}

        # A short-lived probe engine (no pool, hard connect timeout) — the
        # application's own engine is irrelevant for a read-only status check.
        engine = create_engine(settings.database_url, connect_args=connect_args)
        script_dir = ScriptDirectory(os.path.join(_base_dir(), "alembic"))
        heads = set(script_dir.get_heads())

        try:
            with engine.connect() as connection:
                current = MigrationContext.configure(connection).get_current_revision()
                if current is None:
                    connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        up_to_date = current is not None and current in heads and len(heads) == 1
        status = "up_to_date" if up_to_date else "upgrade_required"
        print(
            json.dumps(
                {
                    "status": status,
                    "current": current,
                    "heads": sorted(heads),
                    "up_to_date": up_to_date,
                }
            )
        )
        return 0 if up_to_date else 3
    except Exception:  # noqa: BLE001 — never leak URLs/credentials
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "Migration status check failed. "
                    "See the application log for details.",
                }
            )
        )
        return 4


def serve() -> int:
    """Start uvicorn on the loopback interface only."""
    import uvicorn

    host = "127.0.0.1"  # never bind to all interfaces
    raw_port = os.environ.get("DESKTOP_BACKEND_PORT", "8000")
    try:
        port = int(raw_port)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        port = 8000
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        access_log=False,  # avoid writing guest-portal bearer URLs to logs
    )
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--version" in args:
        print(_PACKAGE_VERSION)
        return 0
    if "--check-migration" in args:
        return check_migration()
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
