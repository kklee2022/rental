from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from fleet.models import Asset

from .models import (
    AssetLogisticsEvent,
    DeliveryReceipt,
    InventoryCount,
    InventoryCountLine,
    LogisticsAttachment,
    TransportJob,
    TransportJobAsset,
)


class TransportJobAssetSerializer(serializers.ModelSerializer):
    asset_number = serializers.CharField(source="asset.asset_number", read_only=True)
    model_name = serializers.CharField(source="asset.model.name", read_only=True)
    qr_code = serializers.CharField(source="asset.qr_code", read_only=True)
    asset_status = serializers.CharField(source="asset.status", read_only=True)

    class Meta:
        model = TransportJobAsset
        fields = (
            "id",
            "asset",
            "asset_number",
            "model_name",
            "qr_code",
            "asset_status",
            "loaded_at",
            "delivered_at",
        )
        read_only_fields = fields


class TransportJobSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.number", read_only=True)
    depot_name = serializers.CharField(source="depot.name", read_only=True)
    destination_location_name = serializers.CharField(
        source="destination_location.name", read_only=True
    )
    destination_site_name = serializers.CharField(
        source="destination_site.name", read_only=True
    )
    destination_site_address = serializers.CharField(
        source="destination_site.address", read_only=True
    )
    customer_name = serializers.CharField(
        source="destination_site.customer.name", read_only=True
    )
    driver_username = serializers.CharField(source="driver.username", read_only=True)
    items = TransportJobAssetSerializer(source="asset_links", many=True, read_only=True)
    asset_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False,
    )

    class Meta:
        model = TransportJob
        fields = (
            "id",
            "number",
            "direction",
            "status",
            "order",
            "order_number",
            "depot",
            "depot_name",
            "destination_location",
            "destination_location_name",
            "destination_site",
            "destination_site_name",
            "destination_site_address",
            "customer_name",
            "driver",
            "driver_username",
            "carrier_name",
            "vehicle",
            "transport_reference",
            "contact_name",
            "contact_phone",
            "scheduled_start",
            "scheduled_end",
            "actual_start",
            "actual_arrival",
            "actual_delivery",
            "completed_at",
            "delay_reason",
            "notes",
            "items",
            "asset_ids",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "number",
            "status",
            "actual_start",
            "actual_arrival",
            "actual_delivery",
            "completed_at",
            "items",
            "created_by",
            "created_at",
            "updated_at",
        )

    @transaction.atomic
    def create(self, validated_data):
        asset_ids = validated_data.pop("asset_ids", [])
        job = TransportJob.objects.create(**validated_data)
        assets = list(Asset.objects.filter(pk__in=set(asset_ids)))
        if len(assets) != len(set(asset_ids)):
            raise serializers.ValidationError(
                {"asset_ids": "One or more assets were not found."}
            )
        for asset in assets:
            TransportJobAsset.objects.create(job=job, asset=asset)
        return job

    @transaction.atomic
    def update(self, instance, validated_data):
        asset_ids = validated_data.pop("asset_ids", None)
        instance = super().update(instance, validated_data)
        if asset_ids is not None:
            assets = list(Asset.objects.filter(pk__in=set(asset_ids)))
            if len(assets) != len(set(asset_ids)):
                raise serializers.ValidationError(
                    {"asset_ids": "One or more assets were not found."}
                )
            instance.asset_links.exclude(asset__in=assets).delete()
            existing = set(instance.asset_links.values_list("asset_id", flat=True))
            for asset in assets:
                if asset.pk not in existing:
                    TransportJobAsset.objects.create(job=instance, asset=asset)
        return instance


