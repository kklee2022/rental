"""Tenant-namespaced storage helpers for private uploads and generated files."""

from django.core.files.storage import FileSystemStorage

from .context import require_current_tenant


class TenantStorageMixin:
    def tenant_name(self, name):
        tenant = require_current_tenant()
        prefix = f"tenants/{tenant.pk}/"
        clean_name = str(name).lstrip("/")
        if clean_name.startswith(prefix):
            return clean_name
        return f"{prefix}{clean_name}"


class TenantFileSystemStorage(TenantStorageMixin, FileSystemStorage):
    """Store files below `tenants/<tenant-id>/` while a tenant context is active."""

    def path(self, name):
        return super().path(self.tenant_name(name))

    def url(self, name):
        return super().url(self.tenant_name(name))


try:
    from storages.backends.s3 import S3Storage
except ImportError:  # Optional for SQLite-only local setups.
    S3Storage = None


if S3Storage is not None:

    class TenantS3Storage(TenantStorageMixin, S3Storage):
        """S3-compatible private storage with a tenant key prefix."""

        def _normalize_name(self, name):
            return super()._normalize_name(self.tenant_name(name))

        def url(self, name, parameters=None, expire=None, http_method=None):
            return super().url(
                self.tenant_name(name),
                parameters=parameters,
                expire=expire,
                http_method=http_method,
            )
