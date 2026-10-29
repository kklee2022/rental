from django.contrib.auth import get_user_model
from django.test import TestCase

from core.context import TenantContextMissing, get_current_tenant, tenant_context
from core.models import AuditEvent, TenantMismatch, record_audit
from tenants.models import Membership, Plan, Role, Tenant
from tests_support.models import Widget


def make_tenant(slug, plan=None, **kwargs):
    plan = (
        plan
        or Plan.objects.get_or_create(code="standard", defaults={"name": "Standard"})[0]
    )
    return Tenant.objects.create(slug=slug, name=slug.title(), plan=plan, **kwargs)


class TenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_tenant("a")
        cls.b = make_tenant("b")
        with tenant_context(cls.a):
            cls.widget_a = Widget.objects.create(name="a-widget")
        with tenant_context(cls.b):
            cls.widget_b = Widget.objects.create(name="b-widget")

    def test_queries_are_limited_to_active_tenant(self):
        with tenant_context(self.a):
            self.assertEqual(
                list(Widget.objects.values_list("name", flat=True)), ["a-widget"]
            )
            self.assertFalse(Widget.objects.filter(pk=self.widget_b.pk).exists())
        with tenant_context(self.b):
            self.assertEqual(
                list(Widget.objects.values_list("name", flat=True)), ["b-widget"]
            )

    def test_fails_closed_without_tenant(self):
        with self.assertRaises(TenantContextMissing):
            list(Widget.objects.all())
        with self.assertRaises(TenantContextMissing):
            Widget(name="x").save()

    def test_tenant_assigned_automatically(self):
        self.assertEqual(self.widget_a.tenant_id, self.a.pk)

    def test_cannot_save_or_delete_other_tenant_record(self):
        with tenant_context(self.a):
            with self.assertRaises(TenantMismatch):
                self.widget_b.save()
            with self.assertRaises(TenantMismatch):
                self.widget_b.delete()

    def test_all_tenants_manager_is_explicit_escape_hatch(self):
        self.assertEqual(Widget.all_tenants.count(), 2)

    def test_nested_context_restores_outer_tenant(self):
        with tenant_context(self.a):
            with tenant_context(self.b):
                self.assertEqual(Widget.objects.get().name, "b-widget")
            self.assertEqual(Widget.objects.get().name, "a-widget")


class AuditTests(TestCase):
    def test_audit_events_are_append_only(self):
        tenant = make_tenant("audit")
        event = record_audit("test.action", tenant=tenant, obj=tenant, foo="bar")
        self.assertEqual(AuditEvent.objects.get().detail, {"foo": "bar"})
        with self.assertRaises(PermissionError):
            event.save()
        with self.assertRaises(PermissionError):
            event.delete()


class TenantApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        plan = Plan.objects.create(
            code="pro", name="Pro", max_assets=50, features=["asset_import"]
        )
        cls.a = make_tenant("a", plan=plan)
        cls.b = make_tenant("b")
        cls.user = get_user_model().objects.create_user("alice", password="pw")
        Membership.objects.create(user=cls.user, tenant=cls.a, role=Role.RENTAL)
        cls.url = "/api/tenant/"

    def setUp(self):
        self.client.force_login(self.user)

    def test_requires_authentication(self):
        self.client.logout()
        self.assertIn(
            self.client.get(self.url, HTTP_X_TENANT="a").status_code, (401, 403)
        )

    def test_header_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 400)

    def test_member_gets_tenant_and_plan(self):
        response = self.client.get(self.url, HTTP_X_TENANT="a")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["slug"], "a")
        self.assertEqual(data["role"], "rental")
        self.assertEqual(data["plan"]["features"], ["asset_import"])

    def test_non_member_cannot_select_other_tenant(self):
        self.assertEqual(self.client.get(self.url, HTTP_X_TENANT="b").status_code, 403)
        self.assertEqual(
            self.client.get(self.url, HTTP_X_TENANT="missing").status_code, 403
        )

    def test_inactive_membership_is_rejected(self):
        Membership.objects.filter(user=self.user).update(is_active=False)
        self.assertEqual(self.client.get(self.url, HTTP_X_TENANT="a").status_code, 403)

    def test_suspended_tenant_is_rejected(self):
        Tenant.objects.filter(pk=self.a.pk).update(status=Tenant.Status.SUSPENDED)
        self.assertEqual(self.client.get(self.url, HTTP_X_TENANT="a").status_code, 403)

    def test_tenant_context_is_cleared_after_request(self):
        self.client.get(self.url, HTTP_X_TENANT="a")
        self.assertIsNone(get_current_tenant())
