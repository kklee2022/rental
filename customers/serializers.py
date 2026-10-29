from rest_framework import serializers

from .models import Contact, Customer, Site


class CustomerSerializer(serializers.ModelSerializer):
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
