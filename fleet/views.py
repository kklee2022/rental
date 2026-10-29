from django.db.models import Count
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from tenants.models import Role
from tenants.permissions import HasTenantMembership
from tenants.viewsets import AuditedTenantModelViewSet

from .models import (
    Asset,
    AssetStatusEvent,
    EquipmentCategory,
    EquipmentModel,
    Location,
    MeterReading,
)
from rentals.models import ReservationAllocation
from .serializers import (
    AssetSerializer,
    AssetStatusEventSerializer,
    AssetTransitionSerializer,
    EquipmentCategorySerializer,
    EquipmentModelSerializer,
    FleetReportSerializer,
    LocationSerializer,
    MeterReadingSerializer,
)


class FleetWriteViewSet(AuditedTenantModelViewSet):
    write_roles = (Role.WAREHOUSE,)


class EquipmentCategoryViewSet(FleetWriteViewSet):
    queryset_model = EquipmentCategory
    serializer_class = EquipmentCategorySerializer


class LocationViewSet(FleetWriteViewSet):
    queryset_model = Location
    serializer_class = LocationSerializer


class EquipmentModelViewSet(FleetWriteViewSet):
    queryset_model = EquipmentModel
    queryset_select_related = ("category",)
    serializer_class = EquipmentModelSerializer


class AssetViewSet(FleetWriteViewSet):
    queryset_model = Asset
    queryset_select_related = ("model", "location")
    serializer_class = AssetSerializer

    @extend_schema(
        request=AssetTransitionSerializer,
        responses=AssetSerializer,
    )
    @action(detail=True, methods=["post"], url_path="transition")
    def transition_status(self, request, pk=None):
        asset = self.get_object()
        payload = AssetTransitionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        asset.transition_to(
            payload.validated_data["status"],
            actor=request.user,
            reason=payload.validated_data.get("reason", ""),
            source=payload.validated_data["source"],
        )
        return Response(self.get_serializer(asset).data)

    @extend_schema(responses=AssetStatusEventSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="status-events")
    def status_events(self, request, pk=None):
        asset = self.get_object()
        events = AssetStatusEvent.objects.filter(asset=asset).select_related("actor")
        return Response(AssetStatusEventSerializer(events, many=True).data)


class MeterReadingViewSet(FleetWriteViewSet):
    queryset_model = MeterReading
    queryset_select_related = ("asset", "actor")
    serializer_class = MeterReadingSerializer

    def perform_create(self, serializer):
        reading = serializer.save(actor=self.request.user)
        from core.models import record_audit

        record_audit("meterreading.created", actor=self.request.user, obj=reading)


@extend_schema(responses=FleetReportSerializer)
class FleetReportView(APIView):
    permission_classes = [IsAuthenticated, HasTenantMembership]

    def get(self, request):
        now = timezone.now()
        status_counts = {
            row["status"]: row["count"]
            for row in Asset.objects.values("status").annotate(count=Count("id"))
        }
        total_assets = Asset.objects.count()
        allocated_assets = (
            ReservationAllocation.objects.filter(
                status=ReservationAllocation.Status.CONFIRMED,
                start_at__lte=now,
                end_at__gt=now,
            )
            .values("asset_id")
            .distinct()
            .count()
        )
        unavailable_statuses = {
            Asset.Status.MAINTENANCE,
            Asset.Status.AWAITING_PARTS,
            Asset.Status.SAFETY_LOCKED,
            Asset.Status.RETIRED,
            Asset.Status.LOST_WRITE_OFF,
        }
        unavailable = sum(
            count
            for status, count in status_counts.items()
            if status in unavailable_statuses
        )
        return Response(
            {
                "total_assets": total_assets,
                "allocated_now": allocated_assets,
                "unavailable": unavailable,
                "utilization_percent": (
                    round(allocated_assets / total_assets * 100, 2)
                    if total_assets
                    else 0
                ),
                "status_counts": status_counts,
            }
        )
