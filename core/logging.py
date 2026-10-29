import json
import logging

from .context import get_current_tenant
from .request_context import get_request_id


class JsonFormatter(logging.Formatter):
    """Small dependency-free JSON formatter for application logs."""

    def format(self, record):
        request = getattr(record, "request", None)
        request_id = getattr(request, "request_id", None) or get_request_id()
        tenant = getattr(request, "tenant", None) or get_current_tenant()
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id,
        }
        if tenant is not None:
            payload["tenant_id"] = tenant.pk
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("tenant_id", "action", "object_type", "object_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=True, default=str)
