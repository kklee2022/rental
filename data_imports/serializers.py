from rest_framework import serializers

from .models import ImportBatch, ImportMapping, ImportRow


class ImportBatchSerializer(serializers.ModelSerializer):
    import_type_label = serializers.CharField(
        source="get_import_type_display", read_only=True
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    duplicate_policy_label = serializers.CharField(
        source="get_duplicate_policy_display", read_only=True
    )
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username", read_only=True
    )
    committed_by_username = serializers.CharField(
        source="committed_by.username", read_only=True
    )
    can_commit = serializers.BooleanField(read_only=True)
    can_undo = serializers.BooleanField(read_only=True)

    class Meta:
        model = ImportBatch
        fields = (
            "id",
            "import_type",
            "import_type_label",
            "status",
            "status_label",
            "duplicate_policy",
            "duplicate_policy_label",
            "original_filename",
            "file_size",
            "content_sha256",
            "mapping_name",
            "total_rows",
            "valid_rows",
            "warning_rows",
            "error_rows",
            "created_rows",
            "updated_rows",
            "skipped_rows",
            "summary",
            "failure_message",
            "uploaded_by",
            "uploaded_by_username",
            "validated_at",
            "committed_by",
            "committed_by_username",
            "committed_at",
            "file_expires_at",
            "created_at",
            "updated_at",
            "can_commit",
            "can_undo",
        )
        read_only_fields = fields


class ImportRowSerializer(serializers.ModelSerializer):
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = ImportRow
        fields = (
            "id",
            "batch",
            "row_number",
            "raw_data",
            "normalized_data",
            "validation_errors",
            "warnings",
            "action",
            "action_label",
            "object_type",
            "object_id",
            "created_at",
        )
        read_only_fields = fields


class ImportMappingSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = ImportMapping
        fields = (
            "id",
            "import_type",
            "name",
            "column_mapping",
            "is_default",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_by", "created_at", "updated_at")


class ImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    import_type = serializers.ChoiceField(choices=ImportBatch.Type.choices)
    duplicate_policy = serializers.ChoiceField(
        choices=ImportBatch.DuplicatePolicy.choices,
        default=ImportBatch.DuplicatePolicy.ERROR,
    )
    column_mapping = serializers.JSONField(required=False)
    mapping_name = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
