from django.db import models

from core.models import TenantScopedModel


class Widget(TenantScopedModel):
    """Concrete tenant-scoped model used only by the isolation tests."""

    name = models.CharField(max_length=50)
