from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import record_audit
from tenants.models import Membership, Plan, Role, Tenant


class Command(BaseCommand):
    help = "Provision a tenant on a plan, optionally with an owner user."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--name", required=True)
        parser.add_argument("--plan", default="standard")
        parser.add_argument(
            "--owner", help="Username of an existing user to make owner"
        )

    @transaction.atomic
    def handle(self, *args, slug, name, plan, owner, **options):
        try:
            plan_obj = Plan.objects.get(code=plan)
        except Plan.DoesNotExist:
            raise CommandError(f"Unknown plan '{plan}'. Create it in the admin first.")
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"Tenant '{slug}' already exists.")

        tenant = Tenant.objects.create(slug=slug, name=name, plan=plan_obj)
        if owner:
            try:
                user = get_user_model().objects.get(
                    **{get_user_model().USERNAME_FIELD: owner}
                )
            except get_user_model().DoesNotExist:
                raise CommandError(f"User '{owner}' does not exist.")
            Membership.objects.create(user=user, tenant=tenant, role=Role.OWNER)
        record_audit("tenant.created", tenant=tenant, obj=tenant, plan=plan)
        self.stdout.write(self.style.SUCCESS(f"Created tenant '{slug}'"))
