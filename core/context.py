"""Request/job-scoped tenant context shared by the ORM layer, API and background jobs."""

from contextlib import contextmanager
from contextvars import ContextVar

_current_tenant: ContextVar = ContextVar("current_tenant", default=None)


class TenantContextMissing(RuntimeError):
    """Raised when tenant-scoped data is accessed without an active tenant."""


def get_current_tenant():
    return _current_tenant.get()


def require_current_tenant():
    tenant = _current_tenant.get()
    if tenant is None:
        raise TenantContextMissing(
            "No active tenant. Wrap the code in tenant_context() or use all_tenants "
            "explicitly for platform-level work."
        )
    return tenant


def set_current_tenant(tenant):
    return _current_tenant.set(tenant)


def reset_current_tenant(token):
    _current_tenant.reset(token)


@contextmanager
def tenant_context(tenant):
    token = _current_tenant.set(tenant)
    try:
        yield tenant
    finally:
        _current_tenant.reset(token)
