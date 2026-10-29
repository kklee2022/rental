from django.test import TestCase

from core.context import tenant_context
from customers.models import Customer
from tests_support.factories import make_customer, make_owner, make_tenant


class CustomerApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = make_tenant("customer-a")
        cls.tenant_b = make_tenant("customer-b")
        cls.owner = make_owner(cls.tenant_a, "customer-owner")
        cls.customer_a = make_customer(cls.tenant_a, "A-001", "Alpha Customer")
        cls.customer_b = make_customer(cls.tenant_b, "B-001", "Beta Customer")

    def setUp(self):
        self.client.force_login(self.owner)

    def test_customer_list_is_tenant_scoped(self):
        response = self.client.get(
            "/api/v1/customers/", HTTP_X_TENANT=self.tenant_a.slug
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["name"] for row in response.json()["results"]],
            ["Alpha Customer"],
        )

    def test_customer_can_be_created_in_active_tenant(self):
        response = self.client.post(
            "/api/v1/customers/",
            {"code": "A-002", "name": "Second Customer"},
            content_type="application/json",
            HTTP_X_TENANT=self.tenant_a.slug,
        )
        self.assertEqual(response.status_code, 201)
        with tenant_context(self.tenant_a):
            self.assertTrue(Customer.objects.filter(code="A-002").exists())

    def test_cannot_select_another_tenants_context(self):
        response = self.client.get(
            "/api/v1/customers/", HTTP_X_TENANT=self.tenant_b.slug
        )
        self.assertEqual(response.status_code, 403)
