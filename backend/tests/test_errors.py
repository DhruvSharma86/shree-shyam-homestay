"""Tests for the API error response format."""

from fastapi.testclient import TestClient

from app.core.errors import ApiError, error_payload


def test_error_payload_shape() -> None:
    """error_payload produces the documented envelope."""
    body = error_payload("NOT_FOUND", "Missing.", {"id": "x"})
    assert body == {"error": {"code": "NOT_FOUND", "message": "Missing.", "details": {"id": "x"}}}


def test_error_payload_omits_empty_details() -> None:
    """details is omitted when None/empty."""
    body = error_payload("BAD_REQUEST", "Nope.")
    assert "details" not in body["error"]


def test_api_error_exception_renders_envelope(client: TestClient) -> None:
    """ApiError raised in a handler renders the standard envelope."""

    app = client.app

    @app.get("/_test/api-error")
    def _raise() -> None:
        raise ApiError(409, "BOOKING_OVERLAP", "Room already booked.", {"room": "101"})

    response = client.get("/_test/api-error")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "BOOKING_OVERLAP"
    assert body["error"]["details"] == {"room": "101"}


def test_validation_error_envelope(client: TestClient) -> None:
    """Request validation failures return 422 with the standard envelope."""
    from pydantic import BaseModel

    app = client.app

    class _Body(BaseModel):
        name: str

    @app.post("/_test/validate")
    def _validate(body: _Body) -> dict:
        return {"name": body.name}

    response = client.post("/_test/validate", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "errors" in body["error"]["details"]
