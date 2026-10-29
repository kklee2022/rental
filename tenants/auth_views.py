from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    LoginRequestSerializer,
    LoginResponseSerializer,
    SessionStatusResponseSerializer,
)


def origin_verified(request):
    origin = request.META.get("HTTP_ORIGIN", "").rstrip("/")
    if not origin:
        return False
    same_origin = f"{request.scheme}://{request.get_host()}".rstrip("/")
    trusted = {value.rstrip("/") for value in settings.CSRF_TRUSTED_ORIGINS}
    return origin == same_origin or origin in trusted


@ensure_csrf_cookie
@require_GET
def csrf_token(request):
    return JsonResponse({"detail": "CSRF cookie set."})


class SessionLoginView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(
        request=LoginRequestSerializer,
        responses={200: LoginResponseSerializer, 400: LoginResponseSerializer},
        auth=[],
    )
    def post(self, request):
        if not origin_verified(request._request):
            return Response({"detail": "Origin verification failed."}, status=403)
        payload = LoginRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = authenticate(
            request=request._request,
            username=payload.validated_data["username"].strip(),
            password=payload.validated_data["password"],
        )
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=400)
        login(request._request, user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "detail": "Signed in.",
                "username": user.get_username(),
                "token": token.key,
            }
        )


class SessionLogoutView(APIView):
    @extend_schema(
        request=None,
        responses=SessionStatusResponseSerializer,
        auth=[{"sessionCookie": []}, {"bearerAuth": []}],
    )
    def post(self, request):
        if isinstance(request.auth, Token):
            request.auth.delete()
        logout(request._request)
        return Response({"detail": "Signed out."})


class SessionStatusView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list[Any] = []

    @extend_schema(
        responses={200: SessionStatusResponseSerializer},
        auth=[],
    )
    def get(self, request):
        if request.user.is_authenticated:
            return Response(
                {
                    "detail": "Authenticated.",
                    "username": request.user.get_username(),
                    "csrf_token": get_token(request._request),
                }
            )
        return Response(
            {
                "detail": "Anonymous.",
                "csrf_token": get_token(request._request),
            }
        )
