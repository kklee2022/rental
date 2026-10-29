from rest_framework import serializers

from .models import RateComponent, RatePlan


class RateComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateComponent
        fields = (
            "id",
            "rate_plan",
            "equipment_model",
            "code",
            "name",
            "component_type",
            "pricing_method",
            "unit",
            "unit_price",
            "included_quantity",
            "taxable",
            "sort_order",
        )


class RatePlanSerializer(serializers.ModelSerializer):
    components = RateComponentSerializer(many=True, read_only=True)

    class Meta:
        model = RatePlan
        fields = (
            "id",
            "code",
            "name",
            "currency",
            "time_unit",
            "base_unit_price",
            "minimum_charge",
            "tax_rate",
            "deposit_percentage",
            "valid_from",
            "valid_to",
            "is_active",
            "components",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")
