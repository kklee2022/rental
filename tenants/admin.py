from django.contrib import admin

from .models import Membership, Plan, Tenant


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "max_assets", "max_users")

    def save_model(self, request, obj, form, change):
        from core.models import record_audit

        previous = None
        if change:
            old = Plan.objects.get(pk=obj.pk)
            previous = {
                field: getattr(old, field)
                for field in ("code", "name", "max_assets", "max_users", "features")
            }
        super().save_model(request, obj, form, change)
        record_audit(
            "plan.updated" if change else "plan.created",
            actor=request.user,
            obj=obj,
            previous=previous,
        )


@admin.action(description="Suspend selected tenants")
def suspend(modeladmin, request, queryset):
    from core.models import record_audit

    for tenant in queryset:
        tenant.status = Tenant.Status.SUSPENDED
        tenant.save(update_fields=["status"])
        record_audit("tenant.suspended", tenant=tenant, actor=request.user, obj=tenant)


@admin.action(description="Activate selected tenants")
def activate(modeladmin, request, queryset):
    from core.models import record_audit

    for tenant in queryset:
        tenant.status = Tenant.Status.ACTIVE
        tenant.save(update_fields=["status"])
        record_audit("tenant.activated", tenant=tenant, actor=request.user, obj=tenant)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "status", "created_at")
    list_filter = ("status", "plan")
    search_fields = ("name", "slug")
    actions = [suspend, activate]

    def save_model(self, request, obj, form, change):
        from core.models import record_audit

        previous = None
        if change:
            old = Tenant.objects.get(pk=obj.pk)
            previous = {
                "name": old.name,
                "slug": old.slug,
                "plan_id": old.plan_id,
                "status": old.status,
            }
        super().save_model(request, obj, form, change)
        record_audit(
            "tenant.updated" if change else "tenant.created",
            tenant=obj,
            actor=request.user,
            obj=obj,
            previous=previous,
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "is_active")
    list_filter = ("tenant", "role", "is_active")

    def save_model(self, request, obj, form, change):
        from core.models import record_audit

        previous = None
        if change:
            old = Membership.objects.get(pk=obj.pk)
            previous = {"role": old.role, "is_active": old.is_active}
        super().save_model(request, obj, form, change)
        record_audit(
            "membership.updated" if change else "membership.created",
            tenant=obj.tenant,
            actor=request.user,
            obj=obj,
            previous=previous,
        )

    def delete_model(self, request, obj):
        from core.models import record_audit

        tenant = obj.tenant
        detail = {
            "member_user_id": obj.user_id,
            "member_role": obj.role,
        }
        super().delete_model(request, obj)
        record_audit(
            "membership.deleted",
            tenant=tenant,
            actor=request.user,
            **detail,
        )
