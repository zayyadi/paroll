from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from django.conf import settings
from django.db import models
from django.http import Http404
from django.shortcuts import get_object_or_404

from company.models import Company
from company.utils import get_user_company

# ---------------------------------------------------------------------------
# Company context (contextvars)
# ---------------------------------------------------------------------------

_current_company: contextvars.ContextVar[Company | None] = contextvars.ContextVar(
    "paynest_current_company", default=None
)


class CompanyContextRequired(Exception):
    """Raised when a tenant-scoped query runs with no company context set.

    This is a programming-error signal: the code path must run inside
    ``company_context(...)`` or resolve a user's company first (e.g. via
    ``get_user_company``). It is only raised when
    ``TENANT_SCOPING_ENFORCED`` is enabled.
    """


def get_current_company() -> Company | None:
    """Return the company active in the current context, or None."""
    return _current_company.get()


def set_current_company(company: Company | None) -> None:
    """Set the company active in the current context."""
    _current_company.set(company)


@contextmanager
def company_context(company: Company | None) -> Iterator[None]:
    """Run a block with ``company`` as the active tenant context.

    Restores the previous context on exit, so nested ``company_context``
    blocks behave like a stack. Use this for background tasks, management
    commands, and tests that work with tenant-scoped models.
    """
    token = _current_company.set(company)
    try:
        yield
    finally:
        _current_company.reset(token)


# ---------------------------------------------------------------------------
# Tenant-safe cache keys
# ---------------------------------------------------------------------------


def tenant_cache_key(*parts: object) -> str:
    """Build a cache key namespaced to the current company.

    OWASP multi-tenant caching rule: per-tenant data cached without a tenant
    dimension in the key can be served to another tenant. Model parts are
    normalized to their primary key and contribute their company; otherwise
    the company comes from the current context (``get_current_company``).

    Keys are prefixed ``tenant:<company pk>:`` when a company is known and
    left unprefixed otherwise. Auth-level keys (login lockout, OTP, MFA
    step-up) and national reference data (statutory rate versions) are
    intentionally NOT tenant-scoped and must not use this helper.
    """
    company_pk = None
    normalized: list[str] = []
    for part in parts:
        if isinstance(part, models.Model):
            company_pk = company_pk or getattr(part, "company_id", None)
            part = part.pk
        normalized.append(str(part))
    if company_pk is None:
        current = get_current_company()
        if current is not None:
            company_pk = current.pk
    prefix = f"tenant:{company_pk}:" if company_pk is not None else ""
    return prefix + ":".join(normalized)


# ---------------------------------------------------------------------------
# Fail-closed read scoping
# ---------------------------------------------------------------------------


class CompanyScopedManager(models.Manager):
    """Manager that scopes every read to the current company context.

    With ``TENANT_SCOPING_ENFORCED`` enabled, querying without any company
    context set raises ``CompanyContextRequired`` instead of returning an
    unscoped queryset (fail-closed). With it disabled, behaviour matches the
    pre-retrofit app: no context means an unscoped queryset.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        company = get_current_company()
        if company is None:
            if getattr(settings, "TENANT_SCOPING_ENFORCED", False):
                raise CompanyContextRequired(
                    "No company context is set for this tenant-scoped query. "
                    "Run inside company_context(...) or call "
                    "get_user_company(user) before querying."
                )
            return queryset
        return queryset.filter(company=company)


class CompanyOwnedModel(models.Model):
    """Abstract base for tenant-owned models with fail-closed read scoping.

    ``objects`` is a ``CompanyScopedManager``: reads are transparently scoped
    to the current company context. ``all_objects`` is the unscoped escape
    hatch for migrations, backfills, and cross-tenant administration.

    Subclasses keep their own ``company`` field when they need a custom
    ``related_name`` (the base field is overridden); new models can rely on
    the inherited one.
    """

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
    )

    objects = CompanyScopedManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Request-time helpers
# ---------------------------------------------------------------------------


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
