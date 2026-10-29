from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from billing.services import create_invoice_from_order
from core.context import tenant_context
from pricing.models import RatePlan
from rentals.models import Quote, QuoteLine, RentalOrder
from rentals.services import convert_quote_to_order
from tenants.models import Membership, Plan, Role, TenantSettings
from tests_support.factories import (
    make_customer,
    make_equipment_model,
    make_location,
    make_owner,
    make_site,
    make_tenant,
)


class TenantSettingsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        plan = Plan.objects.create(
            code="settings-plan",
            name="Settings",
            max_users=3,
            features=["asset_import"],
        )
        cls.tenant = make_tenant("settings", plan=plan)
        cls.owner = make_owner(cls.tenant, "settings-owner")
        cls.viewer = get_user_model().objects.create_user(
            "settings-viewer", password="pw"
        )
        Membership.objects.create(user=cls.viewer, tenant=cls.tenant, role=Role.VIEWER)

    def setUp(self):
        self.client.force_login(self.owner)
        self.headers = {"HTTP_X_TENANT": self.tenant.slug}

    def test_settings_defaults_and_update(self):
        response = self.client.get("/api/v1/settings/", **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["company_name"], self.tenant.name)
        self.assertEqual(response.json()["quote_prefix"], "Q")

        updated = self.client.patch(
            "/api/v1/settings/",
            {
                "company_name": "Harbour Machinery Limited",
                "customer_prefix": "cus",
                "quote_prefix": "qt",
                "rental_prefix": "lease",
                "invoice_prefix": "bill",
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, "Harbour Machinery Limited")
        with tenant_context(self.tenant):
            settings = TenantSettings.objects.get(tenant=self.tenant)
        self.assertEqual(settings.customer_prefix, "CUS")
        self.assertEqual(settings.quote_prefix, "QT")
        self.assertEqual(settings.rental_prefix, "LEASE")
        self.assertEqual(settings.invoice_prefix, "BILL")

    def test_invalid_prefix_and_viewer_are_rejected(self):
        invalid = self.client.patch(
            "/api/v1/settings/",
            {"quote_prefix": "bad prefix"},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(invalid.status_code, 400)

        self.client.force_login(self.viewer)
        denied = self.client.get("/api/v1/settings/", **self.headers)
        self.assertEqual(denied.status_code, 403)

    def test_user_crud_and_quota(self):
        created = self.client.post(
            "/api/v1/users/",
            {
                "username": "warehouse.lead",
                "email": "lead@example.com",
                "password": "strong-pass-123",
                "role": Role.WAREHOUSE,
                "is_active": True,
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(created.status_code, 201)
        membership_id = created.json()["id"]
        user = get_user_model().objects.get(username="warehouse.lead")
        self.assertTrue(user.check_password("strong-pass-123"))

        updated = self.client.patch(
            f"/api/v1/users/{membership_id}/",
            {
                "email": "lead-updated@example.com",
                "role": Role.ADMIN,
                "is_active": False,
                "password": "changed-password-456",
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(updated.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "lead-updated@example.com")
        self.assertTrue(user.check_password("changed-password-456"))
        membership = Membership.objects.get(pk=membership_id)
        self.assertEqual(membership.role, Role.ADMIN)
        self.assertFalse(membership.is_active)

        deleted = self.client.delete(f"/api/v1/users/{membership_id}/", **self.headers)
        self.assertEqual(deleted.status_code, 204)
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())

    def test_user_quota_is_enforced(self):
        second = self.client.post(
            "/api/v1/users/",
            {
                "username": "second-user",
                "password": "strong-pass-123",
                "role": Role.VIEWER,
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(second.status_code, 201)
        third = self.client.post(
            "/api/v1/users/",
            {
                "username": "third-user",
                "password": "strong-pass-123",
                "role": Role.VIEWER,
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(third.status_code, 400)

    def test_duplicate_existing_user_is_rejected(self):
        response = self.client.post(
            "/api/v1/users/",
            {
                "existing_user_id": self.viewer.pk,
                "role": Role.RENTAL,
                "is_active": True,
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_administrator_cannot_manage_owner_memberships(self):
        membership = Membership.objects.get(user=self.viewer, tenant=self.tenant)
        membership.role = Role.ADMIN
        membership.save(update_fields=["role"])
        self.client.force_login(self.viewer)

        promote = self.client.post(
            "/api/v1/users/",
            {
                "username": "new-owner",
                "password": "strong-pass-123",
                "role": Role.OWNER,
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(promote.status_code, 400)

        owner_membership = Membership.objects.get(user=self.owner, tenant=self.tenant)
        remove = self.client.delete(
            f"/api/v1/users/{owner_membership.pk}/", **self.headers
        )
        self.assertEqual(remove.status_code, 403)


class PrefixUsageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("prefixes")
        cls.owner = make_owner(cls.tenant, "prefix-owner")
        cls.customer = make_customer(cls.tenant, "PREFIX-CUSTOMER")
        cls.site = make_site(cls.tenant, cls.customer, "PREFIX-SITE")
        cls.model = make_equipment_model(
            cls.tenant, "PUMP-100", category_prefix="PUMP-MODEL"
        )
        cls.location = make_location(cls.tenant, "PREFIX-WH")
        with tenant_context(cls.tenant):
            settings = TenantSettings.objects.create(
                customer_prefix="CUS",
                quote_prefix="QT",
                rental_prefix="LEASE",
                invoice_prefix="BILL",
            )
            settings.save()

    def setUp(self):
        self.client.force_login(self.owner)
        self.headers = {"HTTP_X_TENANT": self.tenant.slug}

    def test_customer_and_asset_numbers_are_generated_from_prefixes(self):
        customer_response = self.client.post(
            "/api/v1/customers/",
            {"name": "Auto Customer"},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(customer_response.status_code, 201)
        self.assertRegex(customer_response.json()["code"], r"^CUS-\d{4}-\d{6}$")

        asset_response = self.client.post(
            "/api/v1/assets/",
            {
                "model": self.model.pk,
                "location": self.location.pk,
                "asset_number": "",
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(asset_response.status_code, 201)
        self.assertRegex(
            asset_response.json()["asset_number"], r"^PUMP-MODEL-\d{4}-\d{6}$"
        )

    def test_quote_rental_and_invoice_numbers_use_configured_prefixes(self):
        quote_response = self.client.post(
            "/api/v1/quotes/",
            {"customer": self.customer.pk, "site": self.site.pk},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(quote_response.status_code, 201)
        self.assertRegex(quote_response.json()["number"], r"^QT-\d{4}-\d{6}$")

        with tenant_context(self.tenant):
            rate_plan = RatePlan.objects.create(
                code="prefix-rate",
                name="Prefix rate",
                time_unit=RatePlan.TimeUnit.DAY,
                base_unit_price=Decimal("100"),
            )
            quote = Quote.objects.create(
                number="QT-MANUAL",
                customer=self.customer,
                site=self.site,
                status=Quote.Status.APPROVED,
                price_snapshot={"demo": True},
                created_by=self.owner,
            )
            quote.lines.create(
                line_type=QuoteLine.LineType.EQUIPMENT,
                description="PUMP-100 rental",
                equipment_model=self.model,
                rate_plan=rate_plan,
                quantity=Decimal("1"),
                start_at=timezone.now(),
                end_at=timezone.now() + timezone.timedelta(days=1),
                pricing_unit=RatePlan.TimeUnit.DAY,
                unit_price=Decimal("100"),
                line_total=Decimal("100"),
            )
            order = convert_quote_to_order(quote, actor=self.owner)
            self.assertRegex(order.number, r"^LEASE-\d{4}-\d{6}$")
            order.status = RentalOrder.Status.RESERVED
            order.save(update_fields=["status", "updated_at"])
            invoice = create_invoice_from_order(order.pk, actor=self.owner)
            self.assertRegex(invoice.number, r"^BILL-\d{4}-\d{6}$")

    def test_referenced_asset_category_cannot_be_deleted(self):
        response = self.client.delete(
            f"/api/v1/equipment-categories/{self.model.category_id}/",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)
