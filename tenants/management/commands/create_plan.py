from django.core.management.base import BaseCommand, CommandError

from core.models import record_audit
from tenants.models import Plan


class Command(BaseCommand):
    help = "Create a tenant subscription plan and its entitlements."

    def add_arguments(self, parser):
        parser.add_argument("code")
        parser.add_argument("--name", required=True)
        parser.add_argument("--max-assets", type=int)
        parser.add_argument("--max-users", type=int)
        parser.add_argument(
            "--feature",
            action="append",
            default=[],
            help="Feature code to enable; repeat for multiple features.",
        )

    def handle(self, *args, code, name, max_assets, max_users, feature, **options):
        if Plan.objects.filter(code=code).exists():
            raise CommandError(f"Plan '{code}' already exists.")
        plan = Plan.objects.create(
            code=code,
            name=name,
            max_assets=max_assets,
            max_users=max_users,
            features=feature,
        )
        record_audit("plan.created", obj=plan, code=plan.code)
        self.stdout.write(self.style.SUCCESS(f"Created plan '{plan.code}'"))
