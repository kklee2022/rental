from django.contrib import admin

from .models import (
    AssetLogisticsEvent,
    DeliveryReceipt,
    InventoryCount,
    InventoryCountLine,
    LogisticsAttachment,
    TransportJob,
    TransportJobAsset,
)


class TransportJobAssetInline(admin.TabularInline):
    model = TransportJobAsset
    extra = 0


@admin.register(TransportJob)
class TransportJobAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "direction",
        "status",
        "depot",
        "destination_site",
        "destination_location",
        "driver",
        "scheduled_start",
    )
    list_filter = ("direction", "status")
    search_fields = ("number", "transport_reference", "vehicle", "carrier_name")
    inlines = (TransportJobAssetInline,)


@admin.register(AssetLogisticsEvent)
class AssetLogisticsEventAdmin(admin.ModelAdmin):
    list_display = ("asset", "event_type", "job", "actor", "occurred_at", "source")
    list_filter = ("event_type", "source")
    search_fields = ("asset__asset_number", "job__number", "notes")
    readonly_fields = (
        "job",
        "asset",
        "event_type",
        "from_location",
        "to_location",
        "site",
        "latitude",
        "longitude",
        "occurred_at",
        "source",
        "client_event_id",
        "actor",
        "notes",
        "metadata",
        "created_at",
    )


@admin.register(DeliveryReceipt)
class DeliveryReceiptAdmin(admin.ModelAdmin):
    list_display = ("job", "signer_name", "accepted", "signed_at", "actor")
    list_filter = ("accepted",)
    search_fields = ("job__number", "signer_name", "signer_phone")


@admin.register(LogisticsAttachment)
class LogisticsAttachmentAdmin(admin.ModelAdmin):
    list_display = ("job", "category", "original_filename", "uploaded_by", "created_at")
    list_filter = ("category",)
    search_fields = ("job__number", "original_filename")


class InventoryCountLineInline(admin.TabularInline):
    model = InventoryCountLine
    extra = 0
    readonly_fields = ("asset", "result", "scanned_at", "scanned_by", "notes")


@admin.register(InventoryCount)
class InventoryCountAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "location",
        "status",
        "expected_assets",
        "found_assets",
        "missing_assets",
        "unexpected_assets",
        "started_at",
    )
    list_filter = ("status", "location")
    inlines = (InventoryCountLineInline,)
