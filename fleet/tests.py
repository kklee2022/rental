from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.context import tenant_context
from fleet.models import Asset, AssetStatusEvent, MeterReading
from tests_support.factories import (
    make_asset,
    make_equipment_model,
    make_plan,
    make_site,
    make_tenant,
    make_owner,
    make_customer,
)


class AssetLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = make_plan("fleet-plan", max_assets=1)
        cls.tenant = make_tenant("fleet", plan=cls.plan)
        cls.owner = make_owner(cls.tenant, "fleet-owner")
        cls.customer = make_customer(cls.tenant)
        make_site(cls.tenant, cls.customer)
        cls.model = make_equipment_model(cls.tenant)

    def test_asset_plan_quota_is_enforced(self):
        make_asset(self.tenant, self.model, "FLEET-1")
        with tenant_context(self.tenant):
            with self.assertRaises(ValidationError):
                Asset.objects.create(model=self.model, asset_number="FLEET-2")

    def test_status_transitions_create_append_only_events(self):
        asset = make_asset(self.tenant, self.model, "FLEET-3")
        with tenant_context(self.tenant):
            asset.transition_to(
                Asset.Status.PREPARING,
                actor=self.owner,
                reason="Customer collection",
            )
            events = list(AssetStatusEvent.objects.filter(asset=asset))
            with self.assertRaises(ValidationError):
                asset.transition_to(Asset.Status.RETIRED)
            with self.assertRaises(PermissionError):
                events[0].save()
        self.assertEqual(
            {(event.from_status, event.to_status) for event in events},
            {
                ("", Asset.Status.AVAILABLE),
                (Asset.Status.AVAILABLE, Asset.Status.PREPARING),
            },
        )

    def test_meter_readings_move_forward_and_update_asset(self):
        asset = make_asset(self.tenant, self.model, "FLEET-4")
        with tenant_context(self.tenant):
            MeterReading.objects.create(
                asset=asset,
                hours=Decimal("10.50"),
                kilometers=Decimal("200"),
                recorded_at=timezone.now(),
                actor=self.owner,
            )
            asset.refresh_from_db()
            self.assertEqual(asset.current_hours, Decimal("10.50"))
            with self.assertRaises(ValidationError):
                MeterReading.objects.create(
                    asset=asset,
                    hours=Decimal("10.00"),
                    recorded_at=timezone.now(),
                    actor=self.owner,
                )

    def test_fleet_report_returns_status_summary(self):
        make_asset(self.tenant, self.model, "FLEET-REPORT")
        self.client.force_login(self.owner)
        response = self.client.get(
            "/api/v1/reports/fleet/", HTTP_X_TENANT=self.tenant.slug
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_assets"], 1)
        self.assertEqual(response.json()["status_counts"][Asset.Status.AVAILABLE], 1)
