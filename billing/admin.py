from django.contrib import admin

from tenants.admin_utils import TenantScopedAdminMixin

from .models import CreditNote, Deposit, Invoice, InvoiceLine, Payment, Refund


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = (
        "rental_line",
        "description",
        "quantity",
        "unit_price",
        "tax_amount",
        "line_total",
        "price_snapshot",
    )


@admin.register(Invoice)
class InvoiceAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "number",
        "order",
        "invoice_type",
        "status",
        "total",
        "balance",
        "due_date",
    )
    list_filter = ("invoice_type", "status")
    search_fields = ("number", "order__number", "order__customer__name")
    readonly_fields = (
        "number",
        "subtotal",
        "tax_total",
        "credit_total",
        "amount_paid",
        "total",
        "balance",
        "price_snapshot",
        "issued_by",
        "issued_at",
        "created_by",
        "created_at",
        "updated_at",
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "method", "received_at", "status")
    list_filter = ("method", "status")


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("payment", "amount", "processed_at", "status")
    list_filter = ("status",)


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ("number", "invoice", "amount", "status", "issued_at")
    list_filter = ("status",)
    readonly_fields = ("number", "snapshot", "created_at")


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "status", "received_at", "applied_to_invoice")
    list_filter = ("status",)
