from rest_framework.permissions import BasePermission

from .models import Role


class HasTenantMembership(BasePermission):
    def has_permission(self, request, view):
        return getattr(request._request, "membership", None) is not None


def has_role(*roles):
    """Permission factory: allow the active membership roles (owner/admin always pass)."""
    allowed = {Role.OWNER, Role.ADMIN, *roles}

    class _HasRole(BasePermission):
        def has_permission(self, request, view):
            membership = getattr(request._request, "membership", None)
            return membership is not None and membership.role in allowed

    _HasRole.__name__ = "HasRole_" + "_".join(sorted(str(r) for r in roles))
    return _HasRole


class HasFeature(BasePermission):
    """Views set `required_feature` to gate access by tenant plan entitlements."""

    def has_permission(self, request, view):
        tenant = getattr(request._request, "tenant", None)
        feature = getattr(view, "required_feature", None)
        return tenant is not None and (feature is None or tenant.has_feature(feature))
