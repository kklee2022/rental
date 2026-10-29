from django.db import models

from core.models import TenantScopedModel


class Customer(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        BLOCKED = "blocked", "Blocked"

    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=240, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=60, blank=True)
    billing_address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_customer_code_per_tenant"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Contact(TenantScopedModel):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="contacts"
    )
    name = models.CharField(max_length=160)
    job_title = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=60, blank=True)
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(is_primary=True),
                name="unique_primary_contact_per_customer",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.customer.name})"


class Site(TenantScopedModel):
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="sites"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    address = models.TextField()
    contact_name = models.CharField(max_length=160, blank=True)
    contact_phone = models.CharField(max_length=60, blank=True)
    access_notes = models.TextField(blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["customer__name", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "code"],
                name="unique_site_code_per_customer",
            )
        ]

    def __str__(self):
        return f"{self.customer.code}/{self.code} - {self.name}"
