from django.contrib import messages

from core.context import tenant_context
from core.models import record_audit


class TenantScopedAdminMixin:
    """Wrap platform-admin edits in the object's tenant context."""

    def has_add_permission(self, request):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def save_model(self, request, obj, form, change):
        if not obj.tenant_id:
            messages.error(request, "Tenant-owned objects must be created via the API.")
            return
        with tenant_context(obj.tenant):
            super().save_model(request, obj, form, change)
            record_audit(
                f"{obj._meta.model_name}.admin_updated",
                tenant=obj.tenant,
                actor=request.user,
                obj=obj,
            )

    def delete_model(self, request, obj):
        tenant = obj.tenant
        object_id = obj.pk
        with tenant_context(tenant):
            super().delete_model(request, obj)
            record_audit(
                f"{obj._meta.model_name}.admin_deleted",
                tenant=tenant,
                actor=request.user,
                object_id=str(object_id),
            )
