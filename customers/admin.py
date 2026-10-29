from django.contrib import admin

from tenants.admin_utils import TenantScopedAdminMixin

from .models import Contact, Customer, Site


@admin.register(Customer)
class CustomerAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "status", "credit_limit")
    list_filter = ("status",)
    search_fields = ("code", "name", "legal_name")


@admin.register(Contact)
class ContactAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "customer", "job_title", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("name", "email", "phone")


@admin.register(Site)
class SiteAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "customer")
    search_fields = ("code", "name", "address")
