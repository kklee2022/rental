from django.core.exceptions import ValidationError
from django.db import models

from core.models import TenantScopedModel


class RatePlan(TenantScopedModel):
    class TimeUnit(models.TextChoices):
        HOUR = "hour", "Hour"
        DAY = "day", "Day"
        WEEK = "week", "Week"
        MONTH = "month", "Month"
        FIXED = "fixed", "Fixed"
        PER_UNIT = "per_unit", "Per unit"

    code = models.SlugField(max_length=50)
    name = models.CharField(max_length=160)
    currency = models.CharField(max_length=3, default="HKD")
    time_unit = models.CharField(
        max_length=20, choices=TimeUnit.choices, default=TimeUnit.DAY
    )
    base_unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    minimum_charge = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    deposit_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_rate_plan_code"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValidationError({"valid_to": "valid_to must follow valid_from."})
        if not 0 <= self.tax_rate <= 100:
            raise ValidationError({"tax_rate": "Tax rate must be between 0 and 100."})
        if not 0 <= self.deposit_percentage <= 100:
            raise ValidationError(
                {"deposit_percentage": "Deposit percentage must be 0 to 100."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class RateComponent(TenantScopedModel):
    class Type(models.TextChoices):
        OPERATOR = "operator", "Operator"
        DELIVERY = "delivery", "Delivery"
        ACCESSORY = "accessory", "Accessory"
        USAGE = "usage", "Usage"
        SITE = "site", "Site"
        RISK = "risk", "Risk"
        DISCOUNT = "discount", "Discount"

    class Method(models.TextChoices):
        FIXED = "fixed", "Fixed"
        PER_UNIT = "per_unit", "Per unit"
        PERCENTAGE = "percentage", "Percentage"

    rate_plan = models.ForeignKey(
        RatePlan, on_delete=models.CASCADE, related_name="components"
    )
    equipment_model = models.ForeignKey(
        "fleet.EquipmentModel",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rate_components",
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=160)
    component_type = models.CharField(max_length=20, choices=Type.choices)
    pricing_method = models.CharField(
        max_length=20, choices=Method.choices, default=Method.FIXED
    )
    unit = models.CharField(max_length=40, blank=True)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    included_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxable = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["rate_plan", "code"],
                name="unique_rate_component_code",
            )
        ]

    def __str__(self):
        return f"{self.rate_plan.code}/{self.code}"

    def clean(self):
        if (
            self.pricing_method == self.Method.PERCENTAGE
            and not 0 <= self.unit_price <= 100
        ):
            raise ValidationError(
                {"unit_price": "Percentage components must be between 0 and 100."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
