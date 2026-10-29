from django.urls import path
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .auth_views import (
    SessionLoginView,
    SessionLogoutView,
    SessionStatusView,
    csrf_token,
)
from .views import (
    AccountView,
    AuditEventListView,
    CurrentTenantView,
    MembershipDetailView,
    MembershipListCreateView,
)

urlpatterns = [
    path("auth/csrf/", csrf_token, name="auth-csrf"),
    path(
        "auth/login/",
        csrf_exempt(SessionLoginView.as_view()),
        name="auth-login",
    ),
    path(
        "auth/logout/",
        SessionLogoutView.as_view(),
        name="auth-logout",
    ),
    path(
        "auth/session/",
        ensure_csrf_cookie(SessionStatusView.as_view()),
        name="auth-session",
    ),
    path("me/", AccountView.as_view(), name="account"),
    path("tenant/", CurrentTenantView.as_view(), name="current-tenant"),
    path(
        "memberships/",
        MembershipListCreateView.as_view(),
        name="membership-list",
    ),
    path(
        "memberships/<int:pk>/",
        MembershipDetailView.as_view(),
        name="membership-detail",
    ),
    path("audit-events/", AuditEventListView.as_view(), name="audit-event-list"),
]
