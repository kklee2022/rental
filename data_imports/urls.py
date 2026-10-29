from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ImportBatchViewSet,
    ImportMappingViewSet,
    ImportRowViewSet,
    ImportTemplateView,
)

router = DefaultRouter()
router.register("imports", ImportBatchViewSet, basename="import-batch")
router.register("import-rows", ImportRowViewSet, basename="import-row")
router.register("import-mappings", ImportMappingViewSet, basename="import-mapping")

urlpatterns = [
    path(
        "import-templates/<str:import_type>/",
        ImportTemplateView.as_view(),
        name="import-template",
    ),
    *router.urls,
]
