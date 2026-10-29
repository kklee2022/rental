import re
import uuid

from django.http import HttpResponseForbidden

from .request_context import reset_request_id, set_request_id

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class RequestIdMiddleware:
    """Attach a safe request identifier to responses and structured logs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get(REQUEST_ID_HEADER, "")
        request_id = (
            incoming if SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        )
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(token)


class PlatformAdminMiddleware:
    """Django admin is platform-only; tenant roles operate through the API."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path.startswith("/admin/")
            and request.user.is_authenticated
            and not request.user.is_superuser
        ):
            return HttpResponseForbidden("Platform administrator access required.")
        return self.get_response(request)
