"""Audit log tests — security-relevant actions are recorded (safely)."""

from sqlalchemy import select

from app.models.audit import AuditLog
from tests.factories import ADMIN_PASSWORD, RECEPTIONIST_PASSWORD, create_user, csrf_headers, login


def test_login_and_logout_are_audited(client, db_session) -> None:
    """AUTH_LOGIN + AUTH_LOGOUT rows appear with actor + no secrets."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    rows = db_session.scalars(select(AuditLog).order_by(AuditLog.created_at)).all()
    actions = [r.action for r in rows]
    assert "AUTH_LOGIN" in actions
    assert "AUTH_LOGOUT" in actions
    for row in rows:
        assert row.actor_user_id is not None
        metadata = row.metadata_json or {}
        assert "password" not in str(metadata).lower()


def test_failed_login_is_audited(client, db_session) -> None:
    """Failed logins create AUTH_LOGIN_FAILED rows (no credentials stored)."""
    login(client, "ghost", "Whatever12345!")

    rows = db_session.scalars(select(AuditLog)).all()
    failed = [r for r in rows if r.action == "AUTH_LOGIN_FAILED"]
    assert len(failed) == 1
    assert failed[0].resource_id == "ghost"
    assert "Whatever12345!" not in str(failed[0].metadata_json or "")


def test_user_management_is_audited(client, db_session) -> None:
    """USER_CREATED is recorded when an ADMIN creates an account."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)

    created = client.post(
        "/api/v1/users",
        json={
            "username": "rec9",
            "password": RECEPTIONIST_PASSWORD,
            "full_name": "Reception Nine",
            "role": "RECEPTIONIST",
        },
        headers=csrf_headers(client),
    )
    assert created.status_code == 201

    rows = db_session.scalars(select(AuditLog).where(AuditLog.action == "USER_CREATED")).all()
    assert len(rows) == 1
    assert rows[0].metadata_json["username"] == "rec9"
    assert RECEPTIONIST_PASSWORD not in str(rows[0].metadata_json)
