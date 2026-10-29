from rest_framework import serializers

from .models import (
    Contract,
    ContractVersion,
    Quote,
    QuoteLine,
    RentalLine,
    RentalOrder,
    ReservationAllocation,
)


class QuoteLineSerializer(serializers.ModelSerializer):
    equipment_model_name = serializers.CharField(
        source="equipment_model.name", read_only=True
    )
    asset_number = serializers.CharField(source="asset.asset_number", read_only=True)
    rate_plan_name = serializers.CharField(source="rate_plan.name", read_only=True)

    class Meta:
        model = QuoteLine
        fields = (
            "id",
            "quote",
            "line_type",
            "description",
            "equipment_model",
            "equipment_model_name",
            "asset",
            "asset_number",
            "rate_plan",
            "rate_plan_name",
            "quantity",
            "start_at",
            "end_at",
            "pricing_unit",
            "unit_price",
            "discount_amount",
            "line_total",
            "tax_amount",
            "price_snapshot",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "line_total",
            "tax_amount",
            "price_snapshot",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        quote = attrs.get("quote", getattr(self.instance, "quote", None))
        if quote is None:
            raise serializers.ValidationError({"quote": "Quote is required."})
        if quote.status != Quote.Status.DRAFT:
            raise serializers.ValidationError(
                {"quote": "Only draft quotes can be edited."}
            )
        if self.instance is not None and quote.pk != self.instance.quote_id:
            raise serializers.ValidationError(
                {"quote": "A quote line cannot be moved to another quote."}
            )
        asset = attrs.get("asset", getattr(self.instance, "asset", None))
        equipment_model = attrs.get(
            "equipment_model", getattr(self.instance, "equipment_model", None)
        )
        if asset and equipment_model and asset.model_id != equipment_model.pk:
            raise serializers.ValidationError(
                {"asset": "Asset does not match the equipment model."}
            )
        return attrs


class QuoteSerializer(serializers.ModelSerializer):
    lines = QuoteLineSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)
    approved_by_username = serializers.CharField(
        source="approved_by.username", read_only=True
    )

    class Meta:
        model = Quote
        fields = (
            "id",
            "number",
            "customer",
            "customer_name",
            "site",
            "site_name",
            "status",
            "valid_until",
            "currency",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "deposit_total",
            "price_snapshot",
            "notes",
            "approved_by",
            "approved_by_username",
            "approved_at",
            "rejected_reason",
            "created_by",
            "created_at",
            "updated_at",
            "lines",
        )
        read_only_fields = (
            "number",
            "status",
            "currency",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "deposit_total",
            "price_snapshot",
            "approved_by",
            "approved_at",
            "rejected_reason",
            "created_by",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        site = attrs.get("site", getattr(self.instance, "site", None))
        if site and customer and site.customer_id != customer.pk:
            raise serializers.ValidationError(
                {"site": "Site does not belong to the selected customer."}
            )
        if self.instance and self.instance.status != Quote.Status.DRAFT:
            if set(attrs) - {"notes"}:
                raise serializers.ValidationError(
                    {"status": "Only notes can be changed after submission."}
                )
        return attrs


class ReservationAllocationSerializer(serializers.ModelSerializer):
    asset_number = serializers.CharField(source="asset.asset_number", read_only=True)

    class Meta:
        model = ReservationAllocation
        fields = (
            "id",
            "rental_line",
            "asset",
            "asset_number",
            "start_at",
            "end_at",
            "status",
            "hold_expires_at",
            "created_by",
            "created_at",
        )
        read_only_fields = fields


class RentalLineSerializer(serializers.ModelSerializer):
    asset_number = serializers.CharField(source="asset.asset_number", read_only=True)
    allocations = ReservationAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = RentalLine
        fields = (
            "id",
            "order",
            "quote_line",
            "line_type",
            "description",
            "equipment_model",
            "asset",
            "asset_number",
            "rate_plan",
            "quantity",
            "start_at",
            "end_at",
            "pricing_unit",
            "unit_price",
            "discount_amount",
            "line_total",
            "tax_amount",
            "price_snapshot",
            "sort_order",
            "allocations",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RentalOrderSerializer(serializers.ModelSerializer):
    lines = RentalLineSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = RentalOrder
        fields = (
            "id",
            "number",
            "quote",
            "customer",
            "customer_name",
            "site",
            "site_name",
            "status",
            "start_at",
            "end_at",
            "prep_buffer_minutes",
            "return_buffer_minutes",
            "currency",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "deposit_total",
            "price_snapshot",
            "confirmed_by",
            "confirmed_at",
            "dispatched_at",
            "returned_at",
            "cancelled_reason",
            "created_by",
            "created_at",
            "updated_at",
            "lines",
        )
        read_only_fields = (
            "number",
            "status",
            "currency",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "deposit_total",
            "price_snapshot",
            "confirmed_by",
            "confirmed_at",
            "dispatched_at",
            "returned_at",
            "cancelled_reason",
            "created_by",
            "created_at",
            "updated_at",
            "lines",
        )

    def validate(self, attrs):
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        site = attrs.get("site", getattr(self.instance, "site", None))
        if site and customer and site.customer_id != customer.pk:
            raise serializers.ValidationError(
                {"site": "Site does not belong to the selected customer."}
            )
        if self.instance and self.instance.status != RentalOrder.Status.DRAFT:
            if set(attrs) - {"notes"}:
                raise serializers.ValidationError(
                    {"status": "Only draft orders can be edited."}
                )
        return attrs


class ContractVersionSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = ContractVersion
        fields = (
            "id",
            "contract",
            "version",
            "snapshot",
            "content_sha256",
            "created_by",
            "created_by_username",
            "created_at",
        )
        read_only_fields = fields


class ContractSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.number", read_only=True)
    versions = ContractVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Contract
        fields = (
            "id",
            "order",
            "order_number",
            "status",
            "current_version",
            "issued_at",
            "signed_at",
            "signed_by_name",
            "created_at",
            "updated_at",
            "versions",
        )
        read_only_fields = fields


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField()


class SignContractSerializer(serializers.Serializer):
    signed_by_name = serializers.CharField(max_length=160)


class RenewalSerializer(serializers.Serializer):
    asset = serializers.IntegerField(min_value=1)
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False
    )
    description = serializers.CharField(
        max_length=240, default="Rental renewal", required=False
    )

    def validate(self, attrs):
        if attrs["end_at"] <= attrs["start_at"]:
            raise serializers.ValidationError(
                {"end_at": "end_at must follow start_at."}
            )
        return attrs


class AvailabilityQuerySerializer(serializers.Serializer):
    equipment_model = serializers.IntegerField(min_value=1)
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()

    def validate(self, attrs):
        if attrs["end_at"] <= attrs["start_at"]:
            raise serializers.ValidationError(
                {"end_at": "end_at must follow start_at."}
            )
        return attrs


class RentalReportSerializer(serializers.Serializer):
    quote_status_counts = serializers.DictField(child=serializers.IntegerField())
    order_status_counts = serializers.DictField(child=serializers.IntegerField())
    active_orders = serializers.IntegerField()
    upcoming_orders = serializers.IntegerField()
    overdue_orders = serializers.IntegerField()
