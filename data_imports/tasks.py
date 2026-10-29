from celery import shared_task
from django.utils import timezone

from core.context import tenant_context
from core.models import record_audit
from core.tasks import TenantTask
from tenants.models import Tenant

from .models import ImportBatch
from .services import validate_import_batch


@shared_task(base=TenantTask, ignore_result=True)
def validate_import_batch_task(batch_id, tenant_id=None):
    batch = ImportBatch.objects.select_related("uploaded_by").get(pk=batch_id)
    return validate_import_batch(batch, actor=batch.uploaded_by).pk


@shared_task(ignore_result=True)
def cleanup_expired_import_files():
    tenant_ids = (
        ImportBatch.all_tenants.filter(file_expires_at__lte=timezone.now())
        .exclude(file="")
        .values_list("tenant_id", flat=True)
        .distinct()
    )
    deleted = 0
    for tenant in Tenant.objects.filter(pk__in=tenant_ids):
        with tenant_context(tenant):
            batches = ImportBatch.objects.filter(
                file_expires_at__lte=timezone.now()
            ).exclude(file="")
            for batch in batches:
                batch.file.delete(save=False)
                batch.file = ""
                batch.save(update_fields=["file", "updated_at"])
                record_audit("import.file_expired", obj=batch)
                deleted += 1
    return deleted
