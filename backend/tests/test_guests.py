"""Guest registration tests — CRUD, validation, RBAC, duplicates, audit."""

import pytest
from sqlalchemy import select

from app.guests.service import normalize_phone
from app.models.audit import AuditLog
from tests.factories import ADMIN_PASSWORD, create_user, csrf_headers, login


@pytest.fixture()
def admin_client(client, db_session):
    """Logged-in ADMIN client."""
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)
    return client


@pytest.fixture()
def receptionist_client(client, db_session):
    """Logged-in RECEPTIONIST client."""
    create_user(db_session, username="rec1", role="RECEPTIONIST")
    db_session.commit()
    login(client, "rec1", ADMIN_PASSWORD)
    return client


def _payload(**overrides):
    base = {"full_name": "Asha Kumar", "phone": "9876543210"}
    base.update(overrides)
    return base


# --- Phone normalization -------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9876543210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("+919876543210", "+919876543210"),
        ("0091 98765 43210", "+919876543210"),
        ("+91-98765-43210", "+919876543210"),
        ("(+91) 98765 43210", "+919876543210"),
        ("+1 (415) 555-0132", "+14155550132"),
    ],
)
def test_normalize_phone_forms(raw, expected) -> None:
    """All agreed Indian input forms normalize to E.164."""
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "123", "abcdefghij", "+0 12345678901", "12345678901234567890"])
def test_normalize_phone_rejects(raw) -> None:
    """Malformed numbers are rejected, never silently accepted."""
    from app.guests.service import InvalidPhoneError

    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


# --- Create / retrieve / list / search -----------------------------------


def test_create_guest_success(admin_client) -> None:
    """Successful registration normalizes phone and returns 201."""
    r = admin_client.post(
        "/api/v1/guests", json=_payload(phone="09876 543210"), headers=csrf_headers(admin_client)
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["full_name"] == "Asha Kumar"
    assert body["phone"] == "+919876543210"
    assert body["is_active"] is True


def test_create_guest_required_fields(admin_client) -> None:
    """Missing name/phone → 422."""
    assert (
        admin_client.post(
            "/api/v1/guests", json={"phone": "9876543210"}, headers=csrf_headers(admin_client)
        ).status_code
        == 422
    )
    assert (
        admin_client.post(
            "/api/v1/guests", json={"full_name": "X"}, headers=csrf_headers(admin_client)
        ).status_code
        == 422
    )


def test_create_guest_invalid_phone(admin_client) -> None:
    """Malformed phone → 422."""
    r = admin_client.post(
        "/api/v1/guests", json=_payload(phone="abc"), headers=csrf_headers(admin_client)
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_guest(admin_client) -> None:
    """Retrieve by ID."""
    created = admin_client.post(
        "/api/v1/guests", json=_payload(), headers=csrf_headers(admin_client)
    ).json()
    r = admin_client.get(f"/api/v1/guests/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_missing_guest_404(admin_client) -> None:
    """Unknown id → 404."""
    r = admin_client.get("/api/v1/guests/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_list_and_pagination(receptionist_client) -> None:
    """List returns data + total; page_size limits results."""
    for i in range(5):
        receptionist_client.post(
            "/api/v1/guests",
            json=_payload(full_name=f"Guest {i}", phone=f"98765432{i:02d}"),
            headers=csrf_headers(receptionist_client),
        )
    r = receptionist_client.get("/api/v1/guests?page=1&page_size=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    page2 = receptionist_client.get("/api/v1/guests?page=2&page_size=2").json()
    assert len(page2["items"]) == 2


def test_search_by_name_and_phone(receptionist_client) -> None:
    """Search matches name substring and normalized phone."""
    receptionist_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Rohan Sharma", phone="9812345678"),
        headers=csrf_headers(receptionist_client),
    )
    by_name = receptionist_client.get("/api/v1/guests?q=rohan").json()
    assert by_name["total"] == 1 and by_name["items"][0]["full_name"] == "Rohan Sharma"
    by_phone = receptionist_client.get("/api/v1/guests?q=+919812345678").json()
    assert by_phone["total"] == 1
    partial_phone = receptionist_client.get("/api/v1/guests?q=981234").json()
    assert partial_phone["total"] == 1
    miss = receptionist_client.get("/api/v1/guests?q=nobody-here").json()
    assert miss["total"] == 0


# --- Duplicate handling --------------------------------------------------


def test_exact_duplicate_rejected_409(admin_client) -> None:
    """Same name (any case/spacing) + same phone → 409 with existing id."""
    first = admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Meena Iyer", phone="9876500001"),
        headers=csrf_headers(admin_client),
    ).json()
    r = admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="  meena  IYER ", phone="+919876500001"),
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 409
    assert r.json()["error"]["details"]["existing_guest_id"] == first["id"]


def test_same_phone_different_name_allowed(admin_client) -> None:
    """Family sharing a phone: different name is a different guest."""
    admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Anil Rao", phone="9876500002"),
        headers=csrf_headers(admin_client),
    )
    r = admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Sunita Rao", phone="09876500002"),
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 201


def test_same_name_different_phone_allowed(admin_client) -> None:
    """Same name with a different phone is not a duplicate."""
    admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Anil Rao", phone="9876500003"),
        headers=csrf_headers(admin_client),
    )
    r = admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Anil Rao", phone="9876500004"),
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 201


