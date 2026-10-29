from django.http import JsonResponse
from rest_framework.authtoken.models import Token

from core.context import reset_current_tenant, set_current_tenant

from .models import Membership

TENANT_HEADER = "HTTP_X_TENANT"
API_PREFIX = "/api/"
TENANTLESS_API_PATHS = {
    "/api/schema/",
    "/api/docs/",
    "/api/v1/auth/csrf/",
    "/api/v1/auth/login/",
    "/api/v1/auth/logout/",
    "/api/v1/auth/session/",
    "/api/me/",
    "/api/v1/me/",
}


class TenantMiddleware:
    """Binds the active tenant for authenticated API requests.

    The tenant is chosen with the `X-Tenant: <slug>` header and is only honoured when
    the user has an active membership of an active tenant. Anything else is rejected
    before view code runs, so tenant-scoped queries can never see another tenant.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _authenticate_token(self, request):
        if request.user.is_authenticated:
            return
        authorization = request.META.get("HTTP_AUTHORIZATION", "")
        scheme, _, key = authorization.partition(" ")
        if scheme.lower() != "token" or not key:
            return
        token = Token.objects.select_related("user").filter(key=key.strip()).first()
        if token is not None and token.user.is_active:
            request.user = token.user

    def __call__(self, request):
        request.tenant = None
        request.membership = None

        if not request.path.startswith(API_PREFIX):
            return self.get_response(request)
        self._authenticate_token(request)
        if request.path in TENANTLESS_API_PATHS or not request.user.is_authenticated:
            return self.get_response(request)

        slug = request.META.get(TENANT_HEADER, "").strip()
        if not slug:
            return JsonResponse({"detail": "X-Tenant header is required."}, status=400)

        membership = (
            Membership.objects.select_related("tenant__plan")
            .filter(user=request.user, tenant__slug=slug, is_active=True)
            .first()
        )
        if membership is None:
            return JsonResponse({"detail": "No access to this tenant."}, status=403)
        if not membership.tenant.is_active:
            return JsonResponse({"detail": "Tenant is suspended."}, status=403)

        request.tenant = membership.tenant
        request.membership = membership
        token = set_current_tenant(membership.tenant)
        try:
            response = self.get_response(request)
            response["Vary"] = "X-Tenant"
            return response
        finally:
            reset_current_tenant(token)
