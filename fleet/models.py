from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from core.context import require_current_tenant
from core.models import (
    AppendOnlyTenantModel,
    TenantScopedModel,
)


class EquipmentCategory(TenantScopedModel):
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_equipment_category_code",
            )
        ]

    def __str__(self):
        return self.name


class Location(TenantScopedModel):
    class Type(models.TextChoices):
        WAREHOUSE = "warehouse", "Warehouse"
        YARD = "yard", "Yard"
        SITE = "site", "Customer site"
        REPAIR = "repair", "Repair location"
        OTHER = "other", "Other"

    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    location_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.WAREHOUSE
    )
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_location_code"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class EquipmentModel(TenantScopedModel):
    category = models.ForeignKey(
        EquipmentCategory, on_delete=models.PROTECT, related_name="models"
    )
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=180)
    manufacturer = models.CharField(max_length=120, blank=True)
    model_number = models.CharField(max_length=120, blank=True)
    specifications = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_equipment_model_code"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Asset(TenantScopedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        PREPARING = "preparing", "Preparing"
        READY_FOR_DISPATCH = "ready_for_dispatch", "Ready for dispatch"
        IN_TRANSIT = "in_transit", "In transit"
        ON_SITE = "on_site", "On site"
        PAUSED = "paused", "Paused"
        PENDING_COLLECTION = "pending_collection", "Pending collection"
        RETURN_INSPECTION = "return_inspection", "Return inspection"
        MAINTENANCE = "maintenance", "Maintenance"
        AWAITING_PARTS = "awaiting_parts", "Awaiting parts"
        SAFETY_LOCKED = "safety_locked", "Safety locked"
        RETIRED = "retired", "Retired"
        LOST_WRITE_OFF = "lost_write_off", "Lost / write-off pending"

    ALLOWED_TRANSITIONS = {
        Status.AVAILABLE: {
            Status.RESERVED,
            Status.PREPARING,
            Status.MAINTENANCE,
            Status.SAFETY_LOCKED,
            Status.RETIRED,
        },
        Status.RESERVED: {
            Status.AVAILABLE,
            Status.PREPARING,
            Status.READY_FOR_DISPATCH,
            Status.MAINTENANCE,
            Status.SAFETY_LOCKED,
        },
        Status.PREPARING: {
            Status.AVAILABLE,
            Status.READY_FOR_DISPATCH,
            Status.MAINTENANCE,
            Status.SAFETY_LOCKED,
        },
        Status.READY_FOR_DISPATCH: {
            Status.AVAILABLE,
            Status.IN_TRANSIT,
            Status.MAINTENANCE,
            Status.SAFETY_LOCKED,
        },
        Status.IN_TRANSIT: {
            Status.ON_SITE,
            Status.RETURN_INSPECTION,
            Status.SAFETY_LOCKED,
        },
        Status.ON_SITE: {
            Status.PAUSED,
            Status.PENDING_COLLECTION,
            Status.RETURN_INSPECTION,
            Status.SAFETY_LOCKED,
        },
        Status.PAUSED: {
            Status.ON_SITE,
            Status.PENDING_COLLECTION,
            Status.RETURN_INSPECTION,
            Status.SAFETY_LOCKED,
        },
        Status.PENDING_COLLECTION: {
            Status.IN_TRANSIT,
            Status.RETURN_INSPECTION,
            Status.SAFETY_LOCKED,
        },
        Status.RETURN_INSPECTION: {
            Status.AVAILABLE,
            Status.MAINTENANCE,
            Status.AWAITING_PARTS,
            Status.SAFETY_LOCKED,
            Status.RETIRED,
        },
        Status.MAINTENANCE: {
            Status.AWAITING_PARTS,
            Status.AVAILABLE,
            Status.SAFETY_LOCKED,
            Status.RETIRED,
        },
        Status.AWAITING_PARTS: {
            Status.MAINTENANCE,
            Status.AVAILABLE,
            Status.SAFETY_LOCKED,
        },
        Status.SAFETY_LOCKED: {
            Status.RETURN_INSPECTION,
            Status.MAINTENANCE,
            Status.AVAILABLE,
            Status.RETIRED,
        },
        Status.RETIRED: set(),
        Status.LOST_WRITE_OFF: {Status.RETIRED},
    }

    model = models.ForeignKey(
        EquipmentModel, on_delete=models.PROTECT, related_name="assets"
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="assets",
        null=True,
        blank=True,
    )
    asset_number = models.CharField(max_length=80)
    serial_number = models.CharField(max_length=120, blank=True)
    registration_number = models.CharField(max_length=60, blank=True)
    qr_code = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.AVAILABLE
    )
    status_changed_at = models.DateTimeField(default=timezone.now)
    current_hours = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_kilometers = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    acquired_on = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "asset_number"],
                name="unique_asset_number_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["tenant", "serial_number"],
                condition=~models.Q(serial_number=""),
                name="unique_asset_serial_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["tenant", "qr_code"],
                condition=~models.Q(qr_code=""),
                name="unique_asset_qr_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["model", "status"]),
        ]

    def __str__(self):
        return f"{self.asset_number} ({self.model.name})"

    def _previous_status(self):
        if self._state.adding:
            return None
        return (
            Asset.all_tenants.filter(pk=self.pk)
            .values_list("status", flat=True)
            .first()
        )

    def save(self, *args, **kwargs):
        if kwargs.get("raw"):
            return super().save(*args, **kwargs)

        with transaction.atomic():
            tenant = require_current_tenant()
            if self._state.adding and tenant.plan.max_assets is not None:
                locked_tenant = (
                    type(tenant)
                    .objects.select_for_update()
                    .select_related("plan")
                    .get(pk=tenant.pk)
                )
                if self.__class__.all_tenants.filter(tenant=tenant).count() >= (
                    locked_tenant.plan.max_assets
                ):
                    raise ValidationError(
                        {
                            "max_assets": (
                                f"Plan '{locked_tenant.plan.code}' allows at most "
                                f"{locked_tenant.plan.max_assets} assets."
                            )
                        }
                    )

            previous_status = self._previous_status()
            status_changed = previous_status is not None and (
                previous_status != self.status
            )
            if status_changed:
                if not getattr(self, "_status_transition_allowed", False):
                    raise ValidationError(
                        {"status": "Use transition_to() to change asset status."}
                    )
                allowed = self.ALLOWED_TRANSITIONS.get(previous_status, set())
                if self.status not in allowed:
                    raise ValidationError(
                        {
                            "status": (
                                f"Cannot transition from {previous_status} "
                                f"to {self.status}."
                            )
                        }
                    )
                self.status_changed_at = timezone.now()

            super().save(*args, **kwargs)
            if previous_status is None or status_changed:
                AssetStatusEvent.objects.create(
                    asset=self,
                    from_status=previous_status or "",
                    to_status=self.status,
                    reason=getattr(self, "_status_reason", "Initial status"),
                    source=getattr(self, "_status_source", "system"),
                    actor=getattr(self, "_status_actor", self.created_by),
                )

    @transaction.atomic
    def transition_to(self, new_status, *, actor=None, reason="", source="manual"):
        locked = Asset.objects.select_for_update().get(pk=self.pk)
        if new_status == locked.status:
            return locked
        if new_status not in self.ALLOWED_TRANSITIONS.get(locked.status, set()):
            raise ValidationError(
                {"status": f"Cannot transition from {locked.status} to {new_status}."}
            )
        locked.status = new_status
        locked._status_transition_allowed = True
        locked._status_actor = actor
        locked._status_reason = reason
        locked._status_source = source
        locked.save(update_fields=["status", "status_changed_at", "updated_at"])
        self.refresh_from_db()
        return self


