from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseForbidden

from company.utils import get_user_company


class ActiveCompanyMiddleware:
    """
    Resolves and attaches the active tenant company to every authenticated request.
    Blocks non-superusers that have no active company in SaaS mode.
    """

    EXEMPT_PATH_PREFIXES = (
        "/users/login",
        "/users/logout",
        "/users/register",
        "/users/password_reset",
        "/users/activate",
        "/admin/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
