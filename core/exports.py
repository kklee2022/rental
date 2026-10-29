"""CSV export helpers that bind output to the active tenant."""

import csv
from pathlib import Path

from django.http import StreamingHttpResponse
from django.utils.text import get_valid_filename

from .context import require_current_tenant
from .models import TenantScopedModel, record_audit


class _CsvBuffer:
    def write(self, value):
        return value


def safe_csv_value(value):
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


def tenant_csv_response(
    *,
    model,
    columns,
    filename,
    actor=None,
    queryset=None,
):
    """Stream an export that can only contain rows from the active tenant."""

    if not isinstance(model, type) or not issubclass(model, TenantScopedModel):
        raise TypeError("CSV exports require a TenantScopedModel")

    tenant = require_current_tenant()
    rows = (
        model.objects.all()
        if queryset is None
        else queryset.filter(tenant_id=tenant.pk)
    )
    row_count = rows.count()
    column_names = [column[0] for column in columns]

    record_audit(
        "export.created",
        actor=actor,
        model=model.__name__,
        filename=filename,
        row_count=row_count,
        columns=column_names,
    )

    buffer = _CsvBuffer()
    writer = csv.writer(buffer)

    def stream():
        yield writer.writerow([label for label, _ in columns])
        for obj in rows.iterator():
            yield writer.writerow(
                [
                    safe_csv_value(
                        value(obj) if callable(value) else getattr(obj, value)
                    )
                    for _, value in columns
                ]
            )

    safe_name = get_valid_filename(Path(filename).name)
    response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{tenant.slug}-{safe_name}"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
