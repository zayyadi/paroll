"""
Development-only response-header guard.

Django's default filesystem template loader re-reads templates from disk on
every render, so a running server picks up template edits immediately -- no
restart is needed. The one thing that can still surface a stale page is an
HTTP cache: responses carry no Cache-Control header by default, which leaves
browsers (and the live Preview tab) free to heuristically keep and reuse an
old copy after a template edit.

This middleware emits Django's canonical no-cache headers on every response
while DEBUG is on, forcing the client to revalidate each request against the
freshly rendered template. It is a no-op when DEBUG is disabled, so
production caching behaviour is untouched.
"""

import re

from django.conf import settings
from django.http import Http404

NO_CACHE_HEADERS = {
    "Cache-Control": "max-age=0, no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
}


class DevNoCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.DEBUG:
            for header, value in NO_CACHE_HEADERS.items():
                response[header] = value
        return response


# Paths served by the inventory app: its pages and its REST endpoints.
INVENTORY_PATH = re.compile(r"^/(?:api/(?:v\d+/)?)?inventory/")


class InventoryFeatureMiddleware:
    """Return 404 for inventory pages and API endpoints unless enabled.

    Inventory is outside the HR/payroll/project product, so it is hidden by
    default. Its code, URLs and tables stay in place (other records may link
    to inventory documents), and ``INVENTORY_ENABLED=True`` restores it.
    The setting is read per request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "INVENTORY_ENABLED", False) and INVENTORY_PATH.match(
            request.path_info
        ):
            raise Http404("Inventory is not enabled.")
        return self.get_response(request)
