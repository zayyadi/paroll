from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseForbidden

from company.tenancy import set_current_company
from company.utils import get_user_company


class ActiveCompanyMiddleware:
    """
    Resolves and attaches the active tenant company to every authenticated request.
    Blocks non-superusers that have no active company in SaaS mode.

    Also establishes the contextvars-based company context for the request's
    lifetime (``get_user_company`` sets it) and clears it unconditionally
    afterwards, so no tenant context leaks across requests on the same thread.
    """

    EXEMPT_PATH_PREFIXES = (
        "/health",
        "/ready",
        "/users/login",
        "/users/logout",
        "/users/register",
        "/users/password_reset",
        "/users/activate",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Fresh tenant context per request; cleared in ``finally`` so a
        # previous request can never leak its company into this one.
        set_current_company(None)
        try:
            request.tenant_company = None
            user = getattr(request, "user", None)
            if not getattr(user, "is_authenticated", False):
                return self.get_response(request)

            company = get_user_company(user)
            request.tenant_company = company

            if not getattr(settings, "SAAS_ENFORCE_ACTIVE_COMPANY", True):
                return self.get_response(request)

            if user.is_superuser:
                return self.get_response(request)

            path = request.path or ""
            if path.startswith(self.EXEMPT_PATH_PREFIXES):
                return self.get_response(request)

            if company is None:
                return HttpResponseForbidden(
                    "No active company is assigned to your account. Contact your administrator."
                )

            return self.get_response(request)
        finally:
            set_current_company(None)
