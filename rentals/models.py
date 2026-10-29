import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import AppendOnlyTenantModel, TenantScopedModel
from pricing.models import RatePlan


class Quote(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        CONVERTED = "converted", "Converted"

    number = models.CharField(max_length=40)
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="quotes"
    )
    site = models.ForeignKey(
        "customers.Site",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quotes",
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.DRAFT
    )
    valid_until = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="HKD")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deposit_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price_snapshot = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)
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
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "number"], name="unique_quote_number"
            )
        ]
        indexes = [models.Index(fields=["tenant", "status", "-created_at"])]

    def __str__(self):
        return self.number


class LineBase(TenantScopedModel):
    class LineType(models.TextChoices):
        EQUIPMENT = "equipment", "Equipment"
        OPERATOR = "operator", "Operator"
        DELIVERY = "delivery", "Delivery"
        ACCESSORY = "accessory", "Accessory"
        USAGE = "usage", "Usage"
        SITE = "site", "Site"
        RISK = "risk", "Risk"
        DISCOUNT = "discount", "Discount"

    line_type = models.CharField(
        max_length=20, choices=LineType.choices, default=LineType.EQUIPMENT
    )
    description = models.CharField(max_length=240)
    equipment_model = models.ForeignKey(
        "fleet.EquipmentModel",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    asset = models.ForeignKey(
        "fleet.Asset",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    rate_plan = models.ForeignKey(
        RatePlan,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    pricing_unit = models.CharField(
        max_length=20,
        choices=RatePlan.TimeUnit.choices,
        default=RatePlan.TimeUnit.DAY,
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price_snapshot = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["sort_order", "id"]

    def clean(self):
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError({"end_at": "end_at must follow start_at."})
        if self.asset_id and self.equipment_model_id:
            if self.asset.model_id != self.equipment_model_id:
                raise ValidationError(
                    {"asset": "Asset does not match the selected equipment model."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class QuoteLine(LineBase):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="lines")

    class Meta(LineBase.Meta):
        abstract = False
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["quote", "sort_order"])]

    def __str__(self):
        return f"{self.quote.number}: {self.description}"


class RentalOrder(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RESERVED = "reserved", "Reserved"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=40)
    quote = models.OneToOneField(
        Quote,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rental_order",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="rental_orders"
    )
    site = models.ForeignKey(
        "customers.Site",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rental_orders",
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.DRAFT
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    prep_buffer_minutes = models.PositiveIntegerField(default=0)
    return_buffer_minutes = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="HKD")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deposit_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price_snapshot = models.JSONField(default=dict, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    cancelled_reason = models.TextField(blank=True)
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
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "number"], name="unique_rental_order_number"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "start_at"]),
            models.Index(fields=["customer", "status"]),
        ]

    def clean(self):
        if self.end_at <= self.start_at:
            raise ValidationError({"end_at": "end_at must follow start_at."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.number


class RentalLine(LineBase):
    order = models.ForeignKey(
        RentalOrder, on_delete=models.CASCADE, related_name="lines"
    )
    quote_line = models.ForeignKey(
        QuoteLine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rental_lines",
    )

    class Meta(LineBase.Meta):
        abstract = False
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["order", "sort_order"])]

    def __str__(self):
        return f"{self.order.number}: {self.description}"


class ReservationAllocation(TenantScopedModel):
    class Status(models.TextChoices):
        HELD = "held", "Held"
        CONFIRMED = "confirmed", "Confirmed"
        RELEASED = "released", "Released"

    rental_line = models.ForeignKey(
        RentalLine, on_delete=models.PROTECT, related_name="allocations"
    )
    asset = models.ForeignKey(
        "fleet.Asset", on_delete=models.PROTECT, related_name="reservations"
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CONFIRMED
    )
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_at", "id"]
        indexes = [
            models.Index(fields=["asset", "start_at", "end_at"]),
            models.Index(fields=["rental_line", "status"]),
        ]

    def clean(self):
        if self.end_at <= self.start_at:
            raise ValidationError({"end_at": "end_at must follow start_at."})
        if (
            self.rental_line_id
            and self.asset_id
            and self.rental_line.asset_id
            and self.rental_line.asset_id != self.asset_id
        ):
            raise ValidationError(
                {"asset": "Allocation must match the rental line asset."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Contract(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        SIGNED = "signed", "Signed"
        VOID = "void", "Void"

    order = models.OneToOneField(
        RentalOrder, on_delete=models.PROTECT, related_name="contract"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    current_version = models.PositiveIntegerField(default=0)
    issued_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_by_name = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Contract {self.order.number}"


class ContractVersion(AppendOnlyTenantModel):
    contract = models.ForeignKey(
        Contract, on_delete=models.PROTECT, related_name="versions"
    )
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    content_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["version"]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "version"],
                name="unique_contract_version",
            )
        ]

    @staticmethod
    def hash_snapshot(snapshot):
        canonical = json.dumps(
            snapshot, sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def __str__(self):
        return f"{self.contract} v{self.version}"
