from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def liveness(request):
    return JsonResponse({"status": "ok"})


@require_GET
def readiness(request):
    checks = {"database": "ok", "cache": "ok"}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        checks["database"] = "unavailable"

    try:
        # This platform-level probe intentionally bypasses tenant_cache.
        from django.core.cache import cache

        probe_key = "system:readiness"
        cache.set(probe_key, "ok", timeout=5)
        if cache.get(probe_key) != "ok":
            checks["cache"] = "unavailable"
    except Exception:
        checks["cache"] = "unavailable"

    ready = all(value == "ok" for value in checks.values())
    return JsonResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status=200 if ready else 503,
    )
