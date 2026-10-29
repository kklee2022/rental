import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TenantScopedModel


def import_upload_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"imports/{uuid.uuid4().hex}.{extension}"


def import_file_expiry():
    return timezone.now() + timedelta(days=30)


class ImportBatch(TenantScopedModel):
    class Type(models.TextChoices):
        LOCATION = "location", "Locations"
        EQUIPMENT_MODEL = "equipment_model", "Equipment models"
        ASSET = "asset", "Assets"
        ACCESSORY = "accessory", "Accessories"
        METER_READING = "meter_reading", "Opening meter readings"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        VALIDATING = "validating", "Validating"
        PREVIEW_READY = "preview_ready", "Preview ready"
        COMMITTING = "committing", "Committing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        UNDONE = "undone", "Undone"

    class DuplicatePolicy(models.TextChoices):
        ERROR = "error", "Reject duplicate"
        UPDATE = "update", "Update existing"
        SKIP = "skip", "Skip existing"

    import_type = models.CharField(max_length=30, choices=Type.choices)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.UPLOADED
    )
    duplicate_policy = models.CharField(
        max_length=20,
        choices=DuplicatePolicy.choices,
        default=DuplicatePolicy.ERROR,
    )
    file = models.FileField(upload_to=import_upload_path)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField(default=0)
    content_sha256 = models.CharField(max_length=64)
    column_mapping = models.JSONField(default=dict, blank=True)
    mapping_name = models.CharField(max_length=120, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    warning_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    created_rows = models.PositiveIntegerField(default=0)
    updated_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    failure_message = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    committed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    committed_at = models.DateTimeField(null=True, blank=True)
    file_expires_at = models.DateTimeField(default=import_file_expiry)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "import_type", "-created_at"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "content_sha256"]),
        ]

    def __str__(self):
        return f"{self.get_import_type_display()} · {self.original_filename}"

    @property
    def can_commit(self):
        return (
            self.status == self.Status.PREVIEW_READY
            and self.error_rows == 0
            and self.total_rows > 0
        )

    @property
    def can_undo(self):
        return (
            self.status == self.Status.COMPLETED
            and self.import_type
            in {
                self.Type.LOCATION,
                self.Type.EQUIPMENT_MODEL,
                self.Type.ASSET,
                self.Type.ACCESSORY,
            }
            and not self.changes.exclude(action=ImportChange.Action.CREATE).exists()
        )


class ImportRow(TenantScopedModel):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        SKIP = "skip", "Skip"
        ERROR = "error", "Error"

    batch = models.ForeignKey(
        ImportBatch, on_delete=models.CASCADE, related_name="rows"
    )
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField(default=dict)
    normalized_data = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_number"],
                name="unique_import_batch_row",
            )
        ]

    def __str__(self):
        return f"{self.batch_id} row {self.row_number}"


class ImportMapping(TenantScopedModel):
    import_type = models.CharField(max_length=30, choices=ImportBatch.Type.choices)
    name = models.CharField(max_length=120)
    column_mapping = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
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
        ordering = ["import_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "import_type", "name"],
                name="unique_import_mapping_name",
            )
        ]

    def __str__(self):
        return f"{self.get_import_type_display()} · {self.name}"


class ImportChange(TenantScopedModel):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        RETIRE = "retire", "Retire"

    batch = models.ForeignKey(
        ImportBatch, on_delete=models.PROTECT, related_name="changes"
    )
    import_row = models.ForeignKey(
        ImportRow, on_delete=models.PROTECT, related_name="changes"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    object_label = models.CharField(max_length=200, blank=True)
    before_data = models.JSONField(default=dict, blank=True)
    after_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.action} {self.object_type}:{self.object_id}"
