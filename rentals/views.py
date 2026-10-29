from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from drf_spectacular.utils import extend_schema

from core.models import record_audit
from core.sequences import next_document_number
from fleet.models import Asset
from fleet.serializers import AssetSerializer
from tenants.models import Role
from tenants.permissions import HasTenantMembership
from tenants.settings_service import get_number_prefix
from tenants.viewsets import AuditedTenantModelViewSet

from .models import (
    Contract,
    Quote,
    QuoteLine,
    RentalOrder,
    ReservationAllocation,
)
from .serializers import (
    AvailabilityQuerySerializer,
    ContractSerializer,
    QuoteLineSerializer,
    QuoteSerializer,
    ReasonSerializer,
    RenewalSerializer,
    RentalOrderSerializer,
    RentalReportSerializer,
    ReservationAllocationSerializer,
    SignContractSerializer,
)
from .services import (
    approve_quote,
    available_assets,
    cancel_order,
    complete_return,
    confirm_order,
    convert_quote_to_order,
    dispatch_order,
    issue_contract,
    recalculate_quote,
    reject_quote,
    renew_order,
    sign_contract,
    submit_quote,
)


def _require_approver(request):
    if request.membership.role not in {Role.OWNER, Role.ADMIN}:
        raise PermissionDenied("Quote approval requires an owner or administrator.")