# --- Update / deactivate -------------------------------------------------


def test_update_guest(admin_client) -> None:
    """PATCH updates permitted fields."""
    created = admin_client.post(
        "/api/v1/guests", json=_payload(), headers=csrf_headers(admin_client)
    ).json()
    r = admin_client.patch(
        f"/api/v1/guests/{created['id']}",
        json={"full_name": "Asha Reddy", "email": "asha@example.com"},
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Asha Reddy"
    assert r.json()["email"] == "asha@example.com"


def test_update_phone_to_duplicate_409(admin_client) -> None:
    """PATCH phone into another guest's name+phone → 409."""
    a = admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Gita Nair", phone="9876500010"),
        headers=csrf_headers(admin_client),
    ).json()
    b = admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Gita Nair", phone="9876500011"),
        headers=csrf_headers(admin_client),
    ).json()
    r = admin_client.patch(
        f"/api/v1/guests/{b['id']}",
        json={"phone": "9876500010"},
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 409
    assert r.json()["error"]["details"]["existing_guest_id"] == a["id"]


def test_patch_rejects_is_active(admin_client) -> None:
    """PATCH must not bypass the deactivate endpoint."""
    created = admin_client.post(
        "/api/v1/guests", json=_payload(), headers=csrf_headers(admin_client)
    ).json()
    r = admin_client.patch(
        f"/api/v1/guests/{created['id']}",
        json={"is_active": False},
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 422


def test_deactivate_idempotent(admin_client) -> None:
    """Deactivation is idempotent and guest remains retrievable."""
    created = admin_client.post(
        "/api/v1/guests", json=_payload(), headers=csrf_headers(admin_client)
    ).json()
    d = admin_client.post(
        f"/api/v1/guests/{created['id']}/deactivate", headers=csrf_headers(admin_client)
    )
    assert d.status_code == 200 and d.json()["is_active"] is False
    d2 = admin_client.post(
        f"/api/v1/guests/{created['id']}/deactivate", headers=csrf_headers(admin_client)
    )
    assert d2.status_code == 200
    assert admin_client.get(f"/api/v1/guests/{created['id']}").status_code == 200


def test_reregistration_after_deactivation(admin_client) -> None:
    """Inactive guest does not block re-registration (active-only rule)."""
    admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Re One", phone="9876500020"),
        headers=csrf_headers(admin_client),
    )
    created = admin_client.get("/api/v1/guests?q=Re+One").json()["items"][0]
    admin_client.post(
        f"/api/v1/guests/{created['id']}/deactivate", headers=csrf_headers(admin_client)
    )
    r = admin_client.post(
        "/api/v1/guests",
        json=_payload(full_name="Re One", phone="9876500020"),
        headers=csrf_headers(admin_client),
    )
    assert r.status_code == 201


def test_deactivated_hidden_from_default_list(admin_client) -> None:
    """Default list excludes inactive; include_inactive=true shows it."""
    created = admin_client.post(
        "/api/v1/guests", json=_payload(), headers=csrf_headers(admin_client)
    ).json()
    admin_client.post(
        f"/api/v1/guests/{created['id']}/deactivate", headers=csrf_headers(admin_client)
    )
    default = admin_client.get("/api/v1/guests").json()
    assert default["total"] == 0
    all_guests = admin_client.get("/api/v1/guests?include_inactive=true").json()
    assert all_guests["total"] == 1


# --- Authorization -------------------------------------------------------


def test_unauthenticated_guest_endpoints(client) -> None:
    """No session → 401 on every guest endpoint."""
    assert client.get("/api/v1/guests").status_code == 401
    assert client.post("/api/v1/guests", json=_payload()).status_code == 401
    assert client.get("/api/v1/guests/00000000-0000-0000-0000-000000000000").status_code == 401


def test_receptionist_can_register_and_read(receptionist_client) -> None:
    """Receptionist operational flow: create, list, get, update, deactivate."""
    created = receptionist_client.post(
        "/api/v1/guests", json=_payload(), headers=csrf_headers(receptionist_client)
    )
    assert created.status_code == 201
    gid = created.json()["id"]
    assert receptionist_client.get("/api/v1/guests").status_code == 200
    assert receptionist_client.get(f"/api/v1/guests/{gid}").status_code == 200
    upd = receptionist_client.patch(
        f"/api/v1/guests/{gid}",
        json={"full_name": "Asha R"},
        headers=csrf_headers(receptionist_client),
    )
    assert upd.status_code == 200
    deact = receptionist_client.post(
        f"/api/v1/guests/{gid}/deactivate", headers=csrf_headers(receptionist_client)
    )
    assert deact.status_code == 200


def test_admin_can_register_and_read(admin_client) -> None:
    """ADMIN has full guest access."""
    created = admin_client.post(
        "/api/v1/guests", json=_payload(), headers=csrf_headers(admin_client)
    )
    assert created.status_code == 201
    assert admin_client.get("/api/v1/guests").status_code == 200


# --- Audit ----------------------------------------------------------------


def test_guest_mutations_audited_without_pii(admin_client, db_session) -> None:
    """Create/update/deactivate write audit rows with no PII in metadata."""
    created = admin_client.post(
        "/api/v1/guests", json=_payload(), headers=csrf_headers(admin_client)
    ).json()
    admin_client.patch(
        f"/api/v1/guests/{created['id']}",
        json={"full_name": "Asha R"},
        headers=csrf_headers(admin_client),
    )
    admin_client.post(
        f"/api/v1/guests/{created['id']}/deactivate", headers=csrf_headers(admin_client)
    )
    rows = db_session.scalars(select(AuditLog).where(AuditLog.action.like("GUEST_%"))).all()
    actions = {r.action for r in rows}
    assert {"GUEST_CREATED", "GUEST_UPDATED", "GUEST_DEACTIVATED"} <= actions
    blob = " ".join(str(r.metadata_json or "") for r in rows)
    assert "Asha" not in blob
    assert "9876543210" not in blob
    assert "+919876543210" not in blob


def test_guest_csrf_required(admin_client) -> None:
    """Mutations without CSRF → 403."""
    r = admin_client.post("/api/v1/guests", json=_payload())
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_FAILED"


def test_concurrent_duplicate_db_guard(db_session) -> None:
    """DB partial unique index blocks a second active row even bypassing service checks."""
    from sqlalchemy.exc import IntegrityError

    from app.models.guest import Guest

    db_session.add(Guest(full_name="Race Guest", phone="+919876543299", is_active=True))
    db_session.commit()
    db_session.add(Guest(full_name="race guest", phone="+919876543299", is_active=True))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
