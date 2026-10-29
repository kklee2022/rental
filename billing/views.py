from typing import Any

from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from core.exports import tenant_csv_response
from rentals.models import RentalOrder
from tenants.models import Role
from tenants.permissions import HasTenantMembership, has_role

from .models import CreditNote, Deposit, Invoice, Payment, Refund
from .serializers import (
    CreditNoteCreateSerializer,
    CreditNoteSerializer,
    BillingReportSerializer,
    BillingReasonSerializer,
    DepositApplySerializer,
    DepositCreateSerializer,
    DepositSerializer,
    InvoiceFromOrderSerializer,
    InvoiceSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    RefundCreateSerializer,
    RefundSerializer,
)
from .services import (
    apply_deposit,
    create_invoice_from_order,
    issue_credit_note,
    issue_invoice,
    record_deposit,
    record_payment,
    record_refund,
    refund_deposit,
    void_invoice,
)


class FinanceViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasTenantMembership]
    queryset_model: Any = None
    queryset_select_related: tuple[str, ...] = ()
    queryset_prefetch_related: tuple[str, ...] = ()

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return self.queryset_model._base_manager.none()
        return (
            self.queryset_model.objects.select_related(*self.queryset_select_related)
            .prefetch_related(*self.queryset_prefetch_related)
            .all()
        )

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            permission_classes = [IsAuthenticated, HasTenantMembership]
        else:
            permission_classes = [IsAuthenticated, has_role(Role.FINANCE)]
        return [permission() for permission in permission_classes]


