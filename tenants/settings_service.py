from core.context import require_current_tenant

from .models import TenantSettings


PREFIX_FIELDS = {
    "customer": "customer_prefix",
    "invoice": "invoice_prefix",
    "rental": "rental_prefix",
    "quote": "quote_prefix",
}


def get_tenant_settings(tenant=None):
    tenant = tenant or require_current_tenant()
    settings, _ = TenantSettings.objects.get_or_create(tenant=tenant)
    return settings


def get_number_prefix(kind):
    settings = get_tenant_settings()
    try:
        return getattr(settings, PREFIX_FIELDS[kind])
    except KeyError as exc:
        raise ValueError(f"Unknown number prefix kind: {kind}") from exc
