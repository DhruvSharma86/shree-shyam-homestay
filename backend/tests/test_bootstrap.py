"""Initial ADMIN bootstrap tests."""

from sqlalchemy import func, select

from app.auth.bootstrap import bootstrap_initial_admin
from app.models.user import User


def _bootstrap_with(monkeypatch, db_session, username="rootadmin", password="Bootstrap123!"):
    """Run the bootstrap against the test DB with env-provided credentials.

    The bootstrap runs in its own session/transaction; the test session is
    expiring it away so assertions see the committed rows.
    """
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", username)
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", password)
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        return bootstrap_initial_admin()
    finally:
        get_settings.cache_clear()
        db_session.expire_all()


def test_bootstrap_creates_admin(monkeypatch, db_session) -> None:
    """Bootstrap creates exactly one active ADMIN from env credentials."""
    code = _bootstrap_with(monkeypatch, db_session)
    assert code == 0
    admins = db_session.scalars(select(User)).all()
    assert len(admins) == 1
    assert admins[0].username == "rootadmin"
    assert admins[0].role == "ADMIN"
    assert admins[0].is_active is True
    # Password stored as hash, never plaintext.
    assert admins[0].password_hash != "Bootstrap123!"


def test_bootstrap_refuses_when_users_exist(monkeypatch, db_session) -> None:
    """Bootstrap will not overwrite existing accounts (exit code 1)."""
    from tests.factories import create_user

    create_user(db_session, username="existing")
    db_session.commit()

    code = _bootstrap_with(monkeypatch, db_session)
    assert code == 1
    count = db_session.scalar(select(func.count()).select_from(User))
    assert count == 1


def test_bootstrap_requires_credentials(monkeypatch, db_session) -> None:
    """Missing env credentials → exit code 2, nothing created."""
    code = _bootstrap_with(monkeypatch, db_session, username="", password="")
    assert code == 2
    count = db_session.scalar(select(func.count()).select_from(User))
    assert count == 0


def test_bootstrap_rejects_short_password(monkeypatch, db_session) -> None:
    """Passwords under 10 characters are refused."""
    code = _bootstrap_with(monkeypatch, db_session, password="short")
    assert code == 2
