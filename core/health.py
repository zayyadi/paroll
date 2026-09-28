"""Liveness / readiness probes for Docker, Nginx and orchestrators.

``/health/`` must always return 200 without touching DB/Redis so
Docker HEALTHCHECK and load-balancers never flap when infra blips.
``/ready/`` does lightweight DB + cache checks for deploy verification.
"""

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def health(request):
    return JsonResponse({"status": "ok"})


def ready(request):
    checks = {}
    status = 200
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't crash probe
        checks["database"] = f"error: {exc.__class__.__name__}"
        status = 503
    try:
        cache.set("ready_probe", "ok", 10)
        checks["cache"] = "ok" if cache.get("ready_probe") == "ok" else "error"
        if checks["cache"] != "ok":
            status = 503
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc.__class__.__name__}"
        status = 503
    checks["status"] = "ok" if status == 200 else "degraded"
    return JsonResponse(checks, status=status)
