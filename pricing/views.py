from tenants.models import Role
from tenants.viewsets import AuditedTenantModelViewSet

from .models import RateComponent, RatePlan
from .serializers import RateComponentSerializer, RatePlanSerializer


class RatePlanViewSet(AuditedTenantModelViewSet):
    write_roles = (Role.RENTAL,)
    queryset_model = RatePlan
    serializer_class = RatePlanSerializer
    queryset_select_related = ()


class RateComponentViewSet(AuditedTenantModelViewSet):
    write_roles = (Role.RENTAL,)
    queryset_model = RateComponent
    queryset_select_related = ("rate_plan", "equipment_model")
    serializer_class = RateComponentSerializer
