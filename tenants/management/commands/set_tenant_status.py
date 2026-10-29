from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import record_audit
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Activate or suspend a tenant."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("status", choices=Tenant.Status.values)
        parser.add_argument("--actor", help="Username recorded as the operator")
        parser.add_argument("--reason", default="")

    def handle(self, *args, slug, status, actor, reason, **options):
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            raise CommandError(f"Tenant '{slug}' does not exist.")

        actor_user = None
        if actor:
            user_model = get_user_model()
            actor_user = user_model.objects.filter(
                **{user_model.USERNAME_FIELD: actor}
            ).first()
            if actor_user is None:
                raise CommandError(f"User '{actor}' does not exist.")

        previous = tenant.status
        tenant.status = status
        tenant.save(update_fields=["status"])
        action = (
            "tenant.activated" if status == Tenant.Status.ACTIVE else "tenant.suspended"
        )
        record_audit(
            action,
            tenant=tenant,
            actor=actor_user,
            obj=tenant,
            previous=previous,
            reason=reason,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Tenant '{tenant.slug}' is now {tenant.status}.")
        )
