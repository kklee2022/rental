from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import TenantScopedModel


class Invoice(TenantScopedModel):
    class Type(models.TextChoices):
        INTERIM = "interim", "Interim"
        FINAL = "final", "Final"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    number = models.CharField(max_length=40)
    order = models.ForeignKey(
        "rentals.RentalOrder", on_delete=models.PROTECT, related_name="invoices"
    )
    invoice_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.FINAL
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    issue_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="HKD")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price_snapshot = models.JSONField(default=dict, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    issued_at = models.DateTimeField(null=True, blank=True)
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
                fields=["tenant", "number"], name="unique_invoice_number"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"]),
            models.Index(fields=["order", "status"]),
        ]

    def clean(self):
        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            raise ValidationError({"due_date": "due_date must follow issue_date."})
        if self.amount_paid < 0 or self.credit_total < 0:
            raise ValidationError("Invoice settlement values cannot be negative.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.number


class InvoiceLine(TenantScopedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    rental_line = models.ForeignKey(
        "rentals.RentalLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="invoice_lines",
    )
    description = models.CharField(max_length=240)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price_snapshot = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["invoice", "sort_order"])]

    def __str__(self):
        return f"{self.invoice.number}: {self.description}"


class Payment(TenantScopedModel):
    class Method(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        CREDIT_CARD = "credit_card", "Credit card"
        FPS = "fps", "FPS"
        CASH = "cash", "Cash"
        DEPOSIT = "deposit", "Deposit"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        REFUNDED = "refunded", "Refunded"
        VOID = "void", "Void"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=30, choices=Method.choices)
    reference = models.CharField(max_length=120, blank=True)
    received_at = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.COMPLETED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        indexes = [models.Index(fields=["invoice", "status"])]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError({"amount": "Payment amount must be positive."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice.number}: {self.amount}"


class Refund(TenantScopedModel):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        VOID = "void", "Void"

    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="refunds"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.COMPLETED
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    processed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-processed_at", "-id"]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError({"amount": "Refund amount must be positive."})


class CreditNote(TenantScopedModel):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        VOID = "void", "Void"

    number = models.CharField(max_length=40)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="credit_notes"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reason = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ISSUED
    )
    snapshot = models.JSONField(default=dict, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    issued_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "number"], name="unique_credit_note_number"
            )
        ]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError({"amount": "Credit amount must be positive."})

    def __str__(self):
        return self.number


class Deposit(TenantScopedModel):
    class Status(models.TextChoices):
        HELD = "held", "Held"
        APPLIED = "applied", "Applied"
        REFUNDED = "refunded", "Refunded"
        FORFEITED = "forfeited", "Forfeited"

    order = models.ForeignKey(
        "rentals.RentalOrder", on_delete=models.PROTECT, related_name="deposits"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.HELD
    )
    received_at = models.DateTimeField()
    applied_to_invoice = models.ForeignKey(
        Invoice,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="applied_deposits",
    )
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-id"]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError({"amount": "Deposit amount must be positive."})
        if self.amount < Decimal("0"):
            raise ValidationError({"amount": "Deposit cannot be negative."})
