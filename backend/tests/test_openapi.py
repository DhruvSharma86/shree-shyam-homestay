"""OpenAPI contract regression tests (Remediation Milestone 2)."""

from app.main import create_app


def _openapi() -> dict:
    return create_app().openapi()


def _schema(name: str) -> dict:
    return _openapi()["components"]["schemas"][name]


def test_payment_create_documents_accepted_modes_and_stages():
    """PaymentCreate.mode / payment_stage are enums, not free strings."""
    payment_create = _schema("PaymentCreate")
    props = payment_create["properties"]
    assert set(props["mode"]["enum"]) == {"CASH", "UPI", "CARD_POS"}
    assert set(props["payment_stage"]["enum"]) == {"ADVANCE", "CHECK_IN", "CHECKOUT", "OTHER"}
    assert props["mode"].get("default") == "CASH"
    assert props["payment_stage"].get("default") == "OTHER"


def test_payment_response_documents_accepted_values():
    payment = _schema("PaymentResponse")
    props = payment["properties"]
    assert set(props["mode"]["enum"]) == {"CASH", "UPI", "CARD_POS"}
    assert set(props["payment_stage"]["enum"]) == {"ADVANCE", "CHECK_IN", "CHECKOUT", "OTHER"}


def test_staff_receipt_download_documents_pdf():
    paths = _openapi()["paths"]
    op = paths["/api/v1/bookings/{booking_id}/receipt/download"]["get"]
    content = op["responses"]["200"]["content"]
    assert "application/pdf" in content


def test_guest_receipt_download_documents_pdf():
    paths = _openapi()["paths"]
    op = paths["/api/v1/guest-portal/{token}/receipt/download"]["get"]
    content = op["responses"]["200"]["content"]
    assert "application/pdf" in content


def test_portal_revoke_example_shows_inactive():
    paths = _openapi()["paths"]
    op = paths["/api/v1/guest-portal/admin-revoke/{booking_id}"]["post"]
    example = op["responses"]["200"]["content"]["application/json"]["example"]
    assert example["active"] is False
    assert example["issued"] is False
