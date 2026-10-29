from django.contrib import admin

from tenants.admin_utils import TenantScopedAdminMixin

from .models import RateComponent, RatePlan


class RateComponentInline(admin.TabularInline):
    model = RateComponent
    extra = 0


@admin.register(RatePlan)
class RatePlanAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "currency",
        "time_unit",
        "base_unit_price",
        "is_active",
    )
    list_filter = ("time_unit", "is_active")


@admin.register(RateComponent)
class RateComponentAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "rate_plan",
        "component_type",
        "pricing_method",
        "unit_price",
    )
    list_filter = ("component_type", "pricing_method")
