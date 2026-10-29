import csv
import json
from io import StringIO

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from core.exports import safe_csv_value
from core.models import record_audit
from tenants.models import Role
from tenants.permissions import HasFeature, HasTenantMembership, has_role

from .models import ImportBatch, ImportMapping, ImportRow
from .parsers import ALLOWED_EXTENSIONS, MAX_FILE_BYTES
from .schemas import build_csv_template, build_xlsx_template
from .serializers import (
    ImportBatchSerializer,
    ImportMappingSerializer,
    ImportRowSerializer,
    ImportUploadSerializer,
)
from .services import (
    cancel_import_batch,
    commit_import_batch,
    file_sha256,
    undo_import_batch,
)
from .tasks import validate_import_batch_task


class ImportPermissionMixin:
    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            permission_classes = [
                IsAuthenticated,
                HasTenantMembership,
                HasFeature,
            ]
        else:
            permission_classes = [
                IsAuthenticated,
                has_role(Role.WAREHOUSE),
                HasFeature,
            ]
        return [permission() for permission in permission_classes]


class ImportBatchViewSet(
    ImportPermissionMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    serializer_class = ImportBatchSerializer
    parser_classes = [MultiPartParser, FormParser]
    required_feature = "asset_import"

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return ImportBatch._base_manager.none()
        return ImportBatch.objects.select_related("uploaded_by", "committed_by")

    @extend_schema(
        request=ImportUploadSerializer,
        responses={202: ImportBatchSerializer},
    )
    def create(self, request, *args, **kwargs):
        payload = ImportUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        upload = payload.validated_data["file"]
        extension = f".{upload.name.rsplit('.', 1)[-1].lower()}"
        if extension not in ALLOWED_EXTENSIONS:
            raise ValidationError({"file": "Only CSV and XLSX files are accepted."})
        if upload.size > MAX_FILE_BYTES:
            raise ValidationError({"file": "File exceeds the 10 MB limit."})

        mapping = payload.validated_data.get("column_mapping") or {}
        if isinstance(mapping, str):
            try:
                mapping = json.loads(mapping)
            except json.JSONDecodeError as exc:
                raise ValidationError(
                    {"column_mapping": "Column mapping must be valid JSON."}
                ) from exc
        if not isinstance(mapping, dict):
            raise ValidationError(
                {"column_mapping": "Column mapping must be an object."}
            )

        mapping_name = payload.validated_data.get("mapping_name", "").strip()
        if mapping_name and mapping:
            ImportMapping.objects.update_or_create(
                import_type=payload.validated_data["import_type"],
                name=mapping_name,
                defaults={"column_mapping": mapping, "created_by": request.user},
            )

        digest = file_sha256(upload)
        previous = (
            ImportBatch.objects.filter(content_sha256=digest)
            .exclude(status=ImportBatch.Status.CANCELLED)
            .order_by("-created_at")
            .first()
        )
        batch = ImportBatch.objects.create(
            import_type=payload.validated_data["import_type"],
            duplicate_policy=payload.validated_data["duplicate_policy"],
            file=upload,
            original_filename=upload.name,
            file_size=upload.size,
            content_sha256=digest,
            column_mapping=mapping,
            mapping_name=mapping_name,
            uploaded_by=request.user,
            summary={"duplicate_file_of": previous.pk} if previous else {},
        )
        record_audit(
            "import.uploaded",
            actor=request.user,
            obj=batch,
            filename=upload.name,
            import_type=batch.import_type,
            duplicate_file_of=previous.pk if previous else None,
        )

        validate_import_batch_task.delay(tenant_id=request.tenant.pk, batch_id=batch.pk)
        batch.refresh_from_db()
        return Response(
            self.get_serializer(batch).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(request=None, responses=ImportBatchSerializer)
    @action(detail=True, methods=["post"])
    def commit(self, request, pk=None):
        batch = commit_import_batch(self.get_object(), actor=request.user)
        return Response(self.get_serializer(batch).data)

    @extend_schema(request=None, responses=ImportBatchSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        batch = cancel_import_batch(self.get_object(), actor=request.user)
        return Response(self.get_serializer(batch).data)

    @extend_schema(request=None, responses=ImportBatchSerializer)
    @action(detail=True, methods=["post"])
    def undo(self, request, pk=None):
        batch = undo_import_batch(self.get_object(), actor=request.user)
        return Response(self.get_serializer(batch).data)

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="error-report")
    def error_report(self, request, pk=None):
        batch = self.get_object()
        output = StringIO()
        writer = csv.writer(output)
        columns = ["row_number", "action", "errors", "warnings"]
        rows = list(batch.rows.all())
        raw_columns = sorted(
            {key for row in rows for key in (row.raw_data or {}).keys()}
        )
        writer.writerow(columns + raw_columns)
        for row in rows:
            writer.writerow(
                [
                    row.row_number,
                    row.action,
                    safe_csv_value("; ".join(row.validation_errors)),
                    safe_csv_value("; ".join(row.warnings)),
                    *[
                        safe_csv_value((row.raw_data or {}).get(column, ""))
                        for column in raw_columns
                    ],
                ]
            )
        response = HttpResponse(
            "\ufeff" + output.getvalue(),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="import-errors-{batch.pk}.csv"'
        )
        return response


class ImportRowViewSet(ImportPermissionMixin, ReadOnlyModelViewSet):
    serializer_class = ImportRowSerializer
    required_feature = "asset_import"

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "batch",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Filter rows by import batch ID.",
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return ImportRow._base_manager.none()
        queryset = ImportRow.objects.select_related("batch")
        batch_id = self.request.query_params.get("batch")
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        return queryset.order_by("batch_id", "row_number")


class ImportMappingViewSet(
    ImportPermissionMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    serializer_class = ImportMappingSerializer
    required_feature = "asset_import"

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return ImportMapping._base_manager.none()
        return ImportMapping.objects.select_related("created_by")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


@extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
class ImportTemplateView(APIView):
    permission_classes = [IsAuthenticated, HasTenantMembership, HasFeature]
    required_feature = "asset_import"

    def get(self, request, import_type):
        if import_type not in ImportBatch.Type.values:
            raise ValidationError({"import_type": "Unknown import type."})
        output_format = request.query_params.get("file_format", "xlsx")
        headers = {"X-Content-Type-Options": "nosniff"}
        if output_format == "csv":
            return HttpResponse(
                build_csv_template(import_type),
                content_type="text/csv; charset=utf-8",
                headers={
                    **headers,
                    "Content-Disposition": (
                        f'attachment; filename="{import_type}-template.csv"'
                    ),
                },
            )
        return HttpResponse(
            build_xlsx_template(import_type),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                **headers,
                "Content-Disposition": (
                    f'attachment; filename="{import_type}-template.xlsx"'
                ),
            },
        )
