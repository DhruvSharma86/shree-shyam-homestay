"""Audit log tests — security-relevant actions are recorded (safely)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.user import User
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


def _new_client(db_session, username: str, role: str):
    """Distinct TestClient per role (separate cookie jars)."""
    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import create_app

    create_user(db_session, username=username, role=role)
    db_session.commit()
    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    login(client, username, ADMIN_PASSWORD)
    return client


def _unauthenticated_client(db_session):
    """TestClient with no session cookie."""
    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import create_app

    app = create_app()

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _audit_row(db_session, action: str, resource_type: str = "booking",
               resource_id: str = "b1", actor_user_id=None, metadata=None,
               ip_address: str = "127.0.0.1", created_at=None) -> None:
    """Insert a raw audit row via the ORM (bypasses write_audit for test speed)."""
    import uuid

    from app.models.audit import AuditLog

    if created_at is None:
        created_at = datetime.now(UTC)

    row = AuditLog(
        id=uuid.uuid4(),
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata,
        ip_address=ip_address,
        created_at=created_at,
    )
    db_session.add(row)
    db_session.commit()


def _admin_client(db_session):
    """Logged-in ADMIN client. Note: login() creates one AUTH_LOGIN audit row."""
    return _new_client(db_session, "admin1", "ADMIN")


def _login_offset() -> int:
    """Number of audit rows created by a single login() call (AUTH_LOGIN)."""
    return 1


def test_admin_can_read_audit_logs(db_session) -> None:
    """ADMIN can list audit records via the read API."""
    client = _admin_client(db_session)
    _audit_row(db_session, "USER_CREATED", "user", "u1", metadata={"username": "newuser"})
    _audit_row(db_session, "BOOKING_CREATED", "booking", "b1")

    resp = client.get("/api/v1/audit-logs")
    assert resp.status_code == 200
    data = resp.json()
    # 2 test rows + 1 AUTH_LOGIN from login()
    assert data["total"] == 2 + _login_offset()
    assert len(data["items"]) == 2 + _login_offset()
    # My two rows should be the first two (newest first, and they're newer than login)
    test_actions = [i["action"] for i in data["items"] if i["action"] != "AUTH_LOGIN"]
    assert test_actions[0] == "BOOKING_CREATED"
    assert test_actions[1] == "USER_CREATED"


def test_receptionist_cannot_read_audit_logs(db_session) -> None:
    """RECEPTIONIST receives 403 when calling the audit read endpoint directly."""
    client = _new_client(db_session, "rec1", "RECEPTIONIST")
    resp = client.get("/api/v1/audit-logs")
    assert resp.status_code == 403


def test_unauthenticated_cannot_read_audit_logs(db_session) -> None:
    """Requests with no session cookie are rejected with 401."""
    client = _unauthenticated_client(db_session)

    resp = client.get("/api/v1/audit-logs")
    assert resp.status_code == 401


def test_audit_logs_ordered_newest_first(db_session) -> None:
    """Records are returned in reverse chronological order."""
    client = _admin_client(db_session)
    now = datetime.now(UTC)
    _audit_row(db_session, "ACTION_OLD", "booking", "b1",
               created_at=now - timedelta(hours=2))
    _audit_row(db_session, "ACTION_NEW", "booking", "b2",
               created_at=now - timedelta(hours=1))

    resp = client.get("/api/v1/audit-logs")
    assert resp.status_code == 200
    data = resp.json()
    # AUTH_LOGIN from login() is at `now` (during _new_client), which is
    # newer than both test rows, so it should be first.
    assert data["items"][0]["action"] == "AUTH_LOGIN"
    assert data["items"][1]["action"] == "ACTION_NEW"
    assert data["items"][2]["action"] == "ACTION_OLD"


def test_audit_logs_pagination(db_session) -> None:
    """Pagination returns the correct page and total."""
    client = _admin_client(db_session)
    for i in range(7):
        _audit_row(db_session, f"ACTION_{i}", "booking", f"b{i}")

    total_expected = 7 + _login_offset()
    resp = client.get("/api/v1/audit-logs?page=1&page_size=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == total_expected
    assert data["page"] == 1
    assert data["page_size"] == 3
    assert len(data["items"]) == 3

    resp = client.get("/api/v1/audit-logs?page=3&page_size=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 3
    # total_expected = 8, page_size = 3, page 3 = items 7-8 → 2 items
    assert len(data["items"]) == 2


def test_audit_logs_max_page_size_enforced(db_session) -> None:
    """page_size above 100 is rejected with 422 by FastAPI query validation."""
    client = _admin_client(db_session)
    _audit_row(db_session, "ACTION_1", "booking", "b1")

    resp = client.get("/api/v1/audit-logs?page_size=200")
    assert resp.status_code == 422  # FastAPI le=100 validation


def test_audit_logs_date_filter(db_session) -> None:
    """from_date/to_date filter records by created_at."""
    client = _admin_client(db_session)
    yesterday = datetime.now(UTC) - timedelta(days=1)
    today = datetime.now(UTC)

    _audit_row(db_session, "ACTION_YESTERDAY", "booking", "b1", created_at=yesterday)
    _audit_row(db_session, "ACTION_TODAY", "booking", "b2", created_at=today)

    today_str = today.strftime("%Y-%m-%d")
    resp = client.get(f"/api/v1/audit-logs?from_date={today_str}")
    assert resp.status_code == 200
    data = resp.json()
    # AUTH_LOGIN from login() happened at roughly `now` which is today
    assert data["total"] == 1 + _login_offset()
    today_actions = [i["action"] for i in data["items"] if i["action"] == "ACTION_TODAY"]
    assert len(today_actions) == 1


def test_audit_logs_invalid_date_range_rejected(db_session) -> None:
    """from_date after to_date returns 422."""
    client = _admin_client(db_session)
    resp = client.get("/api/v1/audit-logs?from_date=2026-01-31&to_date=2026-01-01")
    assert resp.status_code == 422


def test_audit_logs_actor_filter(db_session) -> None:
    """Filter by actor username (case-insensitive substring)."""
    client = _admin_client(db_session)
    import uuid
    admin_user = User(
        id=uuid.uuid4(), username="AliceAdmin", full_name="Alice Admin",
        role="ADMIN", is_active=True, password_hash="x"
    )
    db_session.add(admin_user)
    db_session.commit()

    _audit_row(db_session, "ACTION_BY_ALICE", "booking", "b1", actor_user_id=admin_user.id)
    _audit_row(db_session, "ACTION_BY_OTHER", "booking", "b2")

    resp = client.get("/api/v1/audit-logs?actor=alice")
    assert resp.status_code == 200
    data = resp.json()
    # AUTH_LOGIN actor is "admin1" which doesn't match "alice"
    assert data["total"] == 1
    assert data["items"][0]["action"] == "ACTION_BY_ALICE"
    assert data["items"][0]["actor_username"] == "AliceAdmin"


def test_audit_logs_action_filter(db_session) -> None:
    """Filter by action name (case-insensitive substring)."""
    client = _admin_client(db_session)
    _audit_row(db_session, "USER_CREATED", "user", "u1")
    _audit_row(db_session, "BOOKING_CREATED", "booking", "b1")

    resp = client.get("/api/v1/audit-logs?action=user_created")
    assert resp.status_code == 200
    data = resp.json()
    # AUTH_LOGIN doesn't match "user_created" substring
    assert data["total"] == 1
    assert data["items"][0]["action"] == "USER_CREATED"


def test_audit_logs_resource_filter(db_session) -> None:
    """Filter by resource type and resource ID."""
    client = _admin_client(db_session)
    _audit_row(db_session, "BOOKING_CREATED", "booking", "b1")
    _audit_row(db_session, "ROOM_UPDATED", "room", "r1")

    resp = client.get("/api/v1/audit-logs?resource_type=booking")
    assert resp.status_code == 200
    data = resp.json()
    # AUTH_LOGIN has resource_type="user" so doesn't match "booking"
    assert data["total"] == 1
    assert data["items"][0]["resource_type"] == "booking"

    resp = client.get("/api/v1/audit-logs?resource_id=r1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["resource_id"] == "r1"


def test_audit_logs_empty_results(db_session) -> None:
    """Empty audit log returns zero items (excluding login's AUTH_LOGIN)."""
    client = _admin_client(db_session)
    # AUTH_LOGIN from login() is the only record
    resp = client.get("/api/v1/audit-logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == _login_offset()
    assert len(data["items"]) == _login_offset()


def test_audit_logs_sensitive_metadata_redacted(db_session) -> None:
    """Secret-like metadata keys are redacted in the API response."""
    client = _admin_client(db_session)
    _audit_row(db_session, "SECRET_TEST", "booking", "b1",
               metadata={"password": "hunter2", "api_key": "sk-123", "safe_field": "ok"})

    resp = client.get("/api/v1/audit-logs")
    assert resp.status_code == 200
    data = resp.json()
    entry = [i for i in data["items"] if i["action"] == "SECRET_TEST"][0]
    assert entry["metadata"]["password"] == "[REDACTED]"
    assert entry["metadata"]["api_key"] == "[REDACTED]"
    assert entry["metadata"]["safe_field"] == "ok"


def test_audit_logs_no_write_endpoints(db_session) -> None:
    """Audit history is append-only: POST/PATCH/DELETE are not available."""
    client = _admin_client(db_session)

    # POST to collection endpoint: method not allowed (only GET exists)
    resp = client.post("/api/v1/audit-logs", json={})
    assert resp.status_code == 405

    # PATCH/DELETE to an individual record route: no such route exists -> 404
    resp = client.patch("/api/v1/audit-logs/00000000-0000-0000-0000-000000000000", json={})
    assert resp.status_code == 404

    resp = client.delete("/api/v1/audit-logs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_room_type_creation_audit_metadata(db_session) -> None:
    """Room category creation writes complete metadata (no PII)."""
    client = _admin_client(db_session)

    resp = client.post(
        "/api/v1/admin/room-types",
        json={
            "name": "Deluxe",
            "description": "Spacious room with garden view",
            "maximum_occupancy": 4,
            "amenities": "Wi-Fi, TV, minibar",
            "display_order": 1,
        },
        headers=csrf_headers(client),
    )
    assert resp.status_code == 201

    rows = db_session.scalars(select(AuditLog).where(AuditLog.action == "ROOM_TYPE_CREATED")).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.resource_type == "room_type"
    meta = row.metadata_json or {}
    assert meta["name"] == "Deluxe"
    assert meta["description"] == "Spacious room with garden view"
    assert meta["maximum_occupancy"] == 4
    assert meta["amenities"] == "Wi-Fi, TV, minibar"
    assert meta["display_order"] == 1


def test_room_creation_audit_metadata(db_session) -> None:
    """Room creation writes complete metadata (no PII)."""
    client = _admin_client(db_session)

    # First create a room type
    rt = client.post(
        "/api/v1/admin/room-types",
        json={
            "name": "Standard",
            "description": "Standard room",
            "maximum_occupancy": 2,
            "amenities": None,
            "display_order": 0,
        },
        headers=csrf_headers(client),
    )
    assert rt.status_code == 201
    room_type_id = rt.json()["id"]

    # Then create a room
    resp = client.post(
        "/api/v1/admin/rooms",
        json={
            "room_number": "101",
            "room_type_id": str(room_type_id),
            "floor": 1,
            "description": "First floor standard room",
            "maximum_occupancy": 2,
        },
        headers=csrf_headers(client),
    )
    assert resp.status_code == 201

    rows = db_session.scalars(select(AuditLog).where(AuditLog.action == "ROOM_CREATED")).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.resource_type == "room"
    meta = row.metadata_json or {}
    assert meta["room_number"] == "101"
    assert meta["floor"] == 1
    assert meta["description"] == "First floor standard room"
    assert meta["maximum_occupancy"] == 2


def test_tax_settings_creation_audit_metadata(db_session) -> None:
    """Tax settings creation writes complete metadata (no PII)."""
    client = _admin_client(db_session)

    resp = client.post(
        "/api/v1/admin/tax-settings",
        json={
            "registration_status": "REGISTERED",
            "tax_type": "GST",
            "tax_rate": "18.00",
            "pricing_mode": "EXCLUSIVE",
            "valid_from": "2026-01-01",
            "valid_until": None,
            "notes": None,
        },
        headers=csrf_headers(client),
    )
    assert resp.status_code == 201

    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "TAX_SETTINGS_CREATED")
    ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.resource_type == "tax_settings"
    meta = row.metadata_json or {}
    assert meta["registration_status"] == "REGISTERED"
    assert meta["tax_type"] == "GST"
    assert meta["tax_rate"] == "18.00"
    assert meta["pricing_mode"] == "EXCLUSIVE"
    assert meta["valid_from"] == "2026-01-01"
    assert meta["valid_until"] is None


def test_duplicate_room_type_does_not_leak_audit_entry(db_session) -> None:
    """Failed room type creation (duplicate name) leaves no audit entry."""
    client = _admin_client(db_session)

    # Create first room type
    client.post(
        "/api/v1/admin/room-types",
        json={
            "name": "Deluxe",
            "description": "First deluxe",
            "maximum_occupancy": 2,
            "amenities": None,
            "display_order": 0,
        },
        headers=csrf_headers(client),
    )

    # Attempt duplicate — should fail
    resp = client.post(
        "/api/v1/admin/room-types",
        json={
            "name": "Deluxe",
            "description": "Duplicate",
            "maximum_occupancy": 3,
            "amenities": None,
            "display_order": 1,
        },
        headers=csrf_headers(client),
    )
    assert resp.status_code == 409

    # Only one ROOM_TYPE_CREATED audit entry should exist
    rows = db_session.scalars(select(AuditLog).where(AuditLog.action == "ROOM_TYPE_CREATED")).all()
    assert len(rows) == 1
    assert rows[0].metadata_json["name"] == "Deluxe"
    assert rows[0].metadata_json["description"] == "First deluxe"
