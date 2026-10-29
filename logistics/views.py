from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError as ApiValidationError,
)
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.models import record_audit
from core.sequences import next_document_number
from customers.models import Site
from fleet.models import Asset, Location
from tenants.models import Role
from tenants.permissions import HasFeature, has_role

from .models import (
    AssetLogisticsEvent,
    DeliveryReceipt,
    InventoryCount,
    LogisticsAttachment,
    TransportJob,
)
from .serializers import (
    AssetLogisticsEventCreateSerializer,
    AssetLogisticsEventSerializer,
    DeliveryReceiptSerializer,
    InventoryCountCreateSerializer,
    InventoryCountSerializer,
    InventoryScanSerializer,
    LogisticsAttachmentSerializer,
    MobileLogisticsSummarySerializer,
    TransportJobActionSerializer,
    TransportJobSerializer,
)
from .services import (
    complete_inventory,
    record_asset_event,
    record_delivery_receipt,
    resolve_asset,
    scan_inventory,
    transition_job,
)


class LogisticsPermissionMixin:
    required_feature = "mobile_logistics"

    def get_permissions(self):
        permissions = super().get_permissions()
        permissions.append(HasFeature())
        return permissions


def _driver_owns_job(request, job):
    membership = request.membership
    return membership.role != Role.DRIVER or job.driver_id == request.user.pk


def _job_from_payload(payload, request):
    job_id = payload.get("job")
    if not job_id:
        return None
    job = (
        job_id
        if isinstance(job_id, TransportJob)
        else TransportJob.objects.filter(pk=job_id).first()
    )
    if job is None:
        raise ApiValidationError({"job": "Transport job was not found."})
    if not _driver_owns_job(request, job):
        raise PermissionDenied("Drivers can only update assigned jobs.")
    return job


def _asset_from_payload(payload):
    asset_id = payload.get("asset_id")
    if asset_id:
        asset = Asset.objects.filter(pk=asset_id).first()
        if asset is None:
            raise ApiValidationError({"asset_id": "Asset was not found."})
        return asset
    try:
        return resolve_asset(payload.get("asset_identifier"))
    except ValidationError as exc:
        raise ApiValidationError(exc.message_dict) from exc


