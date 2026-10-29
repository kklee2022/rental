from rest_framework import serializers

from core.sequences import next_document_number
from tenants.settings_service import get_number_prefix

from .models import Contact, Customer, Site


class CustomerSerializer(serializers.ModelSerializer):
    code = serializers.CharField(required=False, allow_blank=True, max_length=40)

    class Meta:
        model = Customer
        fields = (
            "id",
            "code",
            "name",
            "legal_name",
            "status",
            "email",
            "phone",
            "billing_address",
            "credit_limit",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        code = attrs.get("code", getattr(self.instance, "code", ""))
        if self.instance is not None and not code:
            raise serializers.ValidationError(
                {"code": "Customer code cannot be blank."}
            )
        return attrs

    def create(self, validated_data):
        if not validated_data.get("code"):
            validated_data["code"] = next_document_number(
                "customer",
                get_number_prefix("customer"),
            )
        return super().create(validated_data)


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = (
            "id",
            "customer",
            "code",
            "name",
            "address",
            "contact_name",
            "contact_phone",
            "access_notes",
            "latitude",
            "longitude",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")


class ContactSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = Contact
        fields = (
            "id",
            "customer",
            "customer_name",
            "name",
            "job_title",
            "email",
            "phone",
            "is_primary",
            "notes",
            "created_at",
        )
        read_only_fields = ("created_at",)
