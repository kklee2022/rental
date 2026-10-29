from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .context import require_current_tenant
from .models import DocumentSequence


@transaction.atomic
def next_document_number(key, prefix):
    """Return a race-safe tenant document number such as Q-2026-000001."""

    require_current_tenant()
    DocumentSequence.objects.select_for_update().get_or_create(
        key=key, defaults={"last_value": 0}
    )
    sequence = DocumentSequence.objects.select_for_update().get(key=key)
    DocumentSequence.objects.filter(pk=sequence.pk).update(
        last_value=F("last_value") + 1
    )
    sequence.refresh_from_db(fields=["last_value"])
    return f"{prefix}-{timezone.localdate().year}-{sequence.last_value:06d}"