class QuoteViewSet(AuditedTenantModelViewSet):
    write_roles = (Role.RENTAL,)
    queryset_model = Quote
    queryset_select_related = ("customer", "site", "approved_by", "created_by")
    queryset_prefetch_related = (
        "lines",
        "lines__equipment_model",
        "lines__asset",
        "lines__rate_plan",
    )
    serializer_class = QuoteSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        quote = serializer.save(
            number=next_document_number("quote", get_number_prefix("quote")),
            created_by=self.request.user,
        )
        record_audit("quote.created", actor=self.request.user, obj=quote)

    @transaction.atomic
    def perform_update(self, serializer):
        quote = serializer.save()
        record_audit("quote.updated", actor=self.request.user, obj=quote)

    def perform_destroy(self, instance):
        if instance.status != Quote.Status.DRAFT:
            raise ValidationError({"status": "Only draft quotes can be deleted."})
        super().perform_destroy(instance)

    @extend_schema(request=None, responses=QuoteSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        quote = submit_quote(self.get_object(), actor=request.user)
        return Response(self.get_serializer(quote).data)

    @extend_schema(request=None, responses=QuoteSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        _require_approver(request)
        quote = approve_quote(self.get_object(), actor=request.user)
        return Response(self.get_serializer(quote).data)

    @extend_schema(request=ReasonSerializer, responses=QuoteSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        _require_approver(request)
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        quote = reject_quote(
            self.get_object(),
            actor=request.user,
            reason=payload.validated_data["reason"],
        )
        return Response(self.get_serializer(quote).data)

    @extend_schema(request=None, responses=RentalOrderSerializer)
    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        order = convert_quote_to_order(self.get_object(), actor=request.user)
        return Response(
            RentalOrderSerializer(order, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class QuoteLineViewSet(AuditedTenantModelViewSet):
    write_roles = (Role.RENTAL,)
    queryset_model = QuoteLine
    queryset_select_related = (
        "quote",
        "equipment_model",
        "asset",
        "rate_plan",
    )
    serializer_class = QuoteLineSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        line = serializer.save()
        recalculate_quote(line.quote, actor=self.request.user)
        line.refresh_from_db()
        record_audit("quote_line.created", actor=self.request.user, obj=line)

    @transaction.atomic
    def perform_update(self, serializer):
        line = serializer.save()
        recalculate_quote(line.quote, actor=self.request.user)
        line.refresh_from_db()
        record_audit("quote_line.updated", actor=self.request.user, obj=line)

    @transaction.atomic
    def perform_destroy(self, instance):
        quote = instance.quote
        if quote.lines.count() <= 1:
            raise ValidationError({"line": "A quote must retain at least one line."})
        super().perform_destroy(instance)
        recalculate_quote(quote, actor=self.request.user)


class RentalOrderViewSet(AuditedTenantModelViewSet):
    write_roles = (Role.RENTAL,)
    queryset_model = RentalOrder
    queryset_select_related = ("customer", "site", "confirmed_by", "created_by")
    queryset_prefetch_related = (
        "lines",
        "lines__asset",
        "lines__allocations",
        "lines__allocations__asset",
    )
    serializer_class = RentalOrderSerializer

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Rental orders are created from approved quotes."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @extend_schema(
        parameters=[AvailabilityQuerySerializer],
        responses=AssetSerializer(many=True),
    )
    @action(detail=False, methods=["get"], url_path="availability")
    def availability(self, request):
        payload = AvailabilityQuerySerializer(data=request.query_params)
        payload.is_valid(raise_exception=True)
        assets = available_assets(
            equipment_model=payload.validated_data["equipment_model"],
            start_at=payload.validated_data["start_at"],
            end_at=payload.validated_data["end_at"],
        )
        return Response(AssetSerializer(assets, many=True).data)

    @extend_schema(request=None, responses=RentalOrderSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        order = confirm_order(self.get_object(), actor=request.user)
        return Response(self.get_serializer(order).data)

    @extend_schema(request=None, responses=RentalOrderSerializer)
    @action(detail=True, methods=["post"], url_path="dispatch")
    def dispatch_rental(self, request, pk=None):
        order = dispatch_order(self.get_object(), actor=request.user)
        return Response(self.get_serializer(order).data)

    @extend_schema(request=None, responses=RentalOrderSerializer)
    @action(detail=True, methods=["post"])
    def return_rental(self, request, pk=None):
        order = complete_return(self.get_object(), actor=request.user)
        return Response(self.get_serializer(order).data)

    @extend_schema(request=ReasonSerializer, responses=RentalOrderSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        order = cancel_order(
            self.get_object(),
            actor=request.user,
            reason=payload.validated_data["reason"],
        )
        return Response(self.get_serializer(order).data)

    @extend_schema(request=RenewalSerializer, responses=RentalOrderSerializer)
    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        payload = RenewalSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        asset = get_object_or_404(
            Asset.objects.all(), pk=payload.validated_data.pop("asset")
        )
        order = renew_order(
            self.get_object(),
            actor=request.user,
            asset=asset,
            **payload.validated_data,
        )
        return Response(self.get_serializer(order).data)

    @extend_schema(request=None, responses=ContractSerializer)
    @action(detail=True, methods=["post"], url_path="issue-contract")
    def issue_contract(self, request, pk=None):
        contract = issue_contract(self.get_object(), actor=request.user)
        return Response(
            ContractSerializer(contract, context=self.get_serializer_context()).data
        )

    def perform_update(self, serializer):
        order = serializer.save()
        record_audit("rental_order.updated", actor=self.request.user, obj=order)

    def perform_destroy(self, instance):
        if instance.status != RentalOrder.Status.DRAFT:
            raise ValidationError({"status": "Only draft orders can be deleted."})
        super().perform_destroy(instance)


class ReservationAllocationViewSet(ReadOnlyModelViewSet):
    serializer_class = ReservationAllocationSerializer
    permission_classes = [IsAuthenticated, HasTenantMembership]

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return ReservationAllocation._base_manager.none()
        return ReservationAllocation.objects.select_related(
            "asset", "rental_line", "rental_line__order"
        )


class ContractViewSet(ReadOnlyModelViewSet):
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated, HasTenantMembership]

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return Contract._base_manager.none()
        return (
            Contract.objects.select_related("order")
            .prefetch_related("versions")
            .order_by("-created_at", "-id")
        )

    @extend_schema(request=SignContractSerializer, responses=ContractSerializer)
    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        if request.membership.role not in {
            Role.OWNER,
            Role.ADMIN,
            Role.RENTAL,
        }:
            raise PermissionDenied("Signing requires a rental manager.")
        payload = SignContractSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        contract = sign_contract(
            self.get_object(),
            actor=request.user,
            signed_by_name=payload.validated_data["signed_by_name"],
        )
        return Response(self.get_serializer(contract).data)


@extend_schema(responses=RentalReportSerializer)
class RentalReportView(APIView):
    permission_classes = [IsAuthenticated, HasTenantMembership]

    def get(self, request):
        now = timezone.now()
        quote_statuses = {
            row["status"]: row["count"]
            for row in Quote.objects.values("status").annotate(count=Count("id"))
        }
        order_statuses = {
            row["status"]: row["count"]
            for row in RentalOrder.objects.values("status").annotate(count=Count("id"))
        }
        return Response(
            {
                "quote_status_counts": quote_statuses,
                "order_status_counts": order_statuses,
                "active_orders": order_statuses.get(RentalOrder.Status.ACTIVE, 0),
                "upcoming_orders": RentalOrder.objects.filter(
                    status=RentalOrder.Status.RESERVED,
                    start_at__gte=now,
                    start_at__lte=now + timezone.timedelta(days=7),
                ).count(),
                "overdue_orders": RentalOrder.objects.filter(
                    status=RentalOrder.Status.ACTIVE,
                    end_at__lt=now,
                ).count(),
            }
        )
