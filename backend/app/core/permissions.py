"""Permission identifiers and the default-deny role→permission mapping.

Every permission in the system is listed here explicitly. A role grants a
permission **only** if it appears in its set — anything not listed is denied
(default-deny). Adding a permission in a later phase means adding it here
first, then granting it to roles deliberately. See ``docs/RBAC.md``.
"""

import enum


class Permission(enum.StrEnum):
    """All permission identifiers used by the API."""

    # Users & administration (ADMIN only)
    USERS_MANAGE = "users.manage"
    USERS_RESET_CREDENTIALS = "users.reset_credentials"

    # Hotel configuration (ADMIN only)
    HOTEL_MANAGE = "hotel.manage"
    ROOMS_MANAGE = "rooms.manage"
    PRICING_MANAGE = "pricing.manage"
    TAX_MANAGE = "tax.manage"
    CONTENT_MANAGE = "content.manage"

    # Guests (both roles, operational)
    GUESTS_READ = "guests.read"
    GUESTS_WRITE = "guests.write"

    # Bookings (both roles, operational)
    BOOKINGS_READ = "bookings.read"
    BOOKINGS_WRITE = "bookings.write"
    BOOKINGS_CHECKIN = "bookings.checkin"
    BOOKINGS_CHECKOUT = "bookings.checkout"
    BOOKINGS_CANCEL = "bookings.cancel"

    # Billing (both roles, operational)
    BILLING_CHARGES_WRITE = "billing.charges.write"
    BILLING_PAYMENTS_WRITE = "billing.payments.write"
    BILLING_DISCOUNTS_WRITE = "billing.discounts.write"
    BILLING_RECEIPTS_READ = "billing.receipts.read"

    # Reports & audit (ADMIN only)
    REPORTS_FINANCIAL_READ = "reports.financial.read"
    AUDIT_READ = "audit.read"

    # Guest portal administration (ADMIN only)
    PORTAL_TOKENS_MANAGE = "portal.tokens.manage"

    # Self-service (both roles)
    PROFILE_READ = "profile.read"
    PROFILE_WRITE = "profile.write"


_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(Permission)

_RECEPTIONIST_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.PROFILE_READ,
        Permission.PROFILE_WRITE,
        Permission.GUESTS_READ,
        Permission.GUESTS_WRITE,
        Permission.BOOKINGS_READ,
        Permission.BOOKINGS_WRITE,
        Permission.BOOKINGS_CHECKIN,
        Permission.BOOKINGS_CHECKOUT,
        Permission.BOOKINGS_CANCEL,
        Permission.BILLING_CHARGES_WRITE,
        Permission.BILLING_PAYMENTS_WRITE,
        # BILLING_DISCOUNTS_WRITE is ADMIN-only (D4, Phase 4.1): receptionists
        # never receive it, so discount endpoints deny them by default.
        Permission.BILLING_RECEIPTS_READ,
    }
)


def permissions_for_role(role: str) -> frozenset[Permission]:
    """Return the permission set granted to ``role``.

    Unknown roles get an empty set (default-deny).
    """
    name = str(role).upper()
    if name == "ADMIN":
        return _ADMIN_PERMISSIONS
    if name == "RECEPTIONIST":
        return _RECEPTIONIST_PERMISSIONS
    return frozenset()


def role_has_permission(role: str, permission: Permission) -> bool:
    """Return True when ``role`` is explicitly granted ``permission``."""
    return permission in permissions_for_role(role)
