from django.contrib import admin

from tenants.admin_utils import TenantScopedAdminMixin

from .models import ImportBatch, ImportChange, ImportMapping, ImportRow


class ImportRowInline(admin.TabularInline):
    model = ImportRow
    extra = 0
    can_delete = False
    readonly_fields = (
        "row_number",
        "action",
        "validation_errors",
        "warnings",
        "normalized_data",
    )


@admin.register(ImportBatch)
class ImportBatchAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "original_filename",
        "import_type",
        "status",
        "total_rows",
        "error_rows",
        "created_at",
    )
    list_filter = ("import_type", "status")
    search_fields = ("original_filename", "content_sha256")


@admin.register(ImportRow)
class ImportRowAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("batch", "row_number", "action")
    list_filter = ("action",)

    def has_add_permission(self, request):
        return False


@admin.register(ImportMapping)
class ImportMappingAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "import_type", "is_default", "created_by")
    list_filter = ("import_type", "is_default")


@admin.register(ImportChange)
class ImportChangeAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("batch", "action", "object_type", "object_label", "created_at")
    list_filter = ("action", "object_type")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
