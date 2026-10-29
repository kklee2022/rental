from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AccountingExportView,
    BillingReportView,
    CreditNoteViewSet,
    DepositViewSet,
    InvoiceViewSet,
    PaymentViewSet,
    RefundViewSet,
)

router = DefaultRouter()
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")
router.register("refunds", RefundViewSet, basename="refund")
router.register("credit-notes", CreditNoteViewSet, basename="credit-note")
router.register("deposits", DepositViewSet, basename="deposit")

urlpatterns = [
    path("reports/billing/", BillingReportView.as_view(), name="billing-report"),
    path(
        "exports/accounting.csv",
        AccountingExportView.as_view(),
        name="accounting-export",
    ),
    *router.urls,
]
