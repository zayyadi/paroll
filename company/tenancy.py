from __future__ import annotations

from dataclasses import dataclass

from django.http import Http404
from django.shortcuts import get_object_or_404

from company.models import Company
from company.utils import get_user_company


@dataclass(frozen=True)
class TenantContext:
    company: Company | None


def get_tenant_context(user) -> TenantContext:
    return TenantContext(company=get_user_company(user))


def require_company(user) -> Company:
    company = get_user_company(user)
    if company is None:
        raise Http404("No active company is configured for this account.")
    return company


def scoped_queryset(queryset, user, company_field: str = "company"):
    company = get_user_company(user)
    if company is None:
        return queryset.none()
    return queryset.filter(**{company_field: company})


def scoped_get_object_or_404(model, user, company_field: str = "company", **kwargs):
    company = require_company(user)
    kwargs[company_field] = company
    return get_object_or_404(model, **kwargs)
