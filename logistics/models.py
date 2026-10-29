import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import AppendOnlyTenantModel, TenantScopedModel


def attachment_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return (
        f"logistics/{instance.tenant_id}/{timezone.now():%Y/%m}/"
        f"{uuid.uuid4().hex}{suffix}"
    )


class TransportJob(TenantScopedModel):
    class Direction(models.TextChoices):
        OUTBOUND = "outbound", "Outbound delivery"
        INBOUND = "inbound", "Inbound collection"
        TRANSFER = "transfer", "Warehouse transfer"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In progress"
        AT_SITE = "at_site", "At site"
        DELIVERED = "delivered", "Delivered"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=40)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )
    order = models.ForeignKey(
        "rentals.RentalOrder",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="logistics_jobs",
    )
    depot = models.ForeignKey(
        "fleet.Location",
        on_delete=models.PROTECT,
        related_name="departure_jobs",
    )
    destination_location = models.ForeignKey(
        "fleet.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="arrival_jobs",
    )
    destination_site = models.ForeignKey(
        "customers.Site",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="logistics_jobs",
    )
    assets = models.ManyToManyField(
        "fleet.Asset", through="TransportJobAsset", related_name="transport_jobs"
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transport_jobs",
    )
    carrier_name = models.CharField(max_length=160, blank=True)
    vehicle = models.CharField(max_length=120, blank=True)
    transport_reference = models.CharField(max_length=120, blank=True)
    contact_name = models.CharField(max_length=160, blank=True)
    contact_phone = models.CharField(max_length=60, blank=True)
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    actual_delivery = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    delay_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_start", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "number"], name="unique_transport_job_number"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "scheduled_start"]),
            models.Index(fields=["driver", "status"]),
        ]

    def clean(self):
        if self.scheduled_end <= self.scheduled_start:
            raise ValidationError({"scheduled_end": "End must follow start."})
        if self.direction == self.Direction.TRANSFER:
            if not self.destination_location_id:
                raise ValidationError(
                    {"destination_location": "A transfer requires a destination."}
                )
            if self.destination_location_id == self.depot_id:
                raise ValidationError(
                    {"destination_location": "Destination must differ from depot."}
                )
        elif not self.destination_site_id:
            raise ValidationError(
                {"destination_site": "Delivery and collection require a site."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.number} ({self.get_direction_display()})"


class TransportJobAsset(TenantScopedModel):
    job = models.ForeignKey(
        TransportJob, on_delete=models.CASCADE, related_name="asset_links"
    )
    asset = models.ForeignKey(
        "fleet.Asset", on_delete=models.PROTECT, related_name="transport_links"
    )
    loaded_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["asset__asset_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "asset"], name="unique_transport_job_asset"
            )
        ]

    def __str__(self):
        return f"{self.job.number}: {self.asset.asset_number}"


class AssetLogisticsEvent(AppendOnlyTenantModel):
    class Type(models.TextChoices):
        SCAN = "scan", "Scan"
        PREPARE = "prepare", "Prepare"
        LOAD = "load", "Load"
        DEPART = "depart", "Depart"
        ARRIVE_SITE = "arrive_site", "Arrive at site"
        UNLOAD = "unload", "Unload"
        DELIVER = "deliver", "Deliver"
        COLLECT_REQUEST = "collect_request", "Request collection"
        COLLECT = "collect", "Collect"
        RECEIVE_WAREHOUSE = "receive_warehouse", "Receive into warehouse"
        TRANSFER = "transfer", "Transfer location"
        INVENTORY = "inventory", "Inventory scan"
        METER = "meter", "Meter update"
        EXCEPTION = "exception", "Exception"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        MOBILE = "mobile", "Mobile"
        OFFLINE = "offline", "Offline sync"
        SCAN = "scan", "QR / barcode"

    job = models.ForeignKey(
        TransportJob,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    asset = models.ForeignKey(
        "fleet.Asset", on_delete=models.PROTECT, related_name="logistics_events"
    )
    event_type = models.CharField(max_length=30, choices=Type.choices)
    from_location = models.ForeignKey(
        "fleet.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    to_location = models.ForeignKey(
        "fleet.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    site = models.ForeignKey(
        "customers.Site",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.MOBILE
    )
    client_event_id = models.UUIDField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_event_id"],
                condition=models.Q(client_event_id__isnull=False),
                name="unique_logistics_client_event",
            )
        ]
        indexes = [
            models.Index(fields=["asset", "-occurred_at"]),
            models.Index(fields=["job", "-occurred_at"]),
        ]

    def __str__(self):
        return f"{self.asset.asset_number}: {self.get_event_type_display()}"


