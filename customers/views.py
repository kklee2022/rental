from tenants.viewsets import AuditedTenantModelViewSet

from .models import Contact, Customer, Site
from .serializers import ContactSerializer, CustomerSerializer, SiteSerializer


class CustomerViewSet(AuditedTenantModelViewSet):
    queryset_model = Customer
    serializer_class = CustomerSerializer


class ContactViewSet(AuditedTenantModelViewSet):
    queryset_model = Contact
    queryset_select_related = ("customer",)
    serializer_class = ContactSerializer


class SiteViewSet(AuditedTenantModelViewSet):
    queryset_model = Site
    queryset_select_related = ("customer",)
    serializer_class = SiteSerializer
