from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AssetLogisticsEventViewSet,
    DeliveryReceiptViewSet,
    InventoryCountViewSet,
    LogisticsAttachmentViewSet,
    MobileLogisticsSummaryView,
    TransportJobViewSet,
)

router = DefaultRouter()
router.register("jobs", TransportJobViewSet, basename="transport-job")
router.register("events", AssetLogisticsEventViewSet, basename="logistics-event")
router.register(
    "delivery-receipts", DeliveryReceiptViewSet, basename="delivery-receipt"
)
router.register(
    "attachments", LogisticsAttachmentViewSet, basename="logistics-attachment"
)
router.register("inventory-counts", InventoryCountViewSet, basename="inventory-count")

urlpatterns = [
    path("summary/", MobileLogisticsSummaryView.as_view(), name="logistics-summary"),
    *router.urls,
]