class AssetLogisticsEventSerializer(serializers.ModelSerializer):
    asset_number = serializers.CharField(source="asset.asset_number", read_only=True)
    model_name = serializers.CharField(source="asset.model.name", read_only=True)
    job_number = serializers.CharField(source="job.number", read_only=True)
    from_location_name = serializers.CharField(
        source="from_location.name", read_only=True
    )
    to_location_name = serializers.CharField(source="to_location.name", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = AssetLogisticsEvent
        fields = (
            "id",
            "job",
            "job_number",
            "asset",
            "asset_number",
            "model_name",
            "event_type",
            "from_location",
            "from_location_name",
            "to_location",
            "to_location_name",
            "site",
            "site_name",
            "latitude",
            "longitude",
            "occurred_at",
            "source",
            "client_event_id",
            "actor",
            "actor_username",
            "notes",
            "metadata",
            "created_at",
        )
        read_only_fields = fields


class AssetLogisticsEventCreateSerializer(serializers.Serializer):
    job = serializers.IntegerField(required=False, allow_null=True)
    asset_id = serializers.IntegerField(required=False, allow_null=True)
    asset_identifier = serializers.CharField(
        required=False, allow_blank=False, max_length=120
    )
    event_type = serializers.ChoiceField(choices=AssetLogisticsEvent.Type.choices)
    from_location = serializers.IntegerField(required=False, allow_null=True)
    to_location = serializers.IntegerField(required=False, allow_null=True)
    site = serializers.IntegerField(required=False, allow_null=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    occurred_at = serializers.DateTimeField(required=False)
    source = serializers.ChoiceField(
        choices=AssetLogisticsEvent.Source.choices,
        default=AssetLogisticsEvent.Source.MOBILE,
    )
    client_event_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        if not attrs.get("asset_id") and not attrs.get("asset_identifier"):
            raise serializers.ValidationError(
                {"asset_identifier": "Asset ID or asset identifier is required."}
            )
        if attrs.get("event_type") == AssetLogisticsEvent.Type.TRANSFER:
            if not attrs.get("to_location"):
                raise serializers.ValidationError(
                    {"to_location": "Transfer requires a destination location."}
                )
        return attrs


class DeliveryReceiptSerializer(serializers.ModelSerializer):
    job_number = serializers.CharField(source="job.number", read_only=True)
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = DeliveryReceipt
        fields = (
            "id",
            "job",
            "job_number",
            "signer_name",
            "signer_phone",
            "accepted",
            "rejection_reason",
            "signature_data",
            "signed_at",
            "latitude",
            "longitude",
            "client_event_id",
            "actor",
            "actor_username",
            "notes",
            "created_at",
        )
        read_only_fields = ("actor", "actor_username", "created_at")

    def validate(self, attrs):
        accepted = attrs.get("accepted", True)
        rejection_reason = attrs.get("rejection_reason", "")
        if not accepted and not rejection_reason.strip():
            raise serializers.ValidationError(
                {"rejection_reason": "Rejected delivery requires a reason."}
            )
        return attrs


class LogisticsAttachmentSerializer(serializers.ModelSerializer):
    job_number = serializers.CharField(source="job.number", read_only=True)
    asset_number = serializers.CharField(source="asset.asset_number", read_only=True)
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username", read_only=True
    )

    class Meta:
        model = LogisticsAttachment
        fields = (
            "id",
            "job",
            "job_number",
            "event",
            "asset",
            "asset_number",
            "category",
            "file",
            "original_filename",
            "content_type",
            "file_size",
            "captured_at",
            "client_event_id",
            "uploaded_by",
            "uploaded_by_username",
            "created_at",
        )
        read_only_fields = (
            "original_filename",
            "content_type",
            "file_size",
            "uploaded_by",
            "uploaded_by_username",
            "created_at",
        )


class InventoryCountLineSerializer(serializers.ModelSerializer):
    asset_number = serializers.CharField(source="asset.asset_number", read_only=True)
    model_name = serializers.CharField(source="asset.model.name", read_only=True)
    scanned_by_username = serializers.CharField(
        source="scanned_by.username", read_only=True
    )

    class Meta:
        model = InventoryCountLine
        fields = (
            "id",
            "asset",
            "asset_number",
            "model_name",
            "result",
            "scanned_at",
            "scanned_by",
            "scanned_by_username",
            "notes",
        )
        read_only_fields = fields


class InventoryCountSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    started_by_username = serializers.CharField(
        source="started_by.username", read_only=True
    )
    completed_by_username = serializers.CharField(
        source="completed_by.username", read_only=True
    )
    lines = InventoryCountLineSerializer(many=True, read_only=True)

    class Meta:
        model = InventoryCount
        fields = (
            "id",
            "number",
            "location",
            "location_name",
            "status",
            "expected_assets",
            "found_assets",
            "missing_assets",
            "unexpected_assets",
            "started_by",
            "started_by_username",
            "started_at",
            "completed_by",
            "completed_by_username",
            "completed_at",
            "notes",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class InventoryCountCreateSerializer(serializers.Serializer):
    location = serializers.IntegerField(min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class InventoryScanSerializer(serializers.Serializer):
    asset_identifier = serializers.CharField(max_length=120)
    client_event_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class TransportJobActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class MobileLogisticsSummarySerializer(serializers.Serializer):
    scheduled_jobs = serializers.IntegerField()
    active_jobs = serializers.IntegerField()
    awaiting_receipt = serializers.IntegerField()
    pending_collection = serializers.IntegerField()
    recent_events = AssetLogisticsEventSerializer(many=True)


def validation_message(exc):
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "message_dict"):
            return exc.message_dict
        return exc.messages
    return str(exc)
