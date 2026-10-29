from django.test import TestCase

from core.models import AuditEvent
from core.tasks import record_worker_heartbeat
from tenants.models import Plan, Tenant


class TenantTaskTests(TestCase):
    def test_task_binds_tenant_context(self):
        plan = Plan.objects.create(code="task", name="Task")
        tenant = Tenant.objects.create(slug="task", name="Task", plan=plan)

        event_id = record_worker_heartbeat(tenant_id=tenant.pk)

        event = AuditEvent.objects.get(pk=event_id)
        self.assertEqual(event.tenant_id, tenant.pk)
        self.assertEqual(event.action, "job.worker_heartbeat")

    def test_task_requires_explicit_tenant(self):
        with self.assertRaises(ValueError):
            record_worker_heartbeat()
