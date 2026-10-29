from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from billing.models import Payment
from billing.services import (
    create_invoice_from_order,
    issue_invoice,
    record_deposit,
    record_payment,
)
from core.context import tenant_context
from core.sequences import next_document_number
from customers.models import Customer, Site
from fleet.models import Asset, EquipmentCategory, EquipmentModel, Location
from logistics.models import (
    AssetLogisticsEvent,
    TransportJob,
    TransportJobAsset,
)
from logistics.services import record_asset_event
from pricing.models import RateComponent, RatePlan
from rentals.models import Quote, QuoteLine, RentalOrder
from rentals.services import (
    approve_quote,
    confirm_order,
    convert_quote_to_order,
    dispatch_order,
    issue_contract,
    submit_quote,
)
from tenants.models import Membership, Plan, Role, Tenant


class Command(BaseCommand):
    help = "Create an idempotent demo tenant with operational rental data."

    def add_arguments(self, parser):
        parser.add_argument("--owner", default="ops.admin")
        parser.add_argument("--password", default="RentalDemo2026!")

    @transaction.atomic
    def handle(self, *args, owner, password, **options):
        user_model = get_user_model()
        plan, _ = Plan.objects.get_or_create(
            code="enterprise-demo",
            defaults={
                "name": "Enterprise Demo",
                "max_assets": 100,
                "max_users": 20,
                "features": ["asset_import", "customer_portal"],
            },
        )
        features = set(plan.features)
        features.update({"asset_import", "customer_portal", "mobile_logistics"})
        if plan.features != sorted(features):
            plan.features = sorted(features)
            plan.save(update_fields=["features"])
        tenant, _ = Tenant.objects.get_or_create(
            slug="north-harbour",
            defaults={"name": "North Harbour Equipment", "plan": plan},
        )
        owner_user, _ = user_model.objects.get_or_create(
            **{user_model.USERNAME_FIELD: owner}
        )
        owner_user.set_password(password)
        owner_user.is_active = True
        owner_user.save(update_fields=["password", "is_active"])
        Membership.objects.update_or_create(
            user=owner_user,
            tenant=tenant,
            defaults={"role": Role.OWNER, "is_active": True},
        )

        with tenant_context(tenant):
            self._seed_operations(tenant, owner_user)

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo ready: tenant={tenant.slug} user={owner} password={password}"
            )
        )

    def _seed_operations(self, tenant, owner):
        category, _ = EquipmentCategory.objects.get_or_create(
            code="earthmoving",
            defaults={"name": "Earthmoving"},
        )
        lifting, _ = EquipmentCategory.objects.get_or_create(
            code="lifting",
            defaults={"name": "Lifting & access"},
        )
        power, _ = EquipmentCategory.objects.get_or_create(
            code="power",
            defaults={"name": "Power & air"},
        )
        yard, _ = Location.objects.get_or_create(
            code="main-yard",
            defaults={
                "name": "North Harbour Yard",
                "location_type": Location.Type.YARD,
            },
        )
        Location.objects.get_or_create(
            code="kowloon-depot",
            defaults={
                "name": "Kowloon Depot",
                "location_type": Location.Type.WAREHOUSE,
            },
        )

        excavator, _ = EquipmentModel.objects.get_or_create(
            code="CAT-320",
            defaults={
                "category": category,
                "name": "CAT 320 Excavator",
                "manufacturer": "Caterpillar",
                "model_number": "320",
                "specifications": {"operating_weight_kg": 22000, "bucket_m3": 1.4},
            },
        )
        boom_lift, _ = EquipmentModel.objects.get_or_create(
            code="GENIE-S45",
            defaults={
                "category": lifting,
                "name": "Genie S-45 Boom Lift",
                "manufacturer": "Genie",
                "model_number": "S-45",
                "specifications": {"working_height_m": 15.8},
            },
        )
        generator, _ = EquipmentModel.objects.get_or_create(
            code="QAS-60",
            defaults={
                "category": power,
                "name": "Atlas Copco QAS 60",
                "manufacturer": "Atlas Copco",
                "model_number": "QAS 60",
                "specifications": {"power_kva": 60},
            },
        )

        assets = []
        for model, number, serial, hours, kilometers, status in (
            (
                excavator,
                "EX-320-01",
                "CAT320-8841",
                "1840.5",
                "0",
                Asset.Status.AVAILABLE,
            ),
            (
                excavator,
                "EX-320-02",
                "CAT320-8842",
                "2210.0",
                "0",
                Asset.Status.AVAILABLE,
            ),
            (boom_lift, "BL-45-01", "GS45-2918", "640.2", "0", Asset.Status.AVAILABLE),
            (
                generator,
                "GEN-60-01",
                "QAS60-7781",
                "312.0",
                "0",
                Asset.Status.AVAILABLE,
            ),
            (
                generator,
                "GEN-60-02",
                "QAS60-7782",
                "918.0",
                "0",
                Asset.Status.MAINTENANCE,
            ),
        ):
            asset, _ = Asset.objects.get_or_create(
                asset_number=number,
                defaults={
                    "model": model,
                    "location": yard,
                    "serial_number": serial,
                    "current_hours": Decimal(hours),
                    "current_kilometers": Decimal(kilometers),
                    "status": status,
                    "created_by": owner,
                },
            )
            assets.append(asset)

        customer, _ = Customer.objects.get_or_create(
            code="CW-001",
            defaults={
                "name": "Chun Wo Construction",
                "legal_name": "Chun Wo Construction Holdings Limited",
                "email": "plant@chunwo.example",
                "phone": "+852 2801 1000",
                "billing_address": "8 Harbour Road, Hong Kong",
                "credit_limit": Decimal("500000"),
            },
        )
        site, _ = Site.objects.get_or_create(
            customer=customer,
            code="KTD-01",
            defaults={
                "name": "Kai Tak Site 3B",
                "address": "Kai Tak Development Area, Kowloon",
                "contact_name": "Raymond Chan",
                "contact_phone": "+852 9123 4488",
            },
        )
        second_customer, _ = Customer.objects.get_or_create(
            code="GM-002",
            defaults={
                "name": "Gammon Engineering",
                "email": "rentals@gammon.example",
                "phone": "+852 2516 8822",
                "credit_limit": Decimal("800000"),
            },
        )
        second_site, _ = Site.objects.get_or_create(
            customer=second_customer,
            code="CWB-02",
            defaults={
                "name": "Causeway Bay Tunnel Works",
                "address": "Great George Street, Causeway Bay",
            },
        )

        daily_rate, _ = RatePlan.objects.get_or_create(
            code="standard-daily",
            defaults={
                "name": "Standard Daily",
                "currency": "HKD",
                "time_unit": RatePlan.TimeUnit.DAY,
                "base_unit_price": Decimal("3200"),
                "minimum_charge": Decimal("3200"),
                "deposit_percentage": Decimal("20"),
            },
        )
        RateComponent.objects.get_or_create(
            rate_plan=daily_rate,
            code="delivery",
            defaults={
                "name": "Delivery",
                "component_type": RateComponent.Type.DELIVERY,
                "pricing_method": RateComponent.Method.FIXED,
                "unit_price": Decimal("800"),
            },
        )
        weekly_rate, _ = RatePlan.objects.get_or_create(
            code="access-weekly",
            defaults={
                "name": "Access Equipment Weekly",
                "time_unit": RatePlan.TimeUnit.WEEK,
                "base_unit_price": Decimal("18500"),
                "minimum_charge": Decimal("18500"),
                "deposit_percentage": Decimal("15"),
            },
        )

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        pending_quote = Quote.objects.filter(
            notes="demo-pending-quote",
            status__in=[Quote.Status.DRAFT, Quote.Status.PENDING_APPROVAL],
        ).first()
        if pending_quote is None:
            pending_quote = Quote.objects.create(
                number=next_document_number("quote", "Q"),
                customer=second_customer,
                site=second_site,
                valid_until=timezone.localdate() + timedelta(days=10),
                notes="demo-pending-quote",
                created_by=owner,
            )
            QuoteLine.objects.create(
                quote=pending_quote,
                line_type=QuoteLine.LineType.EQUIPMENT,
                description="S-45 boom lift, 5 day access package",
                equipment_model=boom_lift,
                rate_plan=weekly_rate,
                quantity=Decimal("1"),
                start_at=now + timedelta(days=3),
                end_at=now + timedelta(days=8),
                pricing_unit=weekly_rate.time_unit,
            )
            submit_quote(pending_quote, actor=owner)

        active_order = RentalOrder.objects.filter(
            price_snapshot__demo_seed=True
        ).first()
        if active_order is None:
            active_quote = Quote.objects.create(
                number="Q-DEMO-0002",
                customer=customer,
                site=site,
                valid_until=timezone.localdate() + timedelta(days=5),
                notes="demo-active-rental",
                created_by=owner,
            )
            QuoteLine.objects.create(
                quote=active_quote,
                line_type=QuoteLine.LineType.EQUIPMENT,
                description="CAT 320 excavator rental",
                equipment_model=excavator,
                asset=assets[0],
                rate_plan=daily_rate,
                quantity=Decimal("1"),
                start_at=now - timedelta(hours=4),
                end_at=now + timedelta(days=3),
                pricing_unit=daily_rate.time_unit,
            )
            submit_quote(active_quote, actor=owner)
            approve_quote(active_quote, actor=owner)
            active_order = convert_quote_to_order(active_quote, actor=owner)
            active_order = confirm_order(active_order, actor=owner)
            active_order = dispatch_order(active_order, actor=owner)
            active_order.price_snapshot["demo_seed"] = True
            active_order.save(update_fields=["price_snapshot", "updated_at"])
            issue_contract(active_order, actor=owner)

            invoice = create_invoice_from_order(active_order.pk, actor=owner)
            invoice = issue_invoice(invoice, actor=owner)
            record_payment(
                invoice,
                actor=owner,
                amount=Decimal("6000"),
                method=Payment.Method.BANK_TRANSFER,
                reference="DEMO-BANK-001",
            )
            record_deposit(
                active_order.pk,
                actor=owner,
                amount=Decimal("5000"),
                note="Demo damage deposit",
            )

        logistics_job, job_created = TransportJob.objects.get_or_create(
            number="T-DEMO-0001",
            defaults={
                "direction": TransportJob.Direction.OUTBOUND,
                "status": TransportJob.Status.IN_PROGRESS,
                "order": active_order,
                "depot": yard,
                "destination_site": site,
                "driver": owner,
                "carrier_name": "North Harbour Transport",
                "vehicle": "NHV-18",
                "transport_reference": "DEL-DEMO-001",
                "contact_name": site.contact_name,
                "contact_phone": site.contact_phone,
                "scheduled_start": now - timedelta(minutes=30),
                "scheduled_end": now + timedelta(hours=2),
                "actual_start": now - timedelta(minutes=20),
                "created_by": owner,
            },
        )
        TransportJobAsset.objects.get_or_create(job=logistics_job, asset=assets[0])
        if job_created:
            record_asset_event(
                actor=owner,
                event_type=AssetLogisticsEvent.Type.LOAD,
                asset=assets[0],
                job=logistics_job,
                source=AssetLogisticsEvent.Source.SCAN,
                occurred_at=now - timedelta(minutes=20),
                notes="Loaded and sealed for Kai Tak Site 3B.",
            )

        collection_job, collection_created = TransportJob.objects.get_or_create(
            number="T-DEMO-0002",
            defaults={
                "direction": TransportJob.Direction.INBOUND,
                "status": TransportJob.Status.SCHEDULED,
                "depot": yard,
                "destination_site": site,
                "driver": owner,
                "carrier_name": "North Harbour Transport",
                "vehicle": "NHV-22",
                "transport_reference": "COL-DEMO-002",
                "contact_name": site.contact_name,
                "contact_phone": site.contact_phone,
                "scheduled_start": now + timedelta(hours=4),
                "scheduled_end": now + timedelta(hours=6),
                "notes": "Confirm site access before departure.",
                "created_by": owner,
            },
        )
        TransportJobAsset.objects.get_or_create(job=collection_job, asset=assets[2])
        if collection_created:
            AssetLogisticsEvent.objects.create(
                asset=assets[2],
                job=collection_job,
                event_type=AssetLogisticsEvent.Type.SCAN,
                source=AssetLogisticsEvent.Source.SCAN,
                actor=owner,
                notes="Collection task prepared from the yard.",
            )
