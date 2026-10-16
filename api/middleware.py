"""Versioning middleware (P1-10).

Resolves the API version for each request (see :mod:`api.versioning`), rejects
unpublished versions with a 400 that lists the supported set, and stamps the
resolved version on the response via an ``X-API-Version`` header so
integrators can pin and detect drift.

Non-``/api/`` requests pass straight through untouched.
"""
from __future__ import annotations

import re

from django.http import JsonResponse

from api.versioning import (
    CURRENT_VERSION,
    SUPPORTED_VERSIONS,
    is_supported_version,
    version_from_request,
)

_VERSION_SEGMENT_RE = re.compile(r"^v([0-9]+)$")


class ApiVersionMiddleware:
    """Reject unsupported API versions and advertise the resolved one."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        # Authoritative gate on the /api/<version>/ path segment. Any vN that
        # isn't published gets a 400 naming the supported set, so an
        # integrator hitting a future/typo'd version fails loudly instead of
        # silently missing a route (which would surface as a 404).
        segments = request.path.strip("/").split("/")
        # ["api", "v1", ...]
        if len(segments) >= 2 and _VERSION_SEGMENT_RE.match(segments[1]):
            requested = segments[1].lower()
            if not is_supported_version(requested):
                return JsonResponse(
                    {
                        "detail": (
                            f"API version {requested!r} is not supported. "
                            f"Supported versions: {', '.join(SUPPORTED_VERSIONS)}. "
                            f"The current version is {CURRENT_VERSION}."
                        ),
                        "current_version": CURRENT_VERSION,
                        "supported_versions": list(SUPPORTED_VERSIONS),
                    },
                    status=400,
                )

        resolved = version_from_request(request)
        request.api_version = resolved
        response = self.get_response(request)
        response["X-API-Version"] = resolved
        return response
