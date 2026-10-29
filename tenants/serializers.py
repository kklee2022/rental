from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.models import AuditEvent

from .models import Membership


class SessionStatusResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    username = serializers.CharField(required=False)
    csrf_token = serializers.CharField()


class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"})


class LoginResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    username = serializers.CharField(required=False)
    token = serializers.CharField()


class AccountTenantSerializer(serializers.ModelSerializer):
    membership_id = serializers.IntegerField(source="id", read_only=True)
    plan_code = serializers.CharField(source="tenant.plan.code", read_only=True)
    max_assets = serializers.IntegerField(
        source="tenant.plan.max_assets", read_only=True
    )
    max_users = serializers.IntegerField(source="tenant.plan.max_users", read_only=True)
    features = serializers.JSONField(source="tenant.plan.features", read_only=True)

    class Meta:
        model = Membership
        fields = (
            "membership_id",
            "role",
            "plan_code",
            "max_assets",
            "max_users",
            "features",
        )


class MembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=get_user_model().objects.all()
    )
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "user_id", "username", "email", "role", "is_active")

    def validate_user_id(self, user):
        if self.instance is not None and self.instance.user_id != user.pk:
            raise serializers.ValidationError("Membership user cannot be changed.")
        return user

    def validate(self, attrs):
        request = self.context["request"]
        user = attrs.get("user", getattr(self.instance, "user", None))
        if user is None:
            return attrs
        queryset = Membership.objects.filter(tenant=request.tenant, user=user)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                {"user_id": "This user already belongs to the tenant."}
            )
        return attrs


class AuditEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = AuditEvent
        fields = (
            "id",
            "action",
            "actor_username",
            "object_type",
            "object_id",
            "detail",
            "created_at",
        )
        read_only_fields = fields


class AccountTenantItemSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    membership = AccountTenantSerializer()


class AccountResponseSerializer(serializers.Serializer):
    username = serializers.CharField()
    tenants = AccountTenantItemSerializer(many=True)


class CurrentTenantPlanSerializer(serializers.Serializer):
    code = serializers.CharField()
    max_assets = serializers.IntegerField(allow_null=True)
    max_users = serializers.IntegerField(allow_null=True)
    features = serializers.ListField(child=serializers.CharField())


class CurrentTenantResponseSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    role = serializers.CharField()
    plan = CurrentTenantPlanSerializer()