class AssetStatusEvent(AppendOnlyTenantModel):
    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT, related_name="status_events"
    )
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    reason = models.CharField(max_length=240, blank=True)
    source = models.CharField(max_length=60, default="manual")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["asset", "-created_at"])]

    def __str__(self):
        return f"{self.asset.asset_number}: {self.from_status} -> {self.to_status}"


class MeterReading(AppendOnlyTenantModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        TELEMATICS = "telematics", "Telematics"
        IMPORT = "import", "Import"

    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT, related_name="meter_readings"
    )
    hours = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    kilometers = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.MANUAL
    )
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
        ordering = ["-recorded_at", "-id"]
        indexes = [models.Index(fields=["asset", "-recorded_at"])]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            asset = Asset.objects.select_for_update().get(pk=self.asset_id)
            if self.hours is None and self.kilometers is None:
                raise ValidationError("At least one meter value is required.")
            if self.hours is not None and self.hours < asset.current_hours:
                raise ValidationError({"hours": "Meter reading cannot move backwards."})
            if (
                self.kilometers is not None
                and self.kilometers < asset.current_kilometers
            ):
                raise ValidationError(
                    {"kilometers": "Meter reading cannot move backwards."}
                )
            if self.hours is not None:
                asset.current_hours = self.hours
            if self.kilometers is not None:
                asset.current_kilometers = self.kilometers
            asset.save(
                update_fields=["current_hours", "current_kilometers", "updated_at"]
            )
            self.asset = asset
            return super().save(*args, **kwargs)
