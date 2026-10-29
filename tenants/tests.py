from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from core.models import AuditEvent, record_audit
from tenants.models import Membership, Plan, Role, Tenant
from tenants.permissions import HasFeature


class MembershipApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            code="team", name="Team", max_users=2, features=["asset_import"]
        )
        cls.tenant_a = Tenant.objects.create(
            slug="tenant-a", name="Tenant A", plan=cls.plan
        )
        cls.plan_b = Plan.objects.create(code="other", name="Other", max_users=5)
        cls.tenant_b = Tenant.objects.create(
            slug="tenant-b", name="Tenant B", plan=cls.plan_b
        )
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user("owner", password="pw")
        cls.member = user_model.objects.create_user("member", password="pw")
        cls.new_user = user_model.objects.create_user("new-user", password="pw")
        cls.outsider = user_model.objects.create_user("outsider", password="pw")
        Membership.objects.create(user=cls.owner, tenant=cls.tenant_a, role=Role.OWNER)
        Membership.objects.create(
            user=cls.member, tenant=cls.tenant_a, role=Role.VIEWER
        )
        Membership.objects.create(
            user=cls.outsider, tenant=cls.tenant_b, role=Role.OWNER
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_owner_can_list_only_current_tenant_members(self):
        response = self.client.get(
            "/api/v1/memberships/", HTTP_X_TENANT=self.tenant_a.slug
        )
        self.assertEqual(response.status_code, 200)
        users = {row["username"] for row in response.json()["results"]}
        self.assertEqual(users, {"owner", "member"})

    def test_non_manager_cannot_manage_members(self):
        self.client.force_login(self.member)
        response = self.client.get(
            "/api/v1/memberships/", HTTP_X_TENANT=self.tenant_a.slug
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_select_a_tenant_without_membership(self):
        response = self.client.get(
            "/api/v1/memberships/", HTTP_X_TENANT=self.tenant_b.slug
        )
        self.assertEqual(response.status_code, 403)

    def test_member_creation_enforces_plan_user_quota(self):
        # The plan allows two active users and both seats are already occupied.
        response = self.client.post(
            "/api/v1/memberships/",
            {"user_id": self.new_user.pk, "role": Role.VIEWER, "is_active": True},
            content_type="application/json",
            HTTP_X_TENANT=self.tenant_a.slug,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("max_users", response.json()["detail"])
        self.assertFalse(
            Membership.objects.filter(tenant=self.tenant_a, user=self.new_user).exists()
        )

    def test_owner_cannot_demote_the_last_owner(self):
        response = self.client.patch(
            f"/api/v1/memberships/{self.owner.memberships.get(tenant=self.tenant_a).pk}/",
            {"role": Role.ADMIN},
            content_type="application/json",
            HTTP_X_TENANT=self.tenant_a.slug,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("role", response.json()["detail"])

    def test_membership_changes_are_audited(self):
        membership = self.member.memberships.get(tenant=self.tenant_a)
        response = self.client.patch(
            f"/api/v1/memberships/{membership.pk}/",
            {"role": Role.RENTAL},
            content_type="application/json",
            HTTP_X_TENANT=self.tenant_a.slug,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant_a, action="membership.updated"
            ).exists()
        )

    def test_audit_api_never_returns_another_tenant_events(self):
        record_audit("tenant-a.event", tenant=self.tenant_a)
        record_audit("tenant-b.event", tenant=self.tenant_b)
        response = self.client.get(
            "/api/v1/audit-events/", HTTP_X_TENANT=self.tenant_a.slug
        )
        self.assertEqual(response.status_code, 200)
        actions = {row["action"] for row in response.json()["results"]}
        self.assertEqual(actions, {"tenant-a.event"})

    def test_current_tenant_exposes_plan_entitlements(self):
        response = self.client.get("/api/v1/tenant/", HTTP_X_TENANT=self.tenant_a.slug)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["plan"]["max_users"], 2)
        self.assertEqual(response.json()["plan"]["features"], ["asset_import"])
        self.assertIn("X-Tenant", response["Vary"])

    def test_token_auth_resolves_tenant_without_a_session_cookie(self):
        self.client.logout()
        token, _ = Token.objects.get_or_create(user=self.owner)
        response = self.client.get(
            "/api/v1/memberships/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
            HTTP_X_TENANT=self.tenant_a.slug,
        )
        self.assertEqual(response.status_code, 200)
        denied = self.client.get(
            "/api/v1/memberships/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
            HTTP_X_TENANT=self.tenant_b.slug,
        )
        self.assertEqual(denied.status_code, 403)

    def test_account_endpoint_lists_self_memberships_without_tenant_header(self):
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [tenant["slug"] for tenant in response.json()["tenants"]],
            [self.tenant_a.slug],
        )
        self.assertEqual(
            response.json()["tenants"][0]["membership"]["role"], Role.OWNER
        )

    def test_plan_feature_permission_checks_entitlement(self):
        django_request = APIRequestFactory().get("/")
        django_request.tenant = self.tenant_a
        request = Request(django_request)

        class FeatureView:
            pass

        feature_view = FeatureView()
        feature_view.required_feature = "asset_import"
        self.assertTrue(HasFeature().has_permission(request, feature_view))
        feature_view.required_feature = "missing_feature"
        self.assertFalse(HasFeature().has_permission(request, feature_view))


class MembershipModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(code="solo", name="Solo", max_users=1)
        cls.tenant = Tenant.objects.create(
            slug="solo", name="Solo Tenant", plan=cls.plan
        )
        cls.owner = get_user_model().objects.create_user("solo-owner", password="pw")
        cls.other = get_user_model().objects.create_user("solo-other", password="pw")
        cls.owner_membership = Membership.objects.create(
            user=cls.owner, tenant=cls.tenant, role=Role.OWNER
        )

    def test_model_quota_is_enforced_for_direct_creates(self):
        with self.assertRaises(ValidationError):
            Membership.objects.create(
                user=self.other, tenant=self.tenant, role=Role.VIEWER
            )

    def test_last_owner_cannot_be_deleted(self):
        with self.assertRaises(ValidationError):
            self.owner_membership.delete()

    def test_last_owner_can_be_replaced_atomically(self):
        self.owner_membership.is_active = False
        with self.assertRaises(ValidationError):
            self.owner_membership.save()


class PlatformAdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff = user_model.objects.create_user(
            "tenant-staff", password="pw", is_staff=True
        )
        cls.superuser = user_model.objects.create_superuser(
            "platform-admin", password="pw"
        )

    def test_non_superuser_staff_cannot_open_platform_admin(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/admin/").status_code, 403)

    def test_superuser_can_open_platform_admin(self):
        self.client.force_login(self.superuser)
        self.assertIn(self.client.get("/admin/").status_code, (200, 302))
