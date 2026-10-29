from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction


class Plan(models.Model):
    """Subscription plan entitlements. Fee collection is intentionally out of scope."""

    code = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    max_assets = models.PositiveIntegerField(
        null=True, blank=True, help_text="Empty means unlimited."
    )
    max_users = models.PositiveIntegerField(
        null=True, blank=True, help_text="Empty means unlimited."
    )
    features = models.JSONField(
        default=list,
        blank=True,
        help_text="Enabled feature codes, e.g. ['asset_import'].",
    )

    def __str__(self):
        return self.name

    def clean(self):
        if not isinstance(self.features, list) or any(
            not isinstance(feature, str) or not feature.strip()
            for feature in self.features
        ):
            raise ValidationError(
                {"features": "Features must be a list of non-empty strings."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="tenants")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    def has_feature(self, code):
        features = self.plan.features
        return isinstance(features, list) and code in features


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Administrator"
    RENTAL = "rental", "Sales / rental"
    WAREHOUSE = "warehouse", "Warehouse / fleet"
    DRIVER = "driver", "Driver"
    TECHNICIAN = "technician", "Technician"
    FINANCE = "finance", "Finance"
    VIEWER = "viewer", "Read-only"


class MembershipQuerySet(models.QuerySet):
    def delete(self):
        """Route deletes through model checks so the last owner cannot be removed."""

        with transaction.atomic():
            deleted = 0
            for membership in self:
                membership.delete()
                deleted += 1
        return deleted, {self.model._meta.label: deleted}


class Membership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    is_active = models.BooleanField(default=True)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant"], name="unique_membership_per_tenant"
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.tenant} ({self.role})"

    def _validate_owner_removal(self, *, deleting=False):
        if self.pk is None:
            return
        previous = (
            Membership.objects.filter(pk=self.pk).values("role", "is_active").first()
        )
        if not previous:
            return
        removes_owner = (
            previous["role"] == Role.OWNER
            and previous["is_active"]
            and (deleting or self.role != Role.OWNER or not self.is_active)
        )
        if not removes_owner:
            return
        other_owners = Membership.objects.filter(
            tenant_id=self.tenant_id,
            role=Role.OWNER,
            is_active=True,
        ).exclude(pk=self.pk)
        if not other_owners.exists():
            raise ValidationError(
                {"role": "A tenant must retain at least one active owner."}
            )

    def _validate_quota(self, tenant):
        if not self.is_active or tenant.plan.max_users is None:
            return
        active_memberships = Membership.objects.filter(tenant=tenant, is_active=True)
        if self.pk is not None:
            active_memberships = active_memberships.exclude(pk=self.pk)
        if active_memberships.count() >= tenant.plan.max_users:
            raise ValidationError(
                {
                    "max_users": (
                        f"Plan '{tenant.plan.code}' allows at most "
                        f"{tenant.plan.max_users} active users."
                    )
                }
            )

    def clean(self):
        super().clean()
        if self.tenant_id is None:
            return
        self._validate_owner_removal()
        self._validate_quota(self.tenant)

    def save(self, *args, **kwargs):
        if kwargs.get("raw"):
            return super().save(*args, **kwargs)

        with transaction.atomic():
            tenant = (
                Tenant.objects.select_for_update()
                .select_related("plan")
                .get(pk=self.tenant_id)
            )
            if not tenant.is_active:
                raise ValidationError({"tenant": "Cannot change a suspended tenant."})

            self._validate_owner_removal()
            self._validate_quota(tenant)
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=self.tenant_id)
            self._validate_owner_removal(deleting=True)
            return super().delete(*args, **kwargs)
