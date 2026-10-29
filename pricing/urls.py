from rest_framework.routers import DefaultRouter

from .views import RateComponentViewSet, RatePlanViewSet

router = DefaultRouter()
router.register("rate-plans", RatePlanViewSet, basename="rate-plan")
router.register("rate-components", RateComponentViewSet, basename="rate-component")

urlpatterns = router.urls
