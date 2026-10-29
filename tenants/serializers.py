from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from core.models import AuditEvent

from .models import Membership, Role, TenantSettings
from .validators import validate_prefix


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


class TenantUserSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.pk", read_only=True)
    username = serializers.CharField(
        source="user.username", required=False, allow_blank=False
    )
    email = serializers.EmailField(
        source="user.email", required=False, allow_blank=True
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=False, min_length=8
    )
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    existing_user_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Membership
        fields = (
            "id",
            "user_id",
            "existing_user_id",
            "username",
            "email",
            "password",
            "role",
            "is_active",
            "date_joined",
            "last_login",
        )

    def validate_username(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Username is required.")
        queryset = get_user_model().objects.filter(username=normalized)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.user_id)
        if queryset.exists():
            raise serializers.ValidationError(
                "This username is already in use. Add the existing user instead."
            )
        return normalized

    def validate(self, attrs):
        request = self.context["request"]
        requested_role = attrs.get("role", getattr(self.instance, "role", Role.VIEWER))
        target_is_owner = self.instance is not None and self.instance.role == Role.OWNER
        if request.membership.role != Role.OWNER and (
            requested_role == Role.OWNER or target_is_owner
        ):
            raise serializers.ValidationError(
                {"role": "Only an owner can manage owner memberships."}
            )
        if self.instance is None:
            existing_id = attrs.get("existing_user_id")
            if existing_id:
                user = get_user_model().objects.filter(pk=existing_id).first()
                if user is None:
                    raise serializers.ValidationError(
                        {"existing_user_id": "User was not found."}
                    )
                if Membership.objects.filter(tenant=request.tenant, user=user).exists():
                    raise serializers.ValidationError(
                        {"existing_user_id": "User already belongs to this tenant."}
                    )
            else:
                username = attrs.get("user", {}).get("username")
                if not username:
                    raise serializers.ValidationError(
                        {"username": "Username is required."}
                    )
                if not attrs.get("password"):
                    raise serializers.ValidationError(
                        {"password": "Password is required for a new user."}
                    )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        password = validated_data.pop("password", "")
        existing_user_id = validated_data.pop("existing_user_id", None)
        user_data = validated_data.pop("user", {})
        if existing_user_id:
            user = get_user_model().objects.get(pk=existing_user_id)
        else:
            user = get_user_model().objects.create_user(
                username=user_data["username"],
                email=user_data.get("email", ""),
                password=password,
            )
        return Membership.objects.create(
            tenant=request.tenant,
            user=user,
            **validated_data,
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop("existing_user_id", None)
        user_data = validated_data.pop("user", {})
        password = validated_data.pop("password", "")
        if user_data.get("username"):
            instance.user.username = user_data["username"]
        if user_data.get("email") is not None:
            instance.user.email = user_data["email"]
        if password:
            instance.user.set_password(password)
        instance.user.save()
        return super().update(instance, validated_data)


class TenantSettingsSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="tenant.name", max_length=200)
    customer_prefix = serializers.CharField(max_length=12, validators=[validate_prefix])
    invoice_prefix = serializers.CharField(max_length=12, validators=[validate_prefix])
    rental_prefix = serializers.CharField(max_length=12, validators=[validate_prefix])
    quote_prefix = serializers.CharField(max_length=12, validators=[validate_prefix])

    class Meta:
        model = TenantSettings
        fields = (
            "id",
            "company_name",
            "customer_prefix",
            "invoice_prefix",
            "rental_prefix",
            "quote_prefix",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    @transaction.atomic
    def update(self, instance, validated_data):
        tenant_data = validated_data.pop("tenant", {})
        company_name = tenant_data.get("name", instance.tenant.name)
        for field, value in validated_data.items():
            setattr(instance, field, validate_prefix(value))
        instance.tenant.name = company_name.strip()
        instance.tenant.save(update_fields=["name"])
        instance.save()
        return instance


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
