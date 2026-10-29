from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core.context import tenant_context
from pricing.models import RateComponent
from pricing.services import calculate_line
from rentals.models import Quote, QuoteLine
from tests_support.factories import (
    make_customer,
    make_owner,
    make_rate_plan,
    make_tenant,
)


class PricingEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("pricing")
        cls.owner = make_owner(cls.tenant, "pricing-owner")
        cls.customer = make_customer(cls.tenant)

    def test_multidimensional_line_keeps_calculation_snapshot(self):
        with tenant_context(self.tenant):
            plan = make_rate_plan(self.tenant)
            RateComponent.objects.create(
                rate_plan=plan,
                code="operator",
                name="Operator",
                component_type=RateComponent.Type.OPERATOR,
                pricing_method=RateComponent.Method.FIXED,
                unit_price=50,
            )
            RateComponent.objects.create(
                rate_plan=plan,
                code="delivery",
                name="Delivery",
                component_type=RateComponent.Type.DELIVERY,
                pricing_method=RateComponent.Method.PERCENTAGE,
                unit_price=10,
            )
            quote = Quote.objects.create(
                number="Q-PRICE",
                customer=self.customer,
                created_by=self.owner,
            )
            start = timezone.now().replace(microsecond=0)
            line = QuoteLine(
                quote=quote,
                description="Three day rental",
                rate_plan=plan,
                quantity=1,
                start_at=start,
                end_at=start + timezone.timedelta(days=3),
                pricing_unit=plan.TimeUnit.DAY,
                unit_price=100,
                discount_amount=20,
            )
            result = calculate_line(line)

        self.assertEqual(Decimal(result["quantity"]), Decimal("3"))
        self.assertEqual(Decimal(result["subtotal"]), Decimal("380.00"))
        self.assertEqual(Decimal(result["discount"]), Decimal("20.00"))
        self.assertEqual(Decimal(result["tax"]), Decimal("36.00"))
        self.assertEqual(Decimal(result["total"]), Decimal("396.00"))
        self.assertEqual(Decimal(result["deposit"]), Decimal("72.00"))
        self.assertEqual(len(result["items"]), 3)
