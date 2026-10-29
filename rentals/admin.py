from django.contrib import admin

from tenants.admin_utils import TenantScopedAdminMixin

from .models import (
    Contract,
    ContractVersion,
    Quote,
    QuoteLine,
    RentalLine,
    RentalOrder,
    ReservationAllocation,
)


class QuoteLineInline(admin.TabularInline):
    model = QuoteLine
    extra = 0
    readonly_fields = ("line_total", "tax_amount", "price_snapshot")


@admin.register(Quote)
class QuoteAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("number", "customer", "status", "total", "valid_until")
    list_filter = ("status",)
    search_fields = ("number", "customer__name")
    readonly_fields = (
        "number",
        "subtotal",
        "discount_total",
        "tax_total",
        "total",
        "deposit_total",
        "price_snapshot",
        "approved_by",
        "approved_at",
        "created_by",
        "created_at",
        "updated_at",
    )


class RentalLineInline(admin.TabularInline):
    model = RentalLine
    extra = 0
    readonly_fields = (
        "asset",
        "line_total",
        "tax_amount",
        "price_snapshot",
    )


@admin.register(RentalOrder)
class RentalOrderAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("number", "customer", "status", "start_at", "end_at", "total")
    list_filter = ("status",)
    search_fields = ("number", "customer__name")
    readonly_fields = (
        "number",
        "subtotal",
        "discount_total",
        "tax_total",
        "total",
        "deposit_total",
        "price_snapshot",
        "confirmed_by",
        "confirmed_at",
        "dispatched_at",
        "returned_at",
        "created_by",
        "created_at",
        "updated_at",
    )


@admin.register(ReservationAllocation)
class ReservationAllocationAdmin(admin.ModelAdmin):
    list_display = ("asset", "rental_line", "status", "start_at", "end_at")
    list_filter = ("status",)


class ContractVersionInline(admin.TabularInline):
    model = ContractVersion
    extra = 0
    can_delete = False
    readonly_fields = (
        "version",
        "snapshot",
        "content_sha256",
        "created_by",
        "created_at",
    )


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "current_version", "issued_at", "signed_at")
    list_filter = ("status",)
    inlines = [ContractVersionInline]


@admin.register(ContractVersion)
class ContractVersionAdmin(admin.ModelAdmin):
    list_display = ("contract", "version", "content_sha256", "created_at")
    readonly_fields = [field.name for field in ContractVersion._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
