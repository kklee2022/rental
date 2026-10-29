from django.contrib import admin

from tenants.admin_utils import TenantScopedAdminMixin

from .models import (
    Accessory,
    Asset,
    AssetStatusEvent,
    EquipmentCategory,
    EquipmentModel,
    Location,
    MeterReading,
)


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(Location)
class LocationAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "location_type", "is_active")
    list_filter = ("location_type", "is_active")


@admin.register(EquipmentModel)
class EquipmentModelAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "category", "manufacturer", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("code", "name", "manufacturer", "model_number")


@admin.register(Asset)
class AssetAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "asset_number",
        "model",
        "status",
        "location",
        "current_hours",
        "current_kilometers",
    )
    list_filter = ("status", "model__category", "location")
    search_fields = ("asset_number", "serial_number", "registration_number", "qr_code")
    readonly_fields = ("status_changed_at", "created_by", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if change:
            obj._status_transition_allowed = True
            obj._status_actor = request.user
            obj._status_source = "admin"
        super().save_model(request, obj, form, change)


@admin.register(AssetStatusEvent)
class AssetStatusEventAdmin(admin.ModelAdmin):
    list_display = (
        "asset",
        "from_status",
        "to_status",
        "source",
        "actor",
        "created_at",
    )
    list_filter = ("to_status", "source")
    readonly_fields = [field.name for field in AssetStatusEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("asset", "hours", "kilometers", "recorded_at", "source", "actor")
    list_filter = ("source",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Accessory)
class AccessoryAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "accessory_type", "status", "location")
    list_filter = ("status", "accessory_type")
    search_fields = ("code", "name", "serial_number")
