"""Unit tests for the default-deny permission mapping."""

from app.core.permissions import Permission, permissions_for_role, role_has_permission


def test_admin_has_every_permission() -> None:
    """ADMIN is granted the full permission set."""
    assert permissions_for_role("ADMIN") == frozenset(Permission)


def test_receptionist_has_operational_subset_only() -> None:
    """RECEPTIONIST gets operations + self-service, never admin settings."""
    perms = permissions_for_role("RECEPTIONIST")
    assert Permission.BOOKINGS_WRITE in perms
    assert Permission.BILLING_PAYMENTS_WRITE in perms
    assert Permission.PROFILE_READ in perms
    assert Permission.USERS_MANAGE not in perms
    assert Permission.PRICING_MANAGE not in perms
    assert Permission.REPORTS_FINANCIAL_READ not in perms
    assert Permission.AUDIT_READ not in perms
    assert Permission.TAX_MANAGE not in perms
    assert Permission.HOTEL_MANAGE not in perms


def test_unknown_role_denied_everything() -> None:
    """Unrecognised roles receive an empty permission set (default-deny)."""
    assert permissions_for_role("SUPERUSER") == frozenset()
    assert role_has_permission("SUPERUSER", Permission.USERS_MANAGE) is False
    assert role_has_permission("", Permission.PROFILE_READ) is False