class InvoiceViewSet(FinanceViewSet):
    queryset_model = Invoice
    queryset_select_related = ("order", "order__customer", "issued_by", "created_by")
    queryset_prefetch_related = ("lines",)
    serializer_class = InvoiceSerializer

    @extend_schema(
        request=InvoiceFromOrderSerializer,
        responses=InvoiceSerializer,
    )
    @action(detail=False, methods=["post"], url_path="from-order")
    def from_order(self, request):
        payload = InvoiceFromOrderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        invoice = create_invoice_from_order(
            payload.validated_data["order_id"],
            actor=request.user,
            invoice_type=payload.validated_data["invoice_type"],
            due_days=payload.validated_data["due_days"],
        )
        return Response(self.get_serializer(invoice).data, status=201)

    @extend_schema(request=None, responses=InvoiceSerializer)
    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        invoice = issue_invoice(self.get_object(), actor=request.user)
        return Response(self.get_serializer(invoice).data)

    @extend_schema(request=BillingReasonSerializer, responses=InvoiceSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        payload = BillingReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        invoice = void_invoice(
            self.get_object(),
            actor=request.user,
            reason=payload.validated_data["reason"],
        )
        return Response(self.get_serializer(invoice).data)


class PaymentViewSet(FinanceViewSet):
    queryset_model = Payment
    queryset_select_related = ("invoice", "created_by")
    serializer_class = PaymentSerializer

    @extend_schema(request=PaymentCreateSerializer, responses=PaymentSerializer)
    @action(detail=False, methods=["post"])
    def record(self, request):
        payload = PaymentCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        invoice = get_object_or_404(
            Invoice.objects.all(), pk=payload.validated_data.pop("invoice_id")
        )
        payment = record_payment(invoice, actor=request.user, **payload.validated_data)
        return Response(self.get_serializer(payment).data, status=201)


class RefundViewSet(FinanceViewSet):
    queryset_model = Refund
    queryset_select_related = ("payment", "payment__invoice", "processed_by")
    serializer_class = RefundSerializer

    @extend_schema(request=RefundCreateSerializer, responses=RefundSerializer)
    @action(detail=False, methods=["post"])
    def record(self, request):
        payload = RefundCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        payment = get_object_or_404(
            Payment.objects.all(), pk=payload.validated_data.pop("payment_id")
        )
        refund = record_refund(payment, actor=request.user, **payload.validated_data)
        return Response(self.get_serializer(refund).data, status=201)


class CreditNoteViewSet(FinanceViewSet):
    queryset_model = CreditNote
    queryset_select_related = ("invoice", "issued_by")
    serializer_class = CreditNoteSerializer

    @extend_schema(
        request=CreditNoteCreateSerializer,
        responses=CreditNoteSerializer,
    )
    @action(detail=False, methods=["post"])
    def issue(self, request):
        payload = CreditNoteCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        invoice = get_object_or_404(
            Invoice.objects.all(), pk=payload.validated_data.pop("invoice_id")
        )
        note = issue_credit_note(invoice, actor=request.user, **payload.validated_data)
        return Response(self.get_serializer(note).data, status=201)


class DepositViewSet(FinanceViewSet):
    queryset_model = Deposit
    queryset_select_related = (
        "order",
        "applied_to_invoice",
        "created_by",
    )
    serializer_class = DepositSerializer

    @extend_schema(request=DepositCreateSerializer, responses=DepositSerializer)
    @action(detail=False, methods=["post"])
    def record(self, request):
        payload = DepositCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        deposit = record_deposit(actor=request.user, **payload.validated_data)
        return Response(self.get_serializer(deposit).data, status=201)

    @extend_schema(request=DepositApplySerializer, responses=DepositSerializer)
    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        payload = DepositApplySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        invoice = get_object_or_404(
            Invoice.objects.all(), pk=payload.validated_data["invoice_id"]
        )
        deposit = apply_deposit(self.get_object(), actor=request.user, invoice=invoice)
        return Response(self.get_serializer(deposit).data)

    @extend_schema(request=BillingReasonSerializer, responses=DepositSerializer)
    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        payload = BillingReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        deposit = refund_deposit(
            self.get_object(),
            actor=request.user,
            reason=payload.validated_data["reason"],
        )
        return Response(self.get_serializer(deposit).data)


@extend_schema(responses={(200, "text/csv"): OpenApiTypes.BINARY})
class AccountingExportView(APIView):
    permission_classes = [IsAuthenticated, has_role(Role.FINANCE)]

    def get(self, request):
        return tenant_csv_response(
            model=Invoice,
            columns=[
                ("Invoice", "number"),
                ("Order", lambda invoice: invoice.order.number),
                ("Customer", lambda invoice: invoice.order.customer.name),
                ("Type", lambda invoice: invoice.get_invoice_type_display()),
                ("Status", lambda invoice: invoice.get_status_display()),
                ("Issue date", "issue_date"),
                ("Due date", "due_date"),
                ("Currency", "currency"),
                ("Subtotal", "subtotal"),
                ("Tax", "tax_total"),
                ("Credits", "credit_total"),
                ("Paid", "amount_paid"),
                ("Total", "total"),
                ("Balance", "balance"),
            ],
            filename="accounting-invoices.csv",
            actor=request.user,
        )


@extend_schema(responses=BillingReportSerializer)
class BillingReportView(APIView):
    permission_classes = [IsAuthenticated, HasTenantMembership]

    def get(self, request):
        invoices = Invoice.objects.exclude(status=Invoice.Status.VOID)
        totals = invoices.aggregate(
            invoiced=Sum("total"),
            paid=Sum("amount_paid"),
            credits=Sum("credit_total"),
            outstanding=Sum("balance"),
        )
        status_counts = {
            row["status"]: row["count"]
            for row in invoices.values("status").annotate(count=Count("id"))
        }
        held_deposits = (
            Deposit.objects.filter(status=Deposit.Status.HELD).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        open_orders = RentalOrder.objects.filter(
            status__in=[RentalOrder.Status.RESERVED, RentalOrder.Status.ACTIVE]
        ).count()
        return Response(
            {
                "invoiced": totals["invoiced"] or 0,
                "paid": totals["paid"] or 0,
                "credits": totals["credits"] or 0,
                "outstanding": totals["outstanding"] or 0,
                "held_deposits": held_deposits,
                "open_orders": open_orders,
                "invoice_status_counts": status_counts,
            }
        )
