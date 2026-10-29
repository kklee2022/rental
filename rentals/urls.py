from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ContractViewSet,
    QuoteLineViewSet,
    QuoteViewSet,
    RentalOrderViewSet,
    RentalReportView,
    ReservationAllocationViewSet,
)

router = DefaultRouter()
router.register("quotes", QuoteViewSet, basename="quote")
router.register("quote-lines", QuoteLineViewSet, basename="quote-line")
router.register("rental-orders", RentalOrderViewSet, basename="rental-order")
router.register("reservations", ReservationAllocationViewSet, basename="reservation")
router.register("contracts", ContractViewSet, basename="contract")

urlpatterns = [
    path("reports/rentals/", RentalReportView.as_view(), name="rental-report"),
    *router.urls,
]
