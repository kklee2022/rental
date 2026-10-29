from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from core.models import AuditEvent, record_audit

from .models import Membership
from .permissions import has_role
from .serializers import (
    AccountResponseSerializer,
    AccountTenantSerializer,
    AuditEventSerializer,
    CurrentTenantResponseSerializer,
    MembershipSerializer,
)


@extend_schema(
    responses=AccountResponseSerializer,
    auth=[{"sessionCookie": []}],
)
class AccountView(APIView):
    def get(self, request):
        memberships = (
            Membership.objects.filter(user=request.user, is_active=True)
            .select_related("tenant__plan")
            .order_by("tenant__name", "id")
        )
        return Response(
            {
                "username": request.user.get_username(),
                "tenants": [
                    {
                        "slug": membership.tenant.slug,
                        "name": membership.tenant.name,
                        "status": membership.tenant.status,
                        "membership": AccountTenantSerializer(membership).data,
                    }
                    for membership in memberships
                ],
            }
        )


@extend_schema(responses=CurrentTenantResponseSerializer)
class CurrentTenantView(APIView):
    def get(self, request):
        tenant = request.tenant
        membership = request.membership
        return Response(
            {
                "slug": tenant.slug,
                "name": tenant.name,
                "role": membership.role,
                "plan": {
                    "code": tenant.plan.code,
                    "max_assets": tenant.plan.max_assets,
                    "max_users": tenant.plan.max_users,
                    "features": tenant.plan.features,
                },
            }
        )


class MembershipQuerysetMixin:
    def get_queryset(self):
        return (
            Membership.objects.filter(tenant=self.request.tenant)
            .select_related("user", "tenant")
            .order_by("id")
        )


class MembershipListCreateView(
    MembershipQuerysetMixin,
    generics.ListCreateAPIView,
):
    serializer_class = MembershipSerializer
    permission_classes = [IsAuthenticated, has_role()]

    def perform_create(self, serializer):
        membership = serializer.save(tenant=self.request.tenant)
        record_audit(
            "membership.created",
            actor=self.request.user,
            obj=membership,
            user_id=membership.user_id,
            role=membership.role,
        )


class MembershipDetailView(
    MembershipQuerysetMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = MembershipSerializer
    permission_classes = [IsAuthenticated, has_role()]

    def perform_update(self, serializer):
        previous = {
            "role": serializer.instance.role,
            "is_active": serializer.instance.is_active,
        }
        membership = serializer.save()
        record_audit(
            "membership.updated",
            actor=self.request.user,
            obj=membership,
            previous=previous,
            role=membership.role,
            is_active=membership.is_active,
        )

    def perform_destroy(self, instance):
        membership_id = instance.pk
        user_id = instance.user_id
        role = instance.role
        instance.delete()
        record_audit(
            "membership.deleted",
            actor=self.request.user,
            membership_id=membership_id,
            user_id=user_id,
            role=role,
        )


class AuditEventListView(generics.ListAPIView):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated, has_role()]

    def get_queryset(self):
        return AuditEvent.objects.filter(tenant=self.request.tenant).select_related(
            "actor"
        )
