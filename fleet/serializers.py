from rest_framework import serializers

from .models import (
    Asset,
    AssetStatusEvent,
    EquipmentCategory,
    EquipmentModel,
    Location,
    MeterReading,
)


class EquipmentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentCategory
        fields = ("id", "code", "name", "description")


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ("id", "code", "name", "location_type", "address", "is_active")


class EquipmentModelSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = EquipmentModel
        fields = (
            "id",
            "category",
            "category_name",
            "code",
            "name",
            "manufacturer",
            "model_number",
            "specifications",
            "is_active",
            "created_at",
        )
        read_only_fields = ("created_at",)


class AssetSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source="model.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = Asset
        fields = (
            "id",
            "model",
            "model_name",
            "location",
            "location_name",
            "asset_number",
            "serial_number",
            "registration_number",
            "qr_code",
            "status",
            "status_changed_at",
            "current_hours",
            "current_kilometers",
            "acquired_on",
            "purchase_cost",
            "notes",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "status",
            "status_changed_at",
            "created_by",
            "created_at",
            "updated_at",
        )


class AssetTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Asset.Status.choices)
    reason = serializers.CharField(max_length=240, allow_blank=True, required=False)
    source = serializers.CharField(max_length=60, default="manual")


class AssetStatusEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = AssetStatusEvent
        fields = (
            "id",
            "asset",
            "from_status",
            "to_status",
            "reason",
            "source",
            "actor_username",
            "metadata",
            "created_at",
        )
        read_only_fields = fields


class MeterReadingSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = MeterReading
        fields = (
            "id",
            "asset",
            "hours",
            "kilometers",
            "recorded_at",
            "source",
            "actor",
            "actor_username",
            "notes",
            "created_at",
        )
        read_only_fields = ("actor", "actor_username", "created_at")


class FleetReportSerializer(serializers.Serializer):
    total_assets = serializers.IntegerField()
    allocated_now = serializers.IntegerField()
    unavailable = serializers.IntegerField()
    utilization_percent = serializers.FloatField()
    status_counts = serializers.DictField(child=serializers.IntegerField())
