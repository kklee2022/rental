from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AssetViewSet,
    EquipmentCategoryViewSet,
    EquipmentModelViewSet,
    FleetReportView,
    LocationViewSet,
    MeterReadingViewSet,
)

router = DefaultRouter()
router.register(
    "equipment-categories", EquipmentCategoryViewSet, basename="equipment-category"
)
router.register("locations", LocationViewSet, basename="location")
router.register("equipment-models", EquipmentModelViewSet, basename="equipment-model")
router.register("assets", AssetViewSet, basename="asset")
router.register("meter-readings", MeterReadingViewSet, basename="meter-reading")

urlpatterns = [
    path("reports/fleet/", FleetReportView.as_view(), name="fleet-report"),
    *router.urls,
]
