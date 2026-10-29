import uuid
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from core.context import tenant_context
from fleet.models import Asset, Location
from logistics.models import (
    AssetLogisticsEvent,
    DeliveryReceipt,
    InventoryCount,
    InventoryCountLine,
    LogisticsAttachment,
    TransportJob,
    TransportJobAsset,
)
from tenants.models import Membership, Role
from tests_support.factories import (
    make_asset,
    make_customer,
    make_equipment_model,
    make_location,
    make_owner,
    make_plan,
    make_site,
    make_tenant,
)


class LogisticsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        plan = make_plan("logistics-plan", max_assets=20)
        plan.features = ["asset_import", "mobile_logistics"]
        plan.save()
        cls.tenant = make_tenant("logistics", plan=plan)
        cls.owner = make_owner(cls.tenant, "logistics-owner")
        cls.driver = get_user_model().objects.create_user(
            "logistics-driver", password="pw"
        )
        Membership.objects.create(user=cls.driver, tenant=cls.tenant, role=Role.DRIVER)
        cls.depot = make_location(cls.tenant, "LOG-WH")
        with tenant_context(cls.tenant):
            cls.other_location = Location.objects.create(
                code="LOG-YARD",
                name="Other Yard",
                location_type=Location.Type.YARD,
            )
        cls.model = make_equipment_model(cls.tenant, "LOG-MODEL")
        cls.customer = make_customer(cls.tenant, "LOG-CUSTOMER")
        cls.site = make_site(cls.tenant, cls.customer, "LOG-SITE")
        cls.asset = make_asset(
            cls.tenant,
            cls.model,
            "LOG-ASSET-1",
            location=cls.depot,
            qr_code="QR-LOG-1",
            status=Asset.Status.RESERVED,
        )
        cls.asset_2 = make_asset(
            cls.tenant,
            cls.model,
            "LOG-ASSET-2",
            location=cls.other_location,
            qr_code="QR-LOG-2",
        )
        cls.asset_3 = make_asset(
            cls.tenant,
            cls.model,
            "LOG-ASSET-3",
            location=cls.depot,
            qr_code="QR-LOG-3",
        )
        now = timezone.now()
        with tenant_context(cls.tenant):
            cls.job = TransportJob.objects.create(
                number="T-TEST-001",
                direction=TransportJob.Direction.OUTBOUND,
                depot=cls.depot,
                destination_site=cls.site,
                driver=cls.driver,
                scheduled_start=now,
                scheduled_end=now + timezone.timedelta(hours=3),
                created_by=cls.owner,
            )
            TransportJobAsset.objects.create(job=cls.job, asset=cls.asset)
            TransportJobAsset.objects.create(job=cls.job, asset=cls.asset_3)
            cls.unassigned_job = TransportJob.objects.create(
                number="T-TEST-002",
                direction=TransportJob.Direction.OUTBOUND,
                depot=cls.depot,
                destination_site=cls.site,
                scheduled_start=now + timezone.timedelta(days=1),
                scheduled_end=now + timezone.timedelta(days=1, hours=2),
                created_by=cls.owner,
            )
            TransportJobAsset.objects.create(job=cls.unassigned_job, asset=cls.asset_2)

    def setUp(self):
        self.client.force_login(self.driver)
        self.headers = {"HTTP_X_TENANT": self.tenant.slug}

    def post_event(self, **overrides):
        payload = {
            "job": self.job.pk,
            "asset_identifier": self.asset.qr_code,
            "event_type": AssetLogisticsEvent.Type.PREPARE,
            "source": AssetLogisticsEvent.Source.MOBILE,
            "client_event_id": str(uuid.uuid4()),
        }
        payload.update(overrides)
        return self.client.post(
            "/api/v1/logistics/events/",
            payload,
            content_type="application/json",
            **self.headers,
        )

    def test_scanned_event_chain_updates_asset_and_job_idempotently(self):
        client_event_id = str(uuid.uuid4())
        prepared = self.post_event(client_event_id=client_event_id)
        self.assertEqual(prepared.status_code, 201)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.Status.READY_FOR_DISPATCH)

        repeated = self.post_event(client_event_id=client_event_id)
        self.assertEqual(repeated.status_code, 201)

        loaded = self.post_event(
            event_type=AssetLogisticsEvent.Type.LOAD,
            occurred_at=timezone.now().isoformat(),
        )
        self.assertEqual(loaded.status_code, 201)
        self.asset.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.Status.IN_TRANSIT)
        self.assertEqual(self.job.status, TransportJob.Status.IN_PROGRESS)

        arrived = self.post_event(
            event_type=AssetLogisticsEvent.Type.ARRIVE_SITE,
            site=self.site.pk,
            latitude="22.319300",
            longitude="114.169400",
        )
        self.assertEqual(arrived.status_code, 201)
        self.asset.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.Status.ON_SITE)
        self.assertIsNone(self.asset.location)
        self.assertEqual(self.job.status, TransportJob.Status.AT_SITE)
        with tenant_context(self.tenant):
            self.assertEqual(
                AssetLogisticsEvent.objects.filter(
                    client_event_id=client_event_id
                ).count(),
                1,
            )

    def test_driver_only_sees_and_updates_assigned_jobs(self):
        jobs = self.client.get("/api/v1/logistics/jobs/", **self.headers)
        self.assertEqual(jobs.status_code, 200)
        self.assertEqual([item["id"] for item in jobs.json()["results"]], [self.job.pk])
        hidden = self.client.get(
            f"/api/v1/logistics/jobs/{self.unassigned_job.pk}/", **self.headers
        )
        self.assertEqual(hidden.status_code, 404)
        denied = self.client.post(
            "/api/v1/logistics/events/",
            {
                "job": self.unassigned_job.pk,
                "asset_identifier": self.asset_2.qr_code,
                "event_type": AssetLogisticsEvent.Type.SCAN,
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(denied.status_code, 403)

    def test_delivery_receipt_is_required_before_completing_outbound_job(self):
        with tenant_context(self.tenant):
            self.job.status = TransportJob.Status.AT_SITE
            self.job.save(update_fields=["status", "updated_at"])
        incomplete = self.client.post(
            f"/api/v1/logistics/jobs/{self.job.pk}/complete/",
            {},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(incomplete.status_code, 400)

        receipt = self.client.post(
            "/api/v1/logistics/delivery-receipts/",
            {
                "job": self.job.pk,
                "signer_name": "Raymond Chan",
                "accepted": True,
                "signature_data": "data:image/png;base64,AAAA",
                "client_event_id": str(uuid.uuid4()),
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(receipt.status_code, 201)
        complete = self.client.post(
            f"/api/v1/logistics/jobs/{self.job.pk}/complete/",
            {},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(complete.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, TransportJob.Status.COMPLETED)
        with tenant_context(self.tenant):
            self.assertEqual(DeliveryReceipt.objects.filter(job=self.job).count(), 1)

    def test_rejected_receipt_requires_reason(self):
        with tenant_context(self.tenant):
            self.job.status = TransportJob.Status.AT_SITE
            self.job.save(update_fields=["status", "updated_at"])
        response = self.client.post(
            "/api/v1/logistics/delivery-receipts/",
            {
                "job": self.job.pk,
                "signer_name": "Raymond Chan",
                "accepted": False,
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_inventory_count_records_found_missing_and_unexpected_assets(self):
        self.client.force_login(self.owner)
        started = self.client.post(
            "/api/v1/logistics/inventory-counts/",
            {"location": self.depot.pk},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(started.status_code, 201)
        count_id = started.json()["id"]
        found = self.client.post(
            f"/api/v1/logistics/inventory-counts/{count_id}/scan/",
            {"asset_identifier": self.asset.qr_code},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(found.status_code, 200)
        unexpected = self.client.post(
            f"/api/v1/logistics/inventory-counts/{count_id}/scan/",
            {"asset_identifier": self.asset_2.qr_code},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(unexpected.status_code, 200)
        completed = self.client.post(
            f"/api/v1/logistics/inventory-counts/{count_id}/complete/",
            {},
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(completed.status_code, 200)
        body = completed.json()
        self.assertEqual(body["expected_assets"], 2)
        self.assertEqual(body["found_assets"], 1)
        self.assertEqual(body["missing_assets"], 1)
        self.assertEqual(body["unexpected_assets"], 1)
        with tenant_context(self.tenant):
            count = InventoryCount.objects.get(pk=count_id)
            self.assertEqual(
                count.lines.get(asset=self.asset_3).result,
                InventoryCountLine.Result.MISSING,
            )

    def test_transfer_event_updates_last_location(self):
        self.client.force_login(self.owner)
        with tenant_context(self.tenant):
            transfer_job = TransportJob.objects.create(
                number="T-TRANSFER-001",
                direction=TransportJob.Direction.TRANSFER,
                depot=self.depot,
                destination_location=self.other_location,
                scheduled_start=timezone.now(),
                scheduled_end=timezone.now() + timezone.timedelta(hours=1),
                created_by=self.owner,
            )
            TransportJobAsset.objects.create(job=transfer_job, asset=self.asset_3)
        response = self.client.post(
            "/api/v1/logistics/events/",
            {
                "job": transfer_job.pk,
                "asset_identifier": self.asset_3.qr_code,
                "event_type": AssetLogisticsEvent.Type.TRANSFER,
                "to_location": self.other_location.pk,
            },
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        self.asset_3.refresh_from_db()
        self.assertEqual(self.asset_3.location_id, self.other_location.pk)
        self.assertEqual(self.asset_3.status, Asset.Status.AVAILABLE)

    def test_attachment_upload_and_download(self):
        png = BytesIO(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
        )
        upload = SimpleUploadedFile(
            "arrival.png", png.getvalue(), content_type="image/png"
        )
        response = self.client.post(
            "/api/v1/logistics/attachments/",
            {
                "job": self.job.pk,
                "category": LogisticsAttachment.Category.PHOTO,
                "file": upload,
            },
            **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        attachment_id = response.json()["id"]
        download = self.client.get(
            f"/api/v1/logistics/attachments/{attachment_id}/download/",
            **self.headers,
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "image/png")

    def test_cross_tenant_job_is_hidden(self):
        other_plan = make_plan("logistics-other-plan")
        other_plan.features = ["mobile_logistics"]
        other_plan.save()
        other = make_tenant("logistics-other", plan=other_plan)
        other_owner = make_owner(other, "logistics-other-owner")
        self.client.force_login(other_owner)
        response = self.client.get(
            f"/api/v1/logistics/jobs/{self.job.pk}/",
            HTTP_X_TENANT=other.slug,
        )
        self.assertEqual(response.status_code, 404)

    def test_feature_gate_blocks_opt_out_tenant(self):
        self.tenant.plan.features = ["asset_import"]
        self.tenant.plan.save()
        response = self.client.get("/api/v1/logistics/jobs/", **self.headers)
        self.assertEqual(response.status_code, 403)
