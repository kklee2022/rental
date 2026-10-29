"""Execution boundary for background work that accesses tenant-owned data."""

from tenants.models import Tenant

from .context import tenant_context


class TenantJobUnavailable(RuntimeError):
    pass


def run_tenant_job(tenant_id, callback, *args, **kwargs):
    """Run a job only for an active tenant and always clear tenant context."""

    tenant = (
        Tenant.objects.select_related("plan")
        .filter(pk=tenant_id, status=Tenant.Status.ACTIVE)
        .first()
    )
    if tenant is None:
        raise TenantJobUnavailable(
            f"Tenant {tenant_id} does not exist or is not active"
        )

    with tenant_context(tenant):
        return callback(*args, **kwargs)
