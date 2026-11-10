"""Booking occupancy-capacity tests (Remediation Milestone 3)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from tests.factories import ADMIN_PASSWORD, create_user, csrf_headers, login


def _today() -> date:
    return datetime.now(UTC).date()


@pytest.fixture()
def admin_client(client, db_session):
    create_user(db_session, username="admin1")
    db_session.commit()
    login(client, "admin1", ADMIN_PASSWORD)
    return client


@pytest.fixture()
def room_type_id(admin_client) -> str:
    return admin_client.post(
        "/api/v1/admin/room-types", json={"name": "Deluxe"}, headers=csrf_headers(admin_client)
    ).json()["id"]


def _make_room(admin_client, room_type_id, number, max_occ):
    return admin_client.post(
        "/api/v1/admin/rooms",
        json={"room_number": number, "room_type_id": room_type_id, "maximum_occupancy": max_occ},
        headers=csrf_headers(admin_client),
    ).json()["id"]


def _rate(admin_client, room_type_id, start):
    end = start + timedelta(days=365)
    return admin_client.post(
        "/api/v1/admin/room-rates",
        json={
            "room_type_id": room_type_id,
            "nightly_rate": "2500.00",
            "valid_from": start.isoformat(),
            "valid_until": end.isoformat(),
        },
        headers=csrf_headers(admin_client),
    )


def _guest(admin_client) -> str:
    return admin_client.post(
        "/api/v1/guests",
        json={"full_name": "Occ Guest", "phone": "+919876543210"},
        headers=csrf_headers(admin_client),
    ).json()["id"]


def _book(admin_client, room_type_id, room_id, guest_id, guests, offset=1, nights=2):
    start = _today() + timedelta(days=offset)
    end = start + timedelta(days=nights)
    _rate(admin_client, room_type_id, start)
    return admin_client.post(
        "/api/v1/bookings",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "source": "PHONE",
            "check_in_date": start.isoformat(),
            "check_out_date": end.isoformat(),
            "number_of_guests": guests,
        },
        headers=csrf_headers(admin_client),
    )


def test_exact_occupancy_accepted(admin_client, room_type_id):
    room_id = _make_room(admin_client, room_type_id, "OCC-2A", 2)
    guest_id = _guest(admin_client)
    r = _book(admin_client, room_type_id, room_id, guest_id, 2)
    assert r.status_code == 201, r.text


def test_over_capacity_rejected(admin_client, room_type_id):
    room_id = _make_room(admin_client, room_type_id, "OCC-2B", 2)
    guest_id = _guest(admin_client)
    r = _book(admin_client, room_type_id, room_id, guest_id, 3)
    assert r.status_code == 422, r.text
    assert "accommodates at most 2" in r.text


def test_individual_override_respected(admin_client, room_type_id):
    room_id = _make_room(admin_client, room_type_id, "OCC-3A", 3)
    guest_id = _guest(admin_client)
    r = _book(admin_client, room_type_id, room_id, guest_id, 3)
    assert r.status_code == 201, r.text


def test_individual_override_enforced(admin_client, room_type_id):
    room_id = _make_room(admin_client, room_type_id, "OCC-3B", 3)
    guest_id = _guest(admin_client)
    r = _book(admin_client, room_type_id, room_id, guest_id, 4)
    assert r.status_code == 422, r.text
    assert "accommodates at most 3" in r.text


def test_guest_count_bounds_preserved(admin_client, room_type_id):
    room_id = _make_room(admin_client, room_type_id, "OCC-2C", 2)
    guest_id = _guest(admin_client)
    start = _today() + timedelta(days=1)
    end = start + timedelta(days=2)
    _rate(admin_client, room_type_id, start)
    for n in (0, -1, 21):
        r = admin_client.post(
            "/api/v1/bookings",
            json={
                "guest_id": guest_id,
                "room_id": room_id,
                "source": "PHONE",
                "check_in_date": start.isoformat(),
                "check_out_date": end.isoformat(),
                "number_of_guests": n,
            },
            headers=csrf_headers(admin_client),
        )
        assert r.status_code == 422, (n, r.text)


def test_occupancy_update_rejected(admin_client, room_type_id):
    room_id = _make_room(admin_client, room_type_id, "OCC-2D", 2)
    guest_id = _guest(admin_client)
    r = _book(admin_client, room_type_id, room_id, guest_id, 2)
    assert r.status_code == 201
    booking_id = r.json()["id"]
    rp = admin_client.patch(
        f"/api/v1/bookings/{booking_id}",
        json={"number_of_guests": 3},
        headers=csrf_headers(admin_client),
    )
    assert rp.status_code == 422, rp.text
    assert "accommodates at most 2" in rp.text


def test_occupancy_room_change_rejected(admin_client, room_type_id):
    room_small = _make_room(admin_client, room_type_id, "OCC-SMALL", 1)
    room_big = _make_room(admin_client, room_type_id, "OCC-BIG", 3)
    guest_id = _guest(admin_client)
    r = _book(admin_client, room_type_id, room_big, guest_id, 3, offset=1)
    assert r.status_code == 201
    booking_id = r.json()["id"]
    rp = admin_client.patch(
        f"/api/v1/bookings/{booking_id}",
        json={"room_id": room_small},
        headers=csrf_headers(admin_client),
    )
    assert rp.status_code == 422, rp.text
    assert "accommodates at most 1" in rp.text
