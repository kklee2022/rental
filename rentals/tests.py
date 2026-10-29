from django.db import DatabaseError, transaction
from django.test import TestCase
from django.utils import timezone

from core.context import tenant_context
from rentals.models import (
    Contract,
    Quote,
    QuoteLine,
    RentalOrder,
    ReservationAllocation,
)
from rentals.services import (
    approve_quote,
    complete_return,
    confirm_order,
    convert_quote_to_order,
    dispatch_order,
    issue_contract,
    renew_order,
    sign_contract,
    submit_quote,
)
from tests_support.factories import (
    make_asset,
    make_customer,
    make_equipment_model,
    make_owner,
    make_rate_plan,
    make_rental_period,
    make_site,
    make_tenant,
)


class RentalLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("rental-lifecycle")
        cls.owner = make_owner(cls.tenant, "rental-owner")
        cls.customer = make_customer(cls.tenant)
        cls.site = make_site(cls.tenant, cls.customer)
        cls.equipment_model = make_equipment_model(cls.tenant)
        cls.asset_1 = make_asset(cls.tenant, cls.equipment_model, "RENTAL-ASSET-1")
        cls.asset_2 = make_asset(cls.tenant, cls.equipment_model, "RENTAL-ASSET-2")
        cls.rate_plan = make_rate_plan(cls.tenant)
        cls.sequence = 0

    def create_order(self, *, start_at=None, end_at=None, asset=None):
        start_at = start_at or make_rental_period()[0]
        end_at = end_at or (start_at + timezone.timedelta(days=2))
        type(self).sequence += 1
        with tenant_context(self.tenant):
            quote = Quote.objects.create(
                number=f"Q-TEST-{self.sequence}",
                customer=self.customer,
                site=self.site,
                valid_until=timezone.localdate() + timezone.timedelta(days=7),
                created_by=self.owner,
            )
            QuoteLine.objects.create(
                quote=quote,
                line_type=QuoteLine.LineType.EQUIPMENT,
                description="Excavator rental",
                equipment_model=self.equipment_model,
                asset=asset,
                rate_plan=self.rate_plan,
                quantity=1,
                start_at=start_at,
                end_at=end_at,
                pricing_unit=self.rate_plan.TimeUnit.DAY,
                unit_price=100,
            )
            submit_quote(quote, actor=self.owner)
            approve_quote(quote, actor=self.owner)
            order = convert_quote_to_order(quote, actor=self.owner)
        return order

    def test_full_quote_order_renewal_and_contract_flow(self):
        order = self.create_order(asset=self.asset_1)
        with tenant_context(self.tenant):
            order = confirm_order(order, actor=self.owner)
            self.assertEqual(order.status, RentalOrder.Status.RESERVED)
            self.asset_1.refresh_from_db()
            self.assertEqual(self.asset_1.status, self.asset_1.Status.RESERVED)
            order = dispatch_order(order, actor=self.owner)
            self.assertEqual(order.status, RentalOrder.Status.ACTIVE)
            self.asset_1.refresh_from_db()
            self.assertEqual(self.asset_1.status, self.asset_1.Status.IN_TRANSIT)

            renewal_end = order.end_at + timezone.timedelta(days=1)
            order = renew_order(
                order,
                actor=self.owner,
                start_at=order.end_at,
                end_at=renewal_end,
                asset=self.asset_1,
                description="One day renewal",
            )
            self.assertEqual(order.end_at, renewal_end)
            self.assertEqual(
                ReservationAllocation.objects.filter(
                    rental_line__order=order,
                    asset=self.asset_1,
                    status=ReservationAllocation.Status.CONFIRMED,
                ).count(),
                2,
            )

            contract = issue_contract(order, actor=self.owner)
            contract = sign_contract(
                contract, actor=self.owner, signed_by_name="Alice Customer"
            )
            self.assertEqual(contract.status, Contract.Status.SIGNED)
            self.assertEqual(contract.versions.count(), 2)
            first_version = contract.versions.first()
            self.assertEqual(len(first_version.content_sha256), 64)
            with self.assertRaises(PermissionError):
                first_version.save()

            order = complete_return(order, actor=self.owner)
            self.assertEqual(order.status, RentalOrder.Status.COMPLETED)
            self.asset_1.refresh_from_db()
            self.assertEqual(self.asset_1.status, self.asset_1.Status.RETURN_INSPECTION)

    def test_overlapping_allocation_is_rejected(self):
        order = self.create_order(asset=self.asset_1)
        with tenant_context(self.tenant):
            confirm_order(order, actor=self.owner)
        conflicting = self.create_order(
            start_at=order.start_at,
            end_at=order.start_at + timezone.timedelta(hours=1),
            asset=self.asset_1,
        )
        with tenant_context(self.tenant):
            with self.assertRaisesMessage(Exception, "unavailable"):
                confirm_order(conflicting, actor=self.owner)

    def test_database_constraint_rejects_direct_overlap(self):
        order = self.create_order(asset=self.asset_1)
        with tenant_context(self.tenant):
            confirm_order(order, actor=self.owner)
        conflicting = self.create_order(
            start_at=order.start_at,
            end_at=order.start_at + timezone.timedelta(hours=1),
            asset=self.asset_1,
        )
        with tenant_context(self.tenant):
            line = conflicting.lines.get()
            with self.assertRaises(DatabaseError):
                with transaction.atomic():
                    ReservationAllocation.objects.create(
                        rental_line=line,
                        asset=self.asset_1,
                        start_at=line.start_at,
                        end_at=line.end_at,
                    )

    def test_adjacent_periods_are_allowed(self):
        first = self.create_order(asset=self.asset_1)
        with tenant_context(self.tenant):
            first = confirm_order(first, actor=self.owner)
        second = self.create_order(
            start_at=first.end_at,
            end_at=first.end_at + timezone.timedelta(days=1),
            asset=self.asset_1,
        )
        with tenant_context(self.tenant):
            second = confirm_order(second, actor=self.owner)
        self.assertEqual(second.status, RentalOrder.Status.RESERVED)

    def test_approved_price_snapshot_is_not_rewritten_by_rate_changes(self):
        order = self.create_order(asset=self.asset_1)
        with tenant_context(self.tenant):
            quote = order.quote
            original_total = quote.total
            original_line_total = quote.lines.get().line_total
            self.rate_plan.base_unit_price = 999
            self.rate_plan.save()
            quote.refresh_from_db()
            self.assertEqual(quote.total, original_total)
            self.assertEqual(quote.lines.get().line_total, original_line_total)


class RentalApiWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("rental-api")
        cls.owner = make_owner(cls.tenant, "rental-api-owner")
        cls.customer = make_customer(cls.tenant)
        cls.site = make_site(cls.tenant, cls.customer)
        cls.equipment_model = make_equipment_model(cls.tenant)
        cls.asset_1 = make_asset(cls.tenant, cls.equipment_model, "API-ASSET-1")
        cls.asset_2 = make_asset(cls.tenant, cls.equipment_model, "API-ASSET-2")
        cls.rate_plan = make_rate_plan(cls.tenant)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_quote_to_order_workflow_through_api(self):
        headers = {"HTTP_X_TENANT": self.tenant.slug}
        start = timezone.now().replace(microsecond=0) + timezone.timedelta(days=2)
        end = start + timezone.timedelta(days=2)
        quote_response = self.client.post(
            "/api/v1/quotes/",
            {
                "customer": self.customer.pk,
                "site": self.site.pk,
                "valid_until": (
                    timezone.localdate() + timezone.timedelta(days=7)
                ).isoformat(),
            },
            content_type="application/json",
            **headers,
        )
        self.assertEqual(quote_response.status_code, 201)
        quote_id = quote_response.json()["id"]
        line_response = self.client.post(
            "/api/v1/quote-lines/",
            {
                "quote": quote_id,
                "line_type": "equipment",
                "description": "API excavator",
                "equipment_model": self.equipment_model.pk,
                "asset": self.asset_1.pk,
                "rate_plan": self.rate_plan.pk,
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
                "pricing_unit": "day",
                "unit_price": "100.00",
            },
            content_type="application/json",
            **headers,
        )
        self.assertEqual(line_response.status_code, 201)
        self.assertEqual(line_response.json()["line_total"], "220.00")
        self.assertEqual(
            self.client.post(
                f"/api/v1/quotes/{quote_id}/submit/", **headers
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/quotes/{quote_id}/approve/", **headers
            ).status_code,
            200,
        )
        convert_response = self.client.post(
            f"/api/v1/quotes/{quote_id}/convert/", **headers
        )
        self.assertEqual(convert_response.status_code, 201)
        order_id = convert_response.json()["id"]
        confirm_response = self.client.post(
            f"/api/v1/rental-orders/{order_id}/confirm/", **headers
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_response.json()["status"], "reserved")

        availability = self.client.get(
            "/api/v1/rental-orders/availability/",
            {
                "equipment_model": self.equipment_model.pk,
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
            **headers,
        )
        self.assertEqual(availability.status_code, 200)
        self.assertEqual(
            [row["asset_number"] for row in availability.json()],
            ["API-ASSET-2"],
        )
        report = self.client.get(
            "/api/v1/reports/rentals/",
            **headers,
        )
        self.assertEqual(report.status_code, 200)
        self.assertEqual(
            report.json()["order_status_counts"][RentalOrder.Status.RESERVED], 1
        )
