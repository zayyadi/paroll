"""API versioning + scope policy (P1-10).

Gap #10 of docs/world_class_employee_management_research_2026-10-14.md:
``api/v1`` exists; publish a versioning rule (date-based like Gusto, or
path-based) and scope tokens to resource groups before external integrators
are onboarded.

Policy adopted here
-------------------
*Versioning* — path-based (``/api/<version>/<resource>``), which is what the
URLs already follow. Versions are **additive-only and immutable once
published**: a published version never changes its response shape or removes a
field. Breaking changes ship as a new path version (``v2``); non-breaking
additions (new optional fields, new endpoints, new request options) ship
in-place within the current version. This is the Gusto/BambooHR posture:
increment the major path version only on breakage.

``CURRENT_VERSION`` below is the single source of truth for the current major
version. ``parse_version`` / ``is_supported_version`` / ``version_header``
implement the negotiation helpers used by the versioning middleware.
"""
from __future__ import annotations

import re

from django.http import JsonResponse

# The single source of truth for the current published major API version.
CURRENT_VERSION = "v1"

# Every version this deployment still serves. Add "v2" here (and a matching
# api/v2/ package) when a breaking change ships; keep serving old versions
# until their sunset date so existing integrators don't break.
SUPPORTED_VERSIONS = ("v1",)

# Versions that have been announced for removal. Requests still succeed but
# carry a ``Sunset`` header (RFC 8594) so integrators get advance warning.
SUNSET_VERSIONS: dict = {}

_VERSION_RE = re.compile(r"^v([0-9]+)$")


def parse_version(version: str | None) -> int | None:
    """Return the integer major for a version string like ``v1``, else None."""
    if not version:
        return None
    match = _VERSION_RE.match(version.strip().lower())
    if not match:
        return None
    return int(match.group(1))


def is_supported_version(version: str | None) -> bool:
    """True when ``version`` is a published, supported API version."""
    return version in SUPPORTED_VERSIONS


def version_from_request(request) -> str:
    """Resolve the requested API version for a request.

    Checks, in order:
    1. an explicit ``/api/<version>/...`` path segment (authoritative),
    2. an ``X-API-Version`` request header.

    Falls back to :data:`CURRENT_VERSION` when neither is present so
    unversioned callers land on the current version rather than an error.
    """
    resolver_match = getattr(request, "resolver_match", None)
    path_version = None
    if resolver_match is not None:
        for arg in resolver_match.kwargs.values():
            if isinstance(arg, str) and _VERSION_RE.match(arg):
                path_version = arg.lower()
                break
        if path_version is None:
            # Namespace captured versions (e.g. namespace="v1").
            ns = getattr(resolver_match, "namespace", "") or ""
            for segment in ns.split(":"):
                if _VERSION_RE.match(segment):
                    path_version = segment.lower()
                    break
    if path_version:
        return path_version

    header_version = request.headers.get("X-API-Version")
    if header_version and is_supported_version(header_version.strip().lower()):
        return header_version.strip().lower()

    return CURRENT_VERSION


def version_header(request) -> str:
    """Response header name carrying the resolved version."""
    return "X-API-Version"


def unsupported_version_response(requested: str | None) -> JsonResponse:
    """A 400 explaining an unsupported version and listing the supported set."""
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
