from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core.models import AuditEvent
from tenants.models import Membership, Plan, Role, Tenant


class TenantManagementCommandTests(TestCase):
    def test_provision_foundation_through_commands(self):
        user = get_user_model().objects.create_user("provision-owner", password="pw")
        output = StringIO()

        call_command(
            "create_plan",
            "provision",
            name="Provision",
            max_users=5,
            feature=["asset_import"],
            stdout=output,
        )
        call_command(
            "create_tenant",
            "provision",
            name="Provision Tenant",
            plan="provision",
            owner=user.get_username(),
            stdout=output,
        )
        call_command(
            "set_tenant_status",
            "provision",
            "suspended",
            actor=user.get_username(),
            reason="test",
            stdout=output,
        )

        plan = Plan.objects.get(code="provision")
        tenant = Tenant.objects.get(slug="provision")
        membership = Membership.objects.get(tenant=tenant, user=user)
        self.assertEqual(plan.max_users, 5)
        self.assertEqual(plan.features, ["asset_import"])
        self.assertEqual(membership.role, Role.OWNER)
        self.assertEqual(tenant.status, Tenant.Status.SUSPENDED)
        self.assertTrue(
            AuditEvent.objects.filter(tenant=tenant, action="tenant.suspended").exists()
        )
