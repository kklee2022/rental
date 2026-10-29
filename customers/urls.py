from rest_framework.routers import DefaultRouter

from .views import ContactViewSet, CustomerViewSet, SiteViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("contacts", ContactViewSet, basename="contact")
router.register("sites", SiteViewSet, basename="site")

urlpatterns = router.urls