class TransportJobViewSet(LogisticsPermissionMixin, ModelViewSet):
    serializer_class = TransportJobSerializer

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return TransportJob._base_manager.none()
        queryset = (
            TransportJob.objects.select_related(
                "order",
                "depot",
                "destination_location",
                "destination_site",
                "destination_site__customer",
                "driver",
            )
            .prefetch_related(
                "asset_links",
                "asset_links__asset",
                "asset_links__asset__model",
            )
            .all()
        )
        membership = getattr(request._request, "membership", None)
        if membership and membership.role == Role.DRIVER:
            queryset = queryset.filter(driver=request.user)
        return queryset

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [
                IsAuthenticated(),
                has_role(Role.WAREHOUSE)(),
                HasFeature(),
            ]
        return [
            IsAuthenticated(),
            has_role(Role.WAREHOUSE, Role.DRIVER)(),
            HasFeature(),
        ]

    def perform_create(self, serializer):
        job = serializer.save(
            number=next_document_number("transport_job", "T"),
            created_by=self.request.user,
        )
        record_audit("logistics.job.created", actor=self.request.user, obj=job)

    def perform_update(self, serializer):
        job = serializer.save()
        record_audit("logistics.job.updated", actor=self.request.user, obj=job)

    def perform_destroy(self, instance):
        object_id = instance.pk
        instance.delete()
        record_audit(
            "logistics.job.deleted",
            actor=self.request.user,
            object_id=str(object_id),
        )

    @extend_schema(
        request=TransportJobActionSerializer, responses=TransportJobSerializer
    )
    def _transition(self, request, action):
        payload = TransportJobActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        job = transition_job(
            self.get_object(),
            actor=request.user,
            action=action,
            reason=payload.validated_data.get("reason", ""),
        )
        return Response(self.get_serializer(job).data)

    @extend_schema(
        request=TransportJobActionSerializer, responses=TransportJobSerializer
    )
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._transition(request, "start")

    @extend_schema(
        request=TransportJobActionSerializer, responses=TransportJobSerializer
    )
    @action(detail=True, methods=["post"], url_path="arrive")
    def arrive(self, request, pk=None):
        return self._transition(request, "arrive")

    @extend_schema(
        request=TransportJobActionSerializer, responses=TransportJobSerializer
    )
    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        return self._transition(request, "deliver")

    @extend_schema(
        request=TransportJobActionSerializer, responses=TransportJobSerializer
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._transition(request, "complete")

    @extend_schema(
        request=TransportJobActionSerializer, responses=TransportJobSerializer
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition(request, "cancel")


class AssetLogisticsEventViewSet(
    LogisticsPermissionMixin,
    ModelViewSet,
):
    serializer_class = AssetLogisticsEventSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return AssetLogisticsEvent._base_manager.none()
        queryset = AssetLogisticsEvent.objects.select_related(
            "asset",
            "asset__model",
            "job",
            "from_location",
            "to_location",
            "site",
            "actor",
        ).all()
        membership = getattr(request._request, "membership", None)
        if membership and membership.role == Role.DRIVER:
            queryset = queryset.filter(
                Q(job__driver=request.user) | Q(actor=request.user)
            )
        job_id = request.query_params.get("job")
        if job_id:
            queryset = queryset.filter(job_id=job_id)
        return queryset

    def get_permissions(self):
        return [
            IsAuthenticated(),
            has_role(Role.WAREHOUSE, Role.DRIVER, Role.TECHNICIAN)(),
            HasFeature(),
        ]

    def get_serializer_class(self):
        if self.action == "create":
            return AssetLogisticsEventCreateSerializer
        return AssetLogisticsEventSerializer

    @extend_schema(
        request=AssetLogisticsEventCreateSerializer,
        responses=AssetLogisticsEventSerializer,
    )
    def create(self, request, *args, **kwargs):
        payload = AssetLogisticsEventCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        job = _job_from_payload(data, request)
        asset = _asset_from_payload(data)
        to_location = None
        if data.get("to_location"):
            to_location = Location.objects.filter(pk=data["to_location"]).first()
            if to_location is None:
                raise ApiValidationError(
                    {"to_location": "Destination location was not found."}
                )
        from_location = None
        if data.get("from_location"):
            from_location = Location.objects.filter(pk=data["from_location"]).first()
            if from_location is None:
                raise ApiValidationError(
                    {"from_location": "Origin location was not found."}
                )
        site = None
        if data.get("site"):
            site = Site.objects.filter(pk=data["site"]).first()
            if site is None:
                raise ApiValidationError({"site": "Site was not found."})
        try:
            event = record_asset_event(
                actor=request.user,
                event_type=data["event_type"],
                asset=asset,
                job=job,
                from_location=from_location,
                to_location=to_location,
                site=site,
                latitude=data.get("latitude"),
                longitude=data.get("longitude"),
                occurred_at=data.get("occurred_at"),
                source=data["source"],
                client_event_id=data.get("client_event_id"),
                notes=data.get("notes", ""),
                metadata=data.get("metadata", {}),
            )
        except ValidationError as exc:
            raise ApiValidationError(exc.message_dict or exc.messages) from exc
        return Response(
            AssetLogisticsEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )


class DeliveryReceiptViewSet(LogisticsPermissionMixin, ModelViewSet):
    serializer_class = DeliveryReceiptSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return DeliveryReceipt._base_manager.none()
        queryset = DeliveryReceipt.objects.select_related("job", "actor").all()
        membership = getattr(request._request, "membership", None)
        if membership and membership.role == Role.DRIVER:
            queryset = queryset.filter(job__driver=request.user)
        return queryset

    def get_permissions(self):
        return [
            IsAuthenticated(),
            has_role(Role.WAREHOUSE, Role.DRIVER)(),
            HasFeature(),
        ]

    @extend_schema(
        request=DeliveryReceiptSerializer, responses=DeliveryReceiptSerializer
    )
    def create(self, request, *args, **kwargs):
        payload = DeliveryReceiptSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        job = _job_from_payload(data, request)
        if job is None:
            raise ApiValidationError({"job": "Transport job is required."})
        try:
            receipt = record_delivery_receipt(
                actor=request.user,
                job=job,
                signer_name=data["signer_name"],
                signer_phone=data.get("signer_phone", ""),
                accepted=data.get("accepted", True),
                rejection_reason=data.get("rejection_reason", ""),
                signature_data=data.get("signature_data", ""),
                signed_at=data.get("signed_at"),
                latitude=data.get("latitude"),
                longitude=data.get("longitude"),
                client_event_id=data.get("client_event_id"),
                notes=data.get("notes", ""),
            )
        except ValidationError as exc:
            raise ApiValidationError(exc.message_dict or exc.messages) from exc
        return Response(
            DeliveryReceiptSerializer(receipt).data,
            status=status.HTTP_201_CREATED,
        )


class LogisticsAttachmentViewSet(LogisticsPermissionMixin, ModelViewSet):
    serializer_class = LogisticsAttachmentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "head", "options"]
    allowed_content_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "application/pdf",
    }

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return LogisticsAttachment._base_manager.none()
        queryset = LogisticsAttachment.objects.select_related(
            "job", "asset", "uploaded_by"
        ).all()
        membership = getattr(request._request, "membership", None)
        if membership and membership.role == Role.DRIVER:
            queryset = queryset.filter(job__driver=request.user)
        job_id = request.query_params.get("job")
        if job_id:
            queryset = queryset.filter(job_id=job_id)
        return queryset

    def get_permissions(self):
        return [
            IsAuthenticated(),
            has_role(Role.WAREHOUSE, Role.DRIVER, Role.TECHNICIAN)(),
            HasFeature(),
        ]

    def create(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            raise ApiValidationError({"file": "File is required."})
        if upload.content_type not in self.allowed_content_types:
            raise ApiValidationError({"file": "Unsupported attachment type."})
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.validated_data["job"]
        if not _driver_owns_job(request, job):
            raise PermissionDenied("Drivers can only update assigned jobs.")
        attachment = serializer.save(
            original_filename=upload.name,
            content_type=upload.content_type,
            file_size=upload.size,
            uploaded_by=request.user,
        )
        record_audit(
            "logistics.attachment.created",
            actor=request.user,
            obj=attachment,
            job=job.number,
        )
        return Response(
            self.get_serializer(attachment).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        attachment = self.get_object()
        return FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,
            filename=attachment.original_filename,
            content_type=attachment.content_type or "application/octet-stream",
        )


class InventoryCountViewSet(LogisticsPermissionMixin, ModelViewSet):
    serializer_class = InventoryCountSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return InventoryCount._base_manager.none()
        return (
            InventoryCount.objects.select_related(
                "location", "started_by", "completed_by"
            )
            .prefetch_related("lines", "lines__asset", "lines__asset__model")
            .all()
        )

    def get_permissions(self):
        return [
            IsAuthenticated(),
            has_role(Role.WAREHOUSE)(),
            HasFeature(),
        ]

    def get_serializer_class(self):
        if self.action == "create":
            return InventoryCountCreateSerializer
        return InventoryCountSerializer

    @extend_schema(
        request=InventoryCountCreateSerializer, responses=InventoryCountSerializer
    )
    def create(self, request, *args, **kwargs):
        payload = InventoryCountCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        location = Location.objects.filter(
            pk=payload.validated_data["location"]
        ).first()
        if location is None:
            raise ApiValidationError({"location": "Location was not found."})
        count = InventoryCount.objects.create(
            number=next_document_number("inventory_count", "I"),
            location=location,
            notes=payload.validated_data.get("notes", ""),
            started_by=request.user,
        )
        record_audit("logistics.inventory.started", actor=request.user, obj=count)
        return Response(
            InventoryCountSerializer(count).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=InventoryScanSerializer, responses=InventoryCountSerializer)
    @action(detail=True, methods=["post"])
    def scan(self, request, pk=None):
        count = self.get_object()
        payload = InventoryScanSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            scan_inventory(
                count,
                actor=request.user,
                asset_identifier=payload.validated_data["asset_identifier"],
                client_event_id=payload.validated_data.get("client_event_id"),
                notes=payload.validated_data.get("notes", ""),
            )
        except ValidationError as exc:
            raise ApiValidationError(exc.message_dict or exc.messages) from exc
        count.refresh_from_db()
        return Response(self.get_serializer(count).data)

    @extend_schema(request=None, responses=InventoryCountSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        try:
            count = complete_inventory(self.get_object(), actor=request.user)
        except ValidationError as exc:
            raise ApiValidationError(exc.message_dict or exc.messages) from exc
        return Response(self.get_serializer(count).data)

    @extend_schema(request=None, responses=InventoryCountSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        count = self.get_object()
        if count.status != InventoryCount.Status.IN_PROGRESS:
            raise ApiValidationError(
                {"status": "Only in-progress inventory counts can be cancelled."}
            )
        count.status = InventoryCount.Status.CANCELLED
        count.save(update_fields=["status", "updated_at"])
        record_audit("logistics.inventory.cancelled", actor=request.user, obj=count)
        return Response(self.get_serializer(count).data)


@extend_schema(responses=MobileLogisticsSummarySerializer)
class MobileLogisticsSummaryView(APIView):
    required_feature = "mobile_logistics"
    permission_classes = [
        IsAuthenticated,
        has_role(Role.WAREHOUSE, Role.DRIVER, Role.TECHNICIAN),
        HasFeature,
    ]

    def get(self, request):
        jobs = TransportJob.objects.all()
        events = AssetLogisticsEvent.objects.select_related(
            "asset", "asset__model", "job", "actor"
        )
        if request.membership.role == Role.DRIVER:
            jobs = jobs.filter(driver=request.user)
            events = events.filter(Q(job__driver=request.user) | Q(actor=request.user))
        status_counts = {
            row["status"]: row["count"]
            for row in jobs.values("status").annotate(count=Count("id"))
        }
        recent_events = events.order_by("-occurred_at", "-id")[:10]
        return Response(
            {
                "scheduled_jobs": status_counts.get(TransportJob.Status.SCHEDULED, 0),
                "active_jobs": sum(
                    status_counts.get(value, 0)
                    for value in (
                        TransportJob.Status.IN_PROGRESS,
                        TransportJob.Status.AT_SITE,
                    )
                ),
                "awaiting_receipt": jobs.filter(
                    direction=TransportJob.Direction.OUTBOUND,
                    status=TransportJob.Status.DELIVERED,
                )
                .exclude(receipts__accepted=True)
                .distinct()
                .count(),
                "pending_collection": Asset.objects.filter(
                    status=Asset.Status.PENDING_COLLECTION
                ).count(),
                "recent_events": AssetLogisticsEventSerializer(
                    recent_events, many=True
                ).data,
            }
        )
