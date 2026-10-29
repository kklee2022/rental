from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .context import get_current_tenant, require_current_tenant


class TenantMismatch(Exception):
    """Raised when a record is saved under a different tenant than the active one."""


class TenantScopedQuerySet(models.QuerySet):
    """Bulk operations retain the same tenant checks as model saves."""

    def _validate_tenant_values(self, objects):
        active = require_current_tenant()
        for obj in objects:
            if obj.tenant_id is None:
                obj.tenant_id = active.pk
            elif obj.tenant_id != active.pk:
                raise TenantMismatch(
                    f"{type(obj).__name__} belongs to tenant {obj.tenant_id}, "
                    f"active tenant is {active.pk}"
                )

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        self._validate_tenant_values(objs)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        if "tenant" in fields or "tenant_id" in fields:
            raise TenantMismatch("Bulk updates cannot change ownership")
        self._validate_tenant_values(objs)
        return super().bulk_update(objs, fields, *args, **kwargs)

    def update(self, **kwargs):
        if "tenant" in kwargs or "tenant_id" in kwargs:
            raise TenantMismatch("Updates cannot change ownership")
        return super().update(**kwargs)


class TenantManager(models.Manager.from_queryset(TenantScopedQuerySet)):  # type: ignore[misc]
    """Default manager: every query is limited to the active tenant."""

    def get_queryset(self):
        tenant = require_current_tenant()
        return super().get_queryset().filter(tenant_id=tenant.pk)


class TenantScopedModel(models.Model):
    """Base class for all tenant-owned business data.

    `objects` is always tenant-filtered and fails closed when no tenant is active.
    `all_tenants` is an explicit escape hatch for platform-level code only.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="+", editable=False
    )

    objects = TenantManager()
    all_tenants = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "all_tenants"

    def save(self, *args, **kwargs):
        active = require_current_tenant()
        if self.tenant_id is None:
            self.tenant_id = active.pk
        elif self.tenant_id != active.pk:
            raise TenantMismatch(
                f"{type(self).__name__} belongs to tenant {self.tenant_id}, "
                f"active tenant is {active.pk}"
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        active = require_current_tenant()
        if self.tenant_id != active.pk:
            raise TenantMismatch("Cannot delete a record of another tenant")
        return super().delete(*args, **kwargs)


class AppendOnlyTenantQuerySet(TenantScopedQuerySet):
    def update(self, **kwargs):
        raise PermissionError("This record type is append-only")

    def delete(self):
        raise PermissionError("This record type is append-only")


class AppendOnlyTenantManager(
    TenantManager.from_queryset(AppendOnlyTenantQuerySet)  # type: ignore[misc]
):
    pass


class AppendOnlyTenantModel(TenantScopedModel):
    objects = AppendOnlyTenantManager()

    class Meta:
        abstract = True
        base_manager_name = "all_tenants"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("This record type is append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("This record type is append-only")


class DocumentSequence(TenantScopedModel):
    """Per-tenant document number counters for quotes, orders and invoices."""

    key = models.CharField(max_length=40)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key"], name="unique_document_sequence"
            )
        ]

    def __str__(self):
        return f"{self.key}:{self.last_value}"


class ImmutableAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Audit events are append-only")

    def delete(self):
        raise PermissionError("Audit events cannot be deleted")


class ImmutableAuditManager(
    models.Manager.from_queryset(ImmutableAuditQuerySet)  # type: ignore[misc]
):
    pass


class AuditEvent(models.Model):
    """Append-only record of sensitive operations."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableAuditManager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tenant", "-created_at"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Audit events are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit events cannot be deleted")


def record_audit(action, *, tenant=None, actor=None, obj=None, **detail):
    if not action or not isinstance(action, str):
        raise ValidationError("Audit action is required")
    return AuditEvent.objects.create(
        tenant=tenant or get_current_tenant(),
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        object_type=type(obj).__name__ if obj is not None else "",
        object_id=str(obj.pk) if obj is not None and obj.pk is not None else "",
        detail=detail,
    )