class DeliveryReceipt(AppendOnlyTenantModel):
    job = models.ForeignKey(
        TransportJob, on_delete=models.PROTECT, related_name="receipts"
    )
    signer_name = models.CharField(max_length=160)
    signer_phone = models.CharField(max_length=60, blank=True)
    accepted = models.BooleanField(default=True)
    rejection_reason = models.TextField(blank=True)
    signature_data = models.TextField(blank=True)
    signed_at = models.DateTimeField(default=timezone.now)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    client_event_id = models.UUIDField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-signed_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_event_id"],
                condition=models.Q(client_event_id__isnull=False),
                name="unique_delivery_receipt_client_event",
            )
        ]

    def clean(self):
        if not self.accepted and not self.rejection_reason.strip():
            raise ValidationError(
                {"rejection_reason": "Rejected delivery requires a reason."}
            )
        if len(self.signature_data) > 500_000:
            raise ValidationError({"signature_data": "Signature is too large."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.job.number}: {self.signer_name}"


class LogisticsAttachment(TenantScopedModel):
    class Category(models.TextChoices):
        PHOTO = "photo", "Photo"
        DOCUMENT = "document", "Document"
        SIGNATURE = "signature", "Signature"
        EXCEPTION = "exception", "Exception"

    job = models.ForeignKey(
        TransportJob, on_delete=models.PROTECT, related_name="attachments"
    )
    event = models.ForeignKey(
        AssetLogisticsEvent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="attachments",
    )
    asset = models.ForeignKey(
        "fleet.Asset",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="logistics_attachments",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    file = models.FileField(upload_to=attachment_upload_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    captured_at = models.DateTimeField(default=timezone.now)
    client_event_id = models.UUIDField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-captured_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_event_id"],
                condition=models.Q(client_event_id__isnull=False),
                name="unique_logistics_attachment_client_event",
            )
        ]

    def clean(self):
        if self.file_size > 10 * 1024 * 1024:
            raise ValidationError({"file": "Attachment exceeds 10 MB."})
        if self.event_id and self.event.job_id != self.job_id:
            raise ValidationError({"event": "Event belongs to another job."})
        if self.asset_id and self.asset_id not in self.job.assets.values_list(
            "id", flat=True
        ):
            raise ValidationError({"asset": "Asset is not assigned to this job."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class InventoryCount(TenantScopedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=40)
    location = models.ForeignKey(
        "fleet.Location", on_delete=models.PROTECT, related_name="inventory_counts"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_PROGRESS
    )
    expected_assets = models.PositiveIntegerField(default=0)
    found_assets = models.PositiveIntegerField(default=0)
    missing_assets = models.PositiveIntegerField(default=0)
    unexpected_assets = models.PositiveIntegerField(default=0)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "number"], name="unique_inventory_count_number"
            )
        ]
        indexes = [models.Index(fields=["tenant", "status", "-started_at"])]

    def __str__(self):
        return f"{self.number} @ {self.location.code}"


class InventoryCountLine(TenantScopedModel):
    class Result(models.TextChoices):
        FOUND = "found", "Found"
        MISSING = "missing", "Missing"
        UNEXPECTED = "unexpected", "Unexpected"

    count = models.ForeignKey(
        InventoryCount, on_delete=models.CASCADE, related_name="lines"
    )
    asset = models.ForeignKey(
        "fleet.Asset", on_delete=models.PROTECT, related_name="inventory_lines"
    )
    result = models.CharField(max_length=20, choices=Result.choices)
    scanned_at = models.DateTimeField(default=timezone.now)
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["asset__asset_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["count", "asset"], name="unique_inventory_count_asset"
            )
        ]

    def __str__(self):
        return f"{self.count.number}: {self.asset.asset_number} ({self.result})"
