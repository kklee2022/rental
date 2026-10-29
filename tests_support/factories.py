from django.contrib.auth import get_user_model
from django.utils import timezone

from core.context import tenant_context
from customers.models import Customer, Site
from fleet.models import Asset, EquipmentCategory, EquipmentModel, Location
from pricing.models import RatePlan
from tenants.models import Membership, Plan, Role, Tenant


def make_plan(code="basic", *, max_assets=None, max_users=None):
    return Plan.objects.create(
        code=code,
        name=code.title(),
        max_assets=max_assets,
        max_users=max_users,
        features=["asset_import"],
    )


def make_tenant(slug, *, plan=None):
    return Tenant.objects.create(
        slug=slug,
        name=slug.title(),
        plan=plan or make_plan(f"{slug}-plan"),
    )


def make_owner(tenant, username):
    user = get_user_model().objects.create_user(username, password="pw")
    Membership.objects.create(user=user, tenant=tenant, role=Role.OWNER)
    return user


def make_customer(tenant, code="CUST-1", name="Customer One"):
    with tenant_context(tenant):
        return Customer.objects.create(code=code, name=name)


def make_site(tenant, customer, code="SITE-1"):
    with tenant_context(tenant):
        return Site.objects.create(
            customer=customer,
            code=code,
            name=f"{customer.name} Site",
            address="1 Test Road",
        )


def make_equipment_model(tenant, code="MODEL-1"):
    with tenant_context(tenant):
        category = EquipmentCategory.objects.create(
            code=f"{code}-CAT", name=f"{code} Category"
        )
        return EquipmentModel.objects.create(
            category=category,
            code=code,
            name=f"{code} Equipment",
        )


def make_location(tenant, code="WH-1"):
    with tenant_context(tenant):
        return Location.objects.create(code=code, name="Main Warehouse")


def make_asset(tenant, equipment_model, asset_number="ASSET-1", **kwargs):
    with tenant_context(tenant):
        return Asset.objects.create(
            model=equipment_model,
            asset_number=asset_number,
            **kwargs,
        )


def make_rate_plan(tenant, code="RATE-DAY", **kwargs):
    with tenant_context(tenant):
        return RatePlan.objects.create(
            code=code,
            name="Daily rate",
            time_unit=RatePlan.TimeUnit.DAY,
            base_unit_price=100,
            tax_rate=10,
            deposit_percentage=20,
            **kwargs,
        )


def make_rental_period(days=2):
    start = timezone.now().replace(microsecond=0) + timezone.timedelta(days=1)
    return start, start + timezone.timedelta(days=days)
