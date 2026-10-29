from rest_framework import serializers

from .models import CreditNote, Deposit, Invoice, InvoiceLine, Payment, Refund


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = (
            "id",
            "invoice",
            "rental_line",
            "description",
            "quantity",
            "unit_price",
            "tax_amount",
            "line_total",
            "price_snapshot",
            "sort_order",
            "created_at",
        )
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)
    customer_name = serializers.CharField(source="order.customer.name", read_only=True)

    class Meta:
        model = Invoice
        fields = (
            "id",
            "number",
            "order",
            "order_number",
            "customer_name",
            "invoice_type",
            "status",
            "issue_date",
            "due_date",
            "currency",
            "subtotal",
            "tax_total",
            "credit_total",
            "amount_paid",
            "total",
            "balance",
            "price_snapshot",
            "issued_by",
            "issued_at",
            "created_by",
            "created_at",
            "updated_at",
            "lines",
        )
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = Payment
        fields = (
            "id",
            "invoice",
            "invoice_number",
            "amount",
            "method",
            "reference",
            "received_at",
            "status",
            "created_by",
            "created_by_username",
            "created_at",
        )
        read_only_fields = fields


class RefundSerializer(serializers.ModelSerializer):
    processed_by_username = serializers.CharField(
        source="processed_by.username", read_only=True
    )

    class Meta:
        model = Refund
        fields = (
            "id",
            "payment",
            "amount",
            "reason",
            "status",
            "processed_by",
            "processed_by_username",
            "processed_at",
            "created_at",
        )
        read_only_fields = fields


class CreditNoteSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)

    class Meta:
        model = CreditNote
        fields = (
            "id",
            "number",
            "invoice",
            "invoice_number",
            "amount",
            "tax_amount",
            "reason",
            "status",
            "snapshot",
            "issued_by",
            "issued_at",
            "created_at",
        )
        read_only_fields = fields


class DepositSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.number", read_only=True)
    applied_invoice_number = serializers.CharField(
        source="applied_to_invoice.number", read_only=True
    )

    class Meta:
        model = Deposit
        fields = (
            "id",
            "order",
            "order_number",
            "amount",
            "status",
            "received_at",
            "applied_to_invoice",
            "applied_invoice_number",
            "note",
            "created_by",
            "created_at",
        )
        read_only_fields = fields


class InvoiceFromOrderSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)
    invoice_type = serializers.ChoiceField(
        choices=Invoice.Type.choices, default=Invoice.Type.FINAL
    )
    due_days = serializers.IntegerField(min_value=0, max_value=365, default=30)


class PaymentCreateSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    reference = serializers.CharField(max_length=120, allow_blank=True, required=False)
    received_at = serializers.DateTimeField(required=False)


class RefundCreateSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reason = serializers.CharField()


class CreditNoteCreateSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, default=0
    )
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class DepositCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    received_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(allow_blank=True, required=False, default="")


class DepositApplySerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField(min_value=1)


class BillingReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class BillingReportSerializer(serializers.Serializer):
    invoiced = serializers.DecimalField(max_digits=14, decimal_places=2)
    paid = serializers.DecimalField(max_digits=14, decimal_places=2)
    credits = serializers.DecimalField(max_digits=14, decimal_places=2)
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    held_deposits = serializers.DecimalField(max_digits=14, decimal_places=2)
    open_orders = serializers.IntegerField()
    invoice_status_counts = serializers.DictField(child=serializers.IntegerField())
