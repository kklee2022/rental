from celery import Task, shared_task

from .jobs import run_tenant_job
from .models import record_audit


class TenantTask(Task):
    """Celery task base that requires an explicit `tenant_id` keyword."""

    abstract = True

    def __call__(self, *args, **kwargs):
        tenant_id = kwargs.pop("tenant_id", None)
        if tenant_id is None:
            raise ValueError("Tenant background tasks require a tenant_id")
        return run_tenant_job(
            tenant_id,
            lambda: super(TenantTask, self).__call__(*args, **kwargs),
        )


@shared_task(base=TenantTask, ignore_result=True)
def record_worker_heartbeat(**kwargs):
    """Queue-safe smoke test for the tenant background-job boundary."""

    event = record_audit("job.worker_heartbeat")
    return event.pk
